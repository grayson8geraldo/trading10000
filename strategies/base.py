"""
Base Strategy class.
All strategies inherit from this and implement the analyze() method.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    """Trading signal produced by a strategy."""
    symbol: str
    side: str                # "buy" (long) or "sell" (short)
    strategy: str            # Strategy name
    confidence: float        # 0.0 to 1.0
    entry_price: float       # Current/expected entry price
    stop_loss: float         # Stop loss price
    take_profit: float       # Take profit price
    timeframe: str           # Timeframe that generated the signal
    reason: str              # Human-readable reason for the signal

    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk/reward ratio."""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(self, name: str, params: dict):
        self.name = name
        self.params = params
        self.timeframe = params.get("timeframe", "15m")

    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """
        Analyze the dataframe and return a Signal if conditions are met.

        Args:
            df: DataFrame with OHLCV data and computed indicators
            symbol: Trading pair symbol

        Returns:
            Signal object if trade conditions met, None otherwise
        """
        pass

    def _check_volume(self, df: pd.DataFrame, threshold: float = 1.5) -> bool:
        """Check if current volume is above threshold * average."""
        if "vol_ratio" in df.columns:
            return df["vol_ratio"].iloc[-1] > threshold
        return True

    def _check_spread(self, df: pd.DataFrame, max_spread_pct: float = 0.001) -> bool:
        """Check if spread is acceptable (for scalping)."""
        spread = (df["high"].iloc[-1] - df["low"].iloc[-1]) / df["close"].iloc[-1]
        return spread < max_spread_pct * 10  # Reasonable candle range
