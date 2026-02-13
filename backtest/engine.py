"""
Backtesting Engine.

Simulates strategy performance on historical data.
Supports:
- Multiple strategies
- Commission/fees
- Slippage modeling
- Leverage simulation
- Position sizing via RiskManager
- Detailed performance metrics
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Optional
from indicators.technical import ohlcv_to_dataframe, compute_all_indicators
from risk.manager import RiskManager
from strategies.base import Signal
from utils.logger import log


class BacktestTrade:
    """Represents a single backtest trade."""

    def __init__(self, signal: Signal, amount: float, leverage: int, margin: float):
        self.signal = signal
        self.amount = amount
        self.leverage = leverage
        self.margin = margin
        self.entry_price = signal.entry_price
        self.stop_loss = signal.stop_loss
        self.take_profit = signal.take_profit
        self.side = signal.side
        self.entry_time = None
        self.exit_time = None
        self.exit_price = None
        self.exit_reason = ""
        self.pnl = 0.0
        self.pnl_pct = 0.0
        self.fees = 0.0

    def close(self, exit_price: float, exit_time, reason: str, fee_rate: float = 0.0006):
        """Close the trade and calculate PnL."""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason

        if self.side == "buy":
            price_change = (exit_price - self.entry_price) / self.entry_price
        else:
            price_change = (self.entry_price - exit_price) / self.entry_price

        self.pnl_pct = price_change * self.leverage
        self.fees = self.margin * self.leverage * fee_rate * 2  # Entry + exit fees
        self.pnl = (self.margin * self.pnl_pct) - self.fees

    def to_dict(self) -> dict:
        return {
            "symbol": self.signal.symbol,
            "side": self.side,
            "strategy": self.signal.strategy,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "leverage": self.leverage,
            "margin": self.margin,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct * 100, 2),
            "fees": round(self.fees, 2),
            "exit_reason": self.exit_reason,
            "entry_time": str(self.entry_time),
            "exit_time": str(self.exit_time),
        }


class BacktestEngine:
    """
    Event-driven backtesting engine.
    Walks through historical candles bar-by-bar, simulating strategy execution.
    """

    def __init__(
        self,
        initial_capital: float = 100.0,
        fee_rate: float = 0.0006,       # 0.06% taker fee (Bybit/Binance)
        slippage_pct: float = 0.0002,   # 0.02% slippage
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        self.risk_manager = RiskManager(initial_capital)
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[dict] = []
        self.capital = initial_capital

    def run(
        self,
        strategy,
        ohlcv_data: list,
        symbol: str,
        warmup_bars: int = 200,
    ) -> dict:
        """
        Run backtest for a single strategy on historical data.

        Args:
            strategy: Strategy instance with analyze() method
            ohlcv_data: Raw OHLCV data from exchange
            symbol: Trading pair symbol
            warmup_bars: Number of bars for indicator warmup

        Returns:
            dict with backtest results
        """
        df = ohlcv_to_dataframe(ohlcv_data)
        if len(df) < warmup_bars + 50:
            log.warning(f"Not enough data for backtest: {len(df)} bars")
            return {"error": "Insufficient data"}

        self.capital = self.initial_capital
        self.risk_manager = RiskManager(self.initial_capital)
        self.trades = []
        self.equity_curve = []
        open_trade: Optional[BacktestTrade] = None

        log.info(f"Running backtest: {strategy.name} on {symbol} "
                 f"({len(df)} bars, {strategy.timeframe})")

        for i in range(warmup_bars, len(df)):
            current_bar = df.iloc[i]
            bar_time = df.index[i]

            # Update risk manager
            self.risk_manager.update_capital(self.capital)

            # Check if open trade hit SL/TP
            if open_trade:
                hit_sl = False
                hit_tp = False

                if open_trade.side == "buy":
                    hit_sl = current_bar["low"] <= open_trade.stop_loss
                    hit_tp = current_bar["high"] >= open_trade.take_profit
                else:
                    hit_sl = current_bar["high"] >= open_trade.stop_loss
                    hit_tp = current_bar["low"] <= open_trade.take_profit

                if hit_sl and hit_tp:
                    # Assume SL hit first if open is unfavorable
                    if open_trade.side == "buy":
                        hit_sl = current_bar["open"] < open_trade.entry_price
                    else:
                        hit_sl = current_bar["open"] > open_trade.entry_price
                    hit_tp = not hit_sl

                if hit_sl:
                    slippage = open_trade.stop_loss * self.slippage_pct
                    exit_price = (open_trade.stop_loss - slippage if open_trade.side == "buy"
                                  else open_trade.stop_loss + slippage)
                    open_trade.close(exit_price, bar_time, "stop_loss", self.fee_rate)
                    self.capital += open_trade.pnl
                    self.trades.append(open_trade)
                    open_trade = None

                elif hit_tp:
                    slippage = open_trade.take_profit * self.slippage_pct
                    exit_price = (open_trade.take_profit - slippage if open_trade.side == "buy"
                                  else open_trade.take_profit + slippage)
                    open_trade.close(exit_price, bar_time, "take_profit", self.fee_rate)
                    self.capital += open_trade.pnl
                    self.trades.append(open_trade)
                    open_trade = None

            # Generate signal if no open trade
            if open_trade is None:
                can_trade, reason = self.risk_manager.can_trade()
                if can_trade:
                    # Pass historical window to strategy
                    window = df.iloc[max(0, i-200):i+1].copy()
                    signal = strategy.analyze(window, symbol)

                    if signal:
                        # Calculate position size
                        pos_info = self.risk_manager.calculate_position_size(
                            signal.entry_price, signal.stop_loss, symbol
                        )
                        if pos_info and pos_info["amount"] > 0:
                            # Apply slippage to entry
                            if signal.side == "buy":
                                entry = signal.entry_price * (1 + self.slippage_pct)
                            else:
                                entry = signal.entry_price * (1 - self.slippage_pct)

                            signal.entry_price = entry
                            trade = BacktestTrade(
                                signal=signal,
                                amount=pos_info["amount"],
                                leverage=pos_info["leverage"],
                                margin=pos_info["margin_required"],
                            )
                            trade.entry_time = bar_time
                            open_trade = trade
                            self.risk_manager.open_positions_count = 1

            # Record equity
            unrealized_pnl = 0
            if open_trade:
                if open_trade.side == "buy":
                    unrealized_pnl = open_trade.margin * open_trade.leverage * (
                        (current_bar["close"] - open_trade.entry_price) / open_trade.entry_price
                    )
                else:
                    unrealized_pnl = open_trade.margin * open_trade.leverage * (
                        (open_trade.entry_price - current_bar["close"]) / open_trade.entry_price
                    )

            self.equity_curve.append({
                "time": bar_time,
                "equity": self.capital + unrealized_pnl,
                "capital": self.capital,
            })

        # Close any remaining trade at last price
        if open_trade:
            open_trade.close(df.iloc[-1]["close"], df.index[-1], "end_of_data", self.fee_rate)
            self.capital += open_trade.pnl
            self.trades.append(open_trade)

        return self._generate_report()

    def _generate_report(self) -> dict:
        """Generate comprehensive backtest report."""
        if not self.trades:
            return {
                "total_trades": 0,
                "final_capital": self.capital,
                "return_pct": 0,
                "note": "No trades generated",
            }

        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        pnls = [t.pnl for t in self.trades]

        total_win = sum(t.pnl for t in wins) if wins else 0
        total_loss = abs(sum(t.pnl for t in losses)) if losses else 0

        # Equity curve analysis
        equity_values = [e["equity"] for e in self.equity_curve]
        peak = self.initial_capital
        max_dd = 0
        for eq in equity_values:
            peak = max(peak, eq)
            dd = (peak - eq) / peak
            max_dd = max(max_dd, dd)

        # Sharpe ratio approximation
        returns = pd.Series(pnls)
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

        return {
            "total_trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(self.trades) * 100, 1),
            "total_pnl": round(sum(pnls), 2),
            "total_fees": round(sum(t.fees for t in self.trades), 2),
            "initial_capital": self.initial_capital,
            "final_capital": round(self.capital, 2),
            "return_pct": round((self.capital - self.initial_capital) / self.initial_capital * 100, 1),
            "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else float("inf"),
            "avg_win": round(total_win / len(wins), 2) if wins else 0,
            "avg_loss": round(total_loss / len(losses), 2) if losses else 0,
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
            "max_drawdown": round(max_dd * 100, 1),
            "sharpe_ratio": round(sharpe, 2),
            "avg_leverage": round(np.mean([t.leverage for t in self.trades]), 1),
            "trades": [t.to_dict() for t in self.trades[-20:]],  # Last 20 trades
        }

    def print_report(self, report: dict):
        """Pretty print the backtest report."""
        print("\n" + "=" * 60)
        print("          BACKTEST REPORT")
        print("=" * 60)
        print(f"  Initial Capital:   ${report.get('initial_capital', 0):.2f}")
        print(f"  Final Capital:     ${report.get('final_capital', 0):.2f}")
        print(f"  Return:            {report.get('return_pct', 0):.1f}%")
        print(f"  Total PnL:         ${report.get('total_pnl', 0):.2f}")
        print(f"  Total Fees:        ${report.get('total_fees', 0):.2f}")
        print("-" * 60)
        print(f"  Total Trades:      {report.get('total_trades', 0)}")
        print(f"  Win Rate:          {report.get('win_rate', 0):.1f}%")
        print(f"  Profit Factor:     {report.get('profit_factor', 0):.2f}")
        print(f"  Avg Win:           ${report.get('avg_win', 0):.2f}")
        print(f"  Avg Loss:          ${report.get('avg_loss', 0):.2f}")
        print(f"  Best Trade:        ${report.get('best_trade', 0):.2f}")
        print(f"  Worst Trade:       ${report.get('worst_trade', 0):.2f}")
        print("-" * 60)
        print(f"  Max Drawdown:      {report.get('max_drawdown', 0):.1f}%")
        print(f"  Sharpe Ratio:      {report.get('sharpe_ratio', 0):.2f}")
        print(f"  Avg Leverage:      {report.get('avg_leverage', 0):.1f}x")
        print("=" * 60 + "\n")
