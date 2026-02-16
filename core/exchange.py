"""
Exchange integration via CCXT.
Supports Bybit and Binance futures with unified interface.
Includes proper error handling and trailing stop updates.
"""

import ccxt
import time
from typing import Optional
from utils.logger import log
from config.settings import (
    EXCHANGE, API_KEY, API_SECRET, TESTNET, TRADING_PAIRS,
)


class ExchangeClient:
    """Unified exchange client for futures trading."""

    def __init__(self):
        self.exchange = self._init_exchange()
        self.positions = {}
        self._balance_error_count = 0
        self._last_known_balance = None
        log.info(f"Exchange initialized: {EXCHANGE} (testnet={TESTNET})")

    def _init_exchange(self):
        """Initialize the CCXT exchange instance."""
        exchange_config = {
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",  # Perpetual futures
                "adjustForTimeDifference": True,
            },
        }

        if EXCHANGE == "bybit":
            exchange = ccxt.bybit(exchange_config)
            if TESTNET:
                exchange.set_sandbox_mode(True)
        elif EXCHANGE == "binance":
            exchange = ccxt.binance(exchange_config)
            if TESTNET:
                exchange.set_sandbox_mode(True)
        else:
            raise ValueError(f"Unsupported exchange: {EXCHANGE}")

        return exchange

    def get_balance(self) -> Optional[float]:
        """Get USDT balance. Returns None on error (not 0.0)."""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            val = float(usdt.get("free", 0))
            self._balance_error_count = 0
            self._last_known_balance = val
            return val
        except Exception as e:
            self._balance_error_count += 1
            log.error(f"Failed to fetch balance (attempt #{self._balance_error_count}): {e}")
            return None

    def get_total_equity(self) -> Optional[float]:
        """Get total equity including unrealized PnL. Returns None on error."""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            val = float(usdt.get("total", 0))
            self._balance_error_count = 0
            self._last_known_balance = val
            return val
        except Exception as e:
            self._balance_error_count += 1
            log.error(f"Failed to fetch equity (attempt #{self._balance_error_count}): {e}")
            return None

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list:
        """Fetch OHLCV candlestick data."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            log.error(f"Failed to fetch OHLCV for {symbol} {timeframe}: {e}")
            return []

    def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for a trading pair."""
        try:
            self.exchange.set_leverage(leverage, symbol)
            log.info(f"Leverage set to {leverage}x for {symbol}")
        except Exception as e:
            log.warning(f"Failed to set leverage for {symbol}: {e}")

    def set_margin_mode(self, symbol: str, mode: str = "isolated"):
        """Set margin mode (isolated/cross)."""
        try:
            self.exchange.set_margin_mode(mode, symbol)
        except Exception as e:
            # Some exchanges already have this set
            log.debug(f"Margin mode set note for {symbol}: {e}")

    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        leverage: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Open a futures position with SL/TP.

        If SL fails to set, the position is closed immediately for safety.
        """
        try:
            self.set_margin_mode(symbol, "isolated")
            self.set_leverage(symbol, leverage)

            # Place market order
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
            )
            log.info(
                f"OPENED {side.upper()} {symbol} | "
                f"Amount: {amount} | Leverage: {leverage}x | "
                f"Order ID: {order['id']}"
            )

            # Set stop loss — CRITICAL for risk management
            sl_set = False
            if stop_loss:
                sl_side = "sell" if side == "buy" else "buy"
                try:
                    self._place_stop_loss(symbol, sl_side, amount, stop_loss)
                    sl_set = True
                    log.info(f"  SL set at {stop_loss}")
                except Exception as e:
                    log.error(f"  CRITICAL: Failed to set SL: {e}")

            # If SL failed, close position for safety
            if stop_loss and not sl_set:
                log.error(f"  Closing position {symbol} — SL could not be set!")
                self.close_position(symbol, side, amount)
                return None

            # Set take profit (non-critical)
            if take_profit:
                tp_side = "sell" if side == "buy" else "buy"
                try:
                    self.exchange.create_order(
                        symbol=symbol,
                        type="limit",
                        side=tp_side,
                        amount=amount,
                        price=take_profit,
                        params={"reduceOnly": True},
                    )
                    log.info(f"  TP set at {take_profit}")
                except Exception as e:
                    log.warning(f"  Failed to set TP (will manage manually): {e}")

            return order

        except Exception as e:
            log.error(f"Failed to open {side} position for {symbol}: {e}")
            return None

    def _place_stop_loss(self, symbol: str, side: str, amount: float, stop_price: float):
        """Place a stop-loss order. Raises on failure."""
        if EXCHANGE == "bybit":
            self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params={
                    "stopLossPrice": stop_price,
                    "triggerPrice": stop_price,
                    "reduceOnly": True,
                },
            )
        else:
            self.exchange.create_order(
                symbol=symbol,
                type="stop_market",
                side=side,
                amount=amount,
                params={
                    "stopPrice": stop_price,
                    "reduceOnly": True,
                },
            )

    def update_stop_loss(self, symbol: str, side: str, amount: float, new_sl: float) -> bool:
        """
        Update stop loss by cancelling old orders and placing new one.
        This is the actual trailing stop implementation on the exchange.
        Returns True on success.
        """
        try:
            # Cancel existing stop orders for this symbol
            self.cancel_all_orders(symbol)
            time.sleep(0.3)  # Brief delay for exchange to process

            # Place new SL
            sl_side = "sell" if side == "buy" else "buy"
            self._place_stop_loss(symbol, sl_side, amount, new_sl)
            log.info(f"SL updated on exchange for {symbol}: {new_sl:.4f}")
            return True
        except Exception as e:
            log.error(f"Failed to update SL for {symbol}: {e}")
            return False

    def close_position(self, symbol: str, side: str, amount: float) -> Optional[dict]:
        """Close an open position."""
        try:
            close_side = "sell" if side == "buy" else "buy"
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=close_side,
                amount=amount,
                params={"reduceOnly": True},
            )
            log.info(f"CLOSED {side.upper()} {symbol} | Amount: {amount}")
            # Cancel any remaining orders (SL/TP)
            self.cancel_all_orders(symbol)
            return order
        except Exception as e:
            log.error(f"Failed to close position {symbol}: {e}")
            return None

    def get_open_positions(self) -> list:
        """Get all open positions."""
        try:
            positions = self.exchange.fetch_positions()
            return [
                p for p in positions
                if float(p.get("contracts", 0)) > 0
            ]
        except Exception as e:
            log.error(f"Failed to fetch positions: {e}")
            return []

    def cancel_all_orders(self, symbol: str):
        """Cancel all open orders for a symbol."""
        try:
            self.exchange.cancel_all_orders(symbol)
        except Exception as e:
            log.debug(f"Cancel orders note for {symbol}: {e}")

    def get_ticker(self, symbol: str) -> dict:
        """Get current ticker data."""
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            log.error(f"Failed to fetch ticker for {symbol}: {e}")
            return {}

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """Get order book data."""
        try:
            return self.exchange.fetch_order_book(symbol, limit)
        except Exception as e:
            log.error(f"Failed to fetch orderbook for {symbol}: {e}")
            return {}

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get current funding rate for a perpetual contract."""
        try:
            funding = self.exchange.fetch_funding_rate(symbol)
            return float(funding.get("fundingRate", 0))
        except Exception as e:
            log.debug(f"Failed to get funding rate for {symbol}: {e}")
            return None

    def get_market_info(self, symbol: str) -> dict:
        """Get market info (min order size, tick size, etc.)."""
        try:
            self.exchange.load_markets()
            return self.exchange.market(symbol)
        except Exception as e:
            log.error(f"Failed to get market info for {symbol}: {e}")
            return {}
