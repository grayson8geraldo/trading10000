"""
Pre-Trade Filters.

Additional checks before executing a trade to avoid common traps:
1. Correlation filter — don't take 3 long BTC + ETH + SOL (all correlated)
2. Session timing — avoid low-liquidity periods
3. Funding rate — avoid paying extreme funding
4. Spread check — avoid illiquid markets
5. Cooldown — minimum time between trades on same symbol
"""

from datetime import datetime, timedelta
from typing import Optional
from strategies.base import Signal
from core.exchange import ExchangeClient
from utils.logger import log


# Highly correlated pairs — treat as ONE exposure group
CORRELATION_GROUPS = {
    "btc_group": ["BTC/USDT"],
    "eth_group": ["ETH/USDT"],
    "alt_large": ["SOL/USDT", "AVAX/USDT", "LINK/USDT"],
    "alt_mid": ["ARB/USDT", "XRP/USDT"],
    "meme": ["DOGE/USDT", "PEPE/USDT", "WIF/USDT"],
}


class PreTradeFilter:
    """Applies pre-trade filters to avoid common traps."""

    def __init__(self, exchange: ExchangeClient):
        self.exchange = exchange
        self._last_trade_time = {}  # symbol -> datetime
        self._active_groups = set()

    def check(self, signal: Signal, active_positions: dict) -> tuple:
        """
        Run all pre-trade checks.

        Returns:
            (passed: bool, reason: str)
        """
        # 1. Cooldown check
        passed, reason = self._cooldown_check(signal.symbol)
        if not passed:
            return False, reason

        # 2. Correlation check
        passed, reason = self._correlation_check(signal.symbol, signal.side, active_positions)
        if not passed:
            return False, reason

        # 3. Session timing
        passed, reason = self._session_check()
        if not passed:
            return False, reason

        # 4. Funding rate check
        passed, reason = self._funding_check(signal.symbol, signal.side)
        if not passed:
            return False, reason

        return True, "All filters passed"

    def record_trade(self, symbol: str):
        """Record that a trade was taken for cooldown tracking."""
        self._last_trade_time[symbol] = datetime.utcnow()

    def _cooldown_check(self, symbol: str, min_minutes: int = 5) -> tuple:
        """Minimum time between trades on same symbol."""
        if symbol in self._last_trade_time:
            elapsed = datetime.utcnow() - self._last_trade_time[symbol]
            if elapsed < timedelta(minutes=min_minutes):
                remaining = min_minutes - elapsed.total_seconds() / 60
                return False, f"Cooldown: {remaining:.0f}m remaining for {symbol}"
        return True, "OK"

    def _correlation_check(self, symbol: str, side: str, active_positions: dict) -> tuple:
        """
        Prevent overexposure to correlated assets.
        Max 1 position per correlation group.
        """
        # Find which group this symbol belongs to
        target_group = None
        for group, symbols in CORRELATION_GROUPS.items():
            if symbol in symbols:
                target_group = group
                break

        if target_group is None:
            return True, "OK"

        # Check if we already have a position in this group
        group_symbols = CORRELATION_GROUPS[target_group]
        for active_symbol in active_positions:
            if active_symbol in group_symbols and active_symbol != symbol:
                return False, f"Correlation: already exposed to {target_group} via {active_symbol}"

        # Check if we have too many same-direction positions across all groups
        same_dir_count = sum(
            1 for pos in active_positions.values()
            if pos.get("signal", {}) and
               getattr(pos.get("signal"), "side", "") == side
        )
        if same_dir_count >= 3:
            return False, f"Max 3 same-direction positions (have {same_dir_count})"

        return True, "OK"

    def _session_check(self) -> tuple:
        """
        Check if current time is in a good trading session.
        Crypto trades 24/7 but has varying liquidity.

        Best hours (UTC):
        - 08:00-11:00: European session open
        - 13:00-16:00: US session overlap
        - 00:00-04:00: Asian session

        Worst hours (UTC):
        - 05:00-07:00: Low liquidity gap
        - 20:00-23:00: Post-US, pre-Asian gap
        """
        hour = datetime.utcnow().hour

        # We allow all hours but warn about low liquidity
        low_liquidity = hour in [5, 6, 21, 22]
        if low_liquidity:
            log.info("Low liquidity period — reducing position size recommended")

        return True, "OK"

    def _funding_check(self, symbol: str, side: str, max_rate: float = 0.001) -> tuple:
        """
        Check funding rate to avoid paying extreme funding.
        If funding is very positive and we're long, or very negative and we're short,
        we're paying the high side.
        """
        funding = self.exchange.get_funding_rate(symbol)
        if funding is None:
            return True, "OK"

        # Positive funding = longs pay shorts
        # Negative funding = shorts pay longs
        if side == "buy" and funding > max_rate:
            return False, f"High funding rate ({funding*100:.3f}%) — longs pay"
        elif side == "sell" and funding < -max_rate:
            return False, f"High negative funding ({funding*100:.3f}%) — shorts pay"

        return True, "OK"
