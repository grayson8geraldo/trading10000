"""
Exchange integration via CCXT.
Supports Bybit and Binance futures with unified interface.
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

    def get_balance(self) -> float:
        """Get USDT balance."""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            return float(usdt.get("free", 0))
        except Exception as e:
            log.error(f"Failed to fetch balance: {e}")
            return 0.0

    def get_total_equity(self) -> float:
        """Get total equity including unrealized PnL."""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            return float(usdt.get("total", 0))
        except Exception as e:
            log.error(f"Failed to fetch equity: {e}")
            return 0.0

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
            # Some exchanges don't need this or it's already set
            pass

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
        Open a futures position with optional SL/TP.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            side: "buy" (long) or "sell" (short)
            amount: Position size in contracts/base currency
            leverage: Leverage multiplier
            stop_loss: Stop loss price
            take_profit: Take profit price

        Returns:
            Order dict or None on failure
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

            # Set stop loss
            if stop_loss:
                sl_side = "sell" if side == "buy" else "buy"
                try:
                    self.exchange.create_order(
                        symbol=symbol,
                        type="stop_market" if EXCHANGE == "binance" else "market",
                        side=sl_side,
                        amount=amount,
                        params={
                            "stopLossPrice" if EXCHANGE == "bybit" else "stopPrice": stop_loss,
                            "triggerPrice": stop_loss,
                            "reduceOnly": True,
                        },
                    )
                    log.info(f"  SL set at {stop_loss}")
                except Exception as e:
                    log.warning(f"  Failed to set SL: {e}")

            # Set take profit
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
                    log.warning(f"  Failed to set TP: {e}")

            return order

        except Exception as e:
            log.error(f"Failed to open {side} position for {symbol}: {e}")
            return None

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
            log.info(f"All orders cancelled for {symbol}")
        except Exception as e:
            log.warning(f"Failed to cancel orders for {symbol}: {e}")

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

    def get_market_info(self, symbol: str) -> dict:
        """Get market info (min order size, tick size, etc.)."""
        try:
            self.exchange.load_markets()
            return self.exchange.market(symbol)
        except Exception as e:
            log.error(f"Failed to get market info for {symbol}: {e}")
            return {}
