"""
Main Trading Bot Engine.

Orchestrates the entire trading system:
1. Market scanning
2. Signal generation
3. Position management
4. Risk management
5. Trade execution
6. Dashboard updates
"""

import time
import threading
from datetime import datetime
from typing import Optional

from core.exchange import ExchangeClient
from core.scanner import MarketScanner
from risk.manager import RiskManager
from strategies.base import Signal
from dashboard.display import print_dashboard
from webhooks.tradingview import set_signal_callback, start_webhook_server
from utils.logger import log
from utils.trade_logger import log_trade, get_trade_stats
from config.settings import INITIAL_CAPITAL


class TradingBot:
    """Main trading bot that orchestrates all components."""

    def __init__(self, live_mode: bool = False, use_webhook: bool = False):
        self.live_mode = live_mode
        self.exchange = ExchangeClient()
        self.risk_manager = RiskManager(INITIAL_CAPITAL)
        self.scanner = MarketScanner(self.exchange, self.risk_manager)
        self.active_trades = {}
        self.signal_history = []
        self.running = False
        self.scan_interval = 60  # seconds between scans

        if use_webhook:
            set_signal_callback(self._handle_webhook_signal)
            self.webhook_thread = threading.Thread(
                target=start_webhook_server, daemon=True
            )

        log.info(f"Trading Bot initialized (live={live_mode})")

    def start(self, use_webhook: bool = False):
        """Start the trading bot main loop."""
        self.running = True
        log.info("=" * 50)
        log.info("  TRADING BOT STARTED")
        log.info(f"  Mode: {'LIVE' if self.live_mode else 'PAPER'}")
        log.info(f"  Capital: ${INITIAL_CAPITAL}")
        log.info("=" * 50)

        if use_webhook:
            self.webhook_thread.start()
            log.info("Webhook server started")

        # Update initial balance
        if self.live_mode:
            balance = self.exchange.get_total_equity()
            if balance > 0:
                self.risk_manager.update_capital(balance)
                log.info(f"Live balance: ${balance:.2f}")

        try:
            while self.running:
                self._run_cycle()
                self._update_dashboard()
                time.sleep(self.scan_interval)
        except KeyboardInterrupt:
            log.info("Bot stopped by user")
            self.stop()

    def stop(self):
        """Stop the trading bot."""
        self.running = False
        log.info("Trading bot stopped")

    def _run_cycle(self):
        """Execute one trading cycle: scan, evaluate, execute."""
        try:
            # Update capital from exchange
            if self.live_mode:
                balance = self.exchange.get_total_equity()
                if balance > 0:
                    self.risk_manager.update_capital(balance)

            # Check if we can trade
            can_trade, reason = self.risk_manager.can_trade()
            if not can_trade:
                log.info(f"Cannot trade: {reason}")
                return

            # Manage existing positions (trailing stops, etc.)
            self._manage_positions()

            # Scan for new signals
            signal = self.scanner.get_best_signal()
            if signal:
                self._execute_signal(signal)

        except Exception as e:
            log.error(f"Error in trading cycle: {e}")

    def _execute_signal(self, signal: Signal):
        """Execute a trading signal."""
        # Check if we already have a position in this symbol
        if signal.symbol in self.active_trades:
            log.info(f"Already have position in {signal.symbol}, skipping")
            return

        # Calculate position size
        pos_info = self.risk_manager.calculate_position_size(
            signal.entry_price, signal.stop_loss, signal.symbol
        )

        if not pos_info:
            log.warning("Could not calculate position size")
            return

        log.info(
            f"Executing: {signal.side.upper()} {signal.symbol} | "
            f"Amount: {pos_info['amount']} | Leverage: {pos_info['leverage']}x | "
            f"Risk: ${pos_info['risk_amount']} ({pos_info['risk_pct_of_capital']}%) | "
            f"SL: {signal.stop_loss:.4f} | TP: {signal.take_profit:.4f}"
        )

        if self.live_mode:
            order = self.exchange.open_position(
                symbol=signal.symbol,
                side=signal.side,
                amount=pos_info["amount"],
                leverage=pos_info["leverage"],
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )

            if order:
                self.active_trades[signal.symbol] = {
                    "signal": signal,
                    "order": order,
                    "pos_info": pos_info,
                    "entry_time": datetime.utcnow(),
                    "current_sl": signal.stop_loss,
                }
                self.risk_manager.open_positions_count += 1
                log.info(f"Position opened: {signal.symbol}")
        else:
            # Paper trading
            self.active_trades[signal.symbol] = {
                "signal": signal,
                "pos_info": pos_info,
                "entry_time": datetime.utcnow(),
                "current_sl": signal.stop_loss,
            }
            self.risk_manager.open_positions_count += 1
            log.info(f"[PAPER] Position opened: {signal.symbol}")

        self.signal_history.append({
            "time": datetime.utcnow().isoformat(),
            "symbol": signal.symbol,
            "side": signal.side,
            "strategy": signal.strategy,
            "confidence": signal.confidence,
            "reason": signal.reason,
        })

    def _manage_positions(self):
        """Manage open positions: trailing stops, break-even, etc."""
        if not self.live_mode:
            return

        positions = self.exchange.get_open_positions()
        active_symbols = set()

        for pos in positions:
            symbol = pos.get("symbol", "")
            active_symbols.add(symbol)

            if symbol in self.active_trades:
                trade = self.active_trades[symbol]
                signal = trade["signal"]
                current_price = float(pos.get("markPrice", 0))
                current_sl = trade.get("current_sl", signal.stop_loss)

                # Calculate trailing stop
                new_sl = self.risk_manager.calculate_trailing_stop(
                    side=signal.side,
                    entry_price=signal.entry_price,
                    current_price=current_price,
                    current_sl=current_sl,
                )

                if new_sl:
                    trade["current_sl"] = new_sl
                    # Update SL on exchange (cancel old, place new)
                    # This would need exchange-specific implementation
                    log.info(f"Updated trailing SL for {symbol}: {new_sl:.4f}")

        # Clean up closed positions
        closed = [s for s in self.active_trades if s not in active_symbols]
        for symbol in closed:
            trade = self.active_trades.pop(symbol)
            self.risk_manager.open_positions_count -= 1
            log.info(f"Position closed: {symbol}")

            # Log the trade
            log_trade({
                "symbol": symbol,
                "side": trade["signal"].side,
                "strategy": trade["signal"].strategy,
                "entry_price": trade["signal"].entry_price,
                "leverage": trade["pos_info"]["leverage"],
                "balance_after": self.risk_manager.current_capital,
                "phase": self.risk_manager.get_current_phase()["name"],
            })

    def _handle_webhook_signal(self, data: dict) -> dict:
        """Handle signal from TradingView webhook."""
        log.info(f"Webhook signal received: {data}")

        symbol = data["symbol"]
        side = data["side"]
        action = data["action"]

        if action == "close":
            if symbol in self.active_trades:
                trade = self.active_trades[symbol]
                if self.live_mode:
                    self.exchange.close_position(
                        symbol, trade["signal"].side,
                        trade["pos_info"]["amount"],
                    )
                self.active_trades.pop(symbol, None)
                self.risk_manager.open_positions_count -= 1
                return {"status": "closed", "symbol": symbol}
            return {"status": "no_position", "symbol": symbol}

        elif action == "open":
            price = data["price"]
            if price <= 0:
                ticker = self.exchange.get_ticker(symbol)
                price = float(ticker.get("last", 0))

            # Use provided SL/TP or calculate based on ATR
            sl = data.get("stop_loss", 0)
            tp = data.get("take_profit", 0)

            phase = self.risk_manager.get_current_phase()
            if sl <= 0:
                sl_pct = 0.01  # Default 1% SL
                sl = price * (1 - sl_pct) if side == "buy" else price * (1 + sl_pct)
            if tp <= 0:
                tp_pct = 0.02  # Default 2% TP
                tp = price * (1 + tp_pct) if side == "buy" else price * (1 - tp_pct)

            signal = Signal(
                symbol=symbol,
                side=side,
                strategy=data.get("strategy", "tv_webhook"),
                confidence=0.8,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                timeframe="webhook",
                reason=data.get("message", "TradingView webhook signal"),
            )

            self._execute_signal(signal)
            return {"status": "executed", "symbol": symbol, "side": side}

        return {"status": "unknown_action"}

    def _update_dashboard(self):
        """Update the terminal dashboard."""
        try:
            risk_status = self.risk_manager.get_status()
            positions = self.exchange.get_open_positions() if self.live_mode else []
            stats = get_trade_stats()

            print_dashboard(
                risk_status=risk_status,
                positions=positions,
                signals=self.scanner.last_signals,
                stats=stats,
            )
        except Exception as e:
            log.error(f"Dashboard update error: {e}")
