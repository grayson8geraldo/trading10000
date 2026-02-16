"""
Risk Management Module.

Core responsibilities:
1. Position sizing based on current phase and risk parameters
2. Dynamic leverage adjustment
3. Daily loss limits
4. Maximum drawdown protection
5. Portfolio heat monitoring
6. Trailing stop management
"""

import math
from datetime import date
from typing import Optional
from utils.logger import log
from config.settings import (
    PHASES, MAX_DAILY_LOSS_PCT, MAX_DRAWDOWN_PCT,
    TRAILING_STOP_ACTIVATION, TRAILING_STOP_CALLBACK,
    BREAK_EVEN_TRIGGER, INITIAL_CAPITAL,
)


class RiskManager:
    """Manages all risk aspects of the trading system."""

    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.peak_capital = initial_capital
        self.current_capital = initial_capital
        self.daily_start_capital = initial_capital
        self.current_date = date.today()
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.open_positions_count = 0
        self.trading_halted = False
        self.halt_reason = ""
        self._consecutive_api_failures = 0
        self.MAX_API_FAILURES = 5

    def update_capital(self, new_capital: Optional[float]):
        """
        Update current capital and check drawdown limits.
        Accepts None to indicate API failure — ignores update on None.
        """
        if new_capital is None:
            self._consecutive_api_failures += 1
            if self._consecutive_api_failures >= self.MAX_API_FAILURES:
                self.trading_halted = True
                self.halt_reason = f"Lost exchange connection ({self._consecutive_api_failures} failures)"
                log.error(f"TRADING HALTED: {self.halt_reason}")
            return

        self._consecutive_api_failures = 0
        self.current_capital = new_capital
        self.peak_capital = max(self.peak_capital, new_capital)

        # Reset daily tracking on new day
        today = date.today()
        if today != self.current_date:
            self.current_date = today
            self.daily_start_capital = new_capital
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.trading_halted = False
            self.halt_reason = ""
            log.info(f"New trading day. Capital: ${new_capital:.2f}")

        self._check_limits()

    def _check_limits(self):
        """Check if any risk limits have been breached."""
        if self.daily_start_capital <= 0:
            return

        # Daily loss limit
        daily_change = (self.current_capital - self.daily_start_capital) / self.daily_start_capital
        if daily_change < -MAX_DAILY_LOSS_PCT:
            self.trading_halted = True
            self.halt_reason = f"Daily loss limit hit: {daily_change*100:.1f}%"
            log.warning(f"TRADING HALTED: {self.halt_reason}")

        # Max drawdown from peak
        if self.peak_capital > 0:
            drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
            if drawdown > MAX_DRAWDOWN_PCT:
                self.trading_halted = True
                self.halt_reason = f"Max drawdown hit: {drawdown*100:.1f}%"
                log.warning(f"TRADING HALTED: {self.halt_reason}")

    def get_current_phase(self) -> dict:
        """Determine which phase we're in based on current capital."""
        for phase in PHASES:
            low, high = phase["capital_range"]
            if low <= self.current_capital < high:
                return phase
        return PHASES[-1]  # Default to last (most conservative) phase

    def can_trade(self) -> tuple:
        """Check if trading is allowed."""
        if self.trading_halted:
            return False, self.halt_reason

        phase = self.get_current_phase()
        if self.open_positions_count >= phase["max_concurrent_trades"]:
            return False, f"Max concurrent trades reached ({phase['max_concurrent_trades']})"

        return True, "OK"

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        symbol: str,
    ) -> Optional[dict]:
        """
        Calculate position size based on risk parameters.

        Uses fixed fractional risk: risk a percentage of capital per trade,
        then calculate position size so that if SL is hit, the loss = risk amount.
        """
        if self.current_capital <= 0 or entry_price <= 0:
            return None

        phase = self.get_current_phase()
        risk_pct = phase["risk_per_trade"]
        max_leverage = phase["max_leverage"]

        risk_amount = self.current_capital * risk_pct
        risk_per_unit = abs(entry_price - stop_loss)

        if risk_per_unit <= 0:
            log.warning("Invalid SL: same as entry price")
            return None

        # Position size in base currency (without leverage)
        position_size_base = risk_amount / risk_per_unit

        # Position value in USDT
        position_value = position_size_base * entry_price

        # Calculate required leverage
        max_margin = self.current_capital * 0.5  # Never use more than 50% as margin
        required_leverage = position_value / max_margin if max_margin > 0 else max_leverage

        # Cap leverage — use math.ceil for correct rounding
        leverage = min(math.ceil(required_leverage), max_leverage)
        leverage = max(leverage, 1)

        # Recalculate with actual leverage
        margin_available = self.current_capital * 0.4  # Use 40% of capital as margin
        max_position_value = margin_available * leverage
        position_value = min(position_value, max_position_value)
        position_size_base = position_value / entry_price

        # Final risk check
        actual_risk = position_size_base * risk_per_unit
        if actual_risk > self.current_capital * 0.08:  # Hard cap: never risk >8% of capital
            position_size_base = (self.current_capital * 0.08) / risk_per_unit
            position_value = position_size_base * entry_price
            leverage = min(math.ceil(position_value / (self.current_capital * 0.4)), max_leverage)
            actual_risk = position_size_base * risk_per_unit

        if position_size_base <= 0:
            return None

        return {
            "amount": round(position_size_base, 6),
            "leverage": leverage,
            "risk_amount": round(actual_risk, 2),
            "margin_required": round(position_value / leverage, 2) if leverage > 0 else 0,
            "position_value": round(position_value, 2),
            "risk_pct_of_capital": round(actual_risk / self.current_capital * 100, 2),
        }

    def calculate_trailing_stop(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
    ) -> Optional[float]:
        """
        Calculate trailing stop price.

        Returns:
            New stop loss price, or None if no change needed
        """
        if entry_price <= 0:
            return None

        if side == "buy":
            pnl_pct = (current_price - entry_price) / entry_price

            # Move to break-even
            if pnl_pct >= BREAK_EVEN_TRIGGER and current_sl < entry_price:
                new_sl = entry_price * 1.001  # Slight profit on BE
                log.info(f"Moving SL to break-even: {new_sl:.4f}")
                return new_sl

            # Activate trailing stop
            if pnl_pct >= TRAILING_STOP_ACTIVATION:
                trail_sl = current_price * (1 - TRAILING_STOP_CALLBACK)
                if trail_sl > current_sl:
                    log.info(f"Trailing stop updated: {trail_sl:.4f} (was {current_sl:.4f})")
                    return trail_sl

        elif side == "sell":
            pnl_pct = (entry_price - current_price) / entry_price

            if pnl_pct >= BREAK_EVEN_TRIGGER and current_sl > entry_price:
                new_sl = entry_price * 0.999
                log.info(f"Moving SL to break-even: {new_sl:.4f}")
                return new_sl

            if pnl_pct >= TRAILING_STOP_ACTIVATION:
                trail_sl = current_price * (1 + TRAILING_STOP_CALLBACK)
                if trail_sl < current_sl:
                    log.info(f"Trailing stop updated: {trail_sl:.4f} (was {current_sl:.4f})")
                    return trail_sl

        return None

    def get_status(self) -> dict:
        """Get current risk management status."""
        phase = self.get_current_phase()
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital if self.peak_capital > 0 else 0
        daily_change = (self.current_capital - self.daily_start_capital) / self.daily_start_capital if self.daily_start_capital > 0 else 0
        growth = (self.current_capital - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0

        return {
            "phase": phase["name"],
            "capital": round(self.current_capital, 2),
            "peak_capital": round(self.peak_capital, 2),
            "initial_capital": self.initial_capital,
            "total_growth": f"{growth*100:.1f}%",
            "drawdown": f"{drawdown*100:.1f}%",
            "daily_pnl": f"{daily_change*100:.2f}%",
            "max_leverage": phase["max_leverage"],
            "risk_per_trade": f"{phase['risk_per_trade']*100:.1f}%",
            "max_positions": phase["max_concurrent_trades"],
            "open_positions": self.open_positions_count,
            "trading_halted": self.trading_halted,
            "halt_reason": self.halt_reason,
        }
