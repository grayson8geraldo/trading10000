"""
Market Regime Detector.

Classifies market conditions into regimes to select the best strategy:
  - STRONG_UPTREND:  Use trend_follow, scalp_momentum (longs only)
  - WEAK_UPTREND:    Use breakout_volume, scalp_momentum
  - RANGING:         Use mean_revert, breakout_volume
  - WEAK_DOWNTREND:  Use breakout_volume, scalp_momentum
  - STRONG_DOWNTREND: Use trend_follow, scalp_momentum (shorts only)
  - HIGH_VOLATILITY: Reduce position sizes, wider stops
  - LOW_VOLATILITY:  Squeeze breakouts, tighter stops

This is the KEY module that separates profitable bots from losing ones.
The #1 reason traders lose is using the wrong strategy for the current market.
"""

from enum import Enum
from dataclasses import dataclass
import pandas as pd
import numpy as np
from indicators.technical import (
    ema, sma, rsi, atr, adx, bollinger_bands, compute_all_indicators,
)
from utils.logger import log


class Regime(Enum):
    STRONG_UPTREND = "strong_uptrend"
    WEAK_UPTREND = "weak_uptrend"
    RANGING = "ranging"
    WEAK_DOWNTREND = "weak_downtrend"
    STRONG_DOWNTREND = "strong_downtrend"


class Volatility(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class MarketState:
    """Complete market state assessment."""
    regime: Regime
    volatility: Volatility
    trend_strength: float       # 0-100 (ADX-based)
    momentum_score: float       # -100 to +100
    volume_regime: str          # "increasing", "decreasing", "stable"
    recommended_strategies: list
    recommended_side: str       # "long", "short", "both"
    position_size_mult: float   # 0.5-1.5 multiplier for position sizing
    description: str


class MarketRegimeDetector:
    """
    Detects the current market regime using multiple timeframe analysis.
    This determines WHICH strategies to activate and in which direction.
    """

    def analyze(self, df: pd.DataFrame) -> MarketState:
        """
        Analyze a dataframe and return the current market state.
        Expects df with OHLCV data, at least 200 bars.
        """
        if len(df) < 50:
            return self._default_state()

        df = compute_all_indicators(df)

        regime = self._detect_regime(df)
        volatility = self._detect_volatility(df)
        trend_strength = self._measure_trend_strength(df)
        momentum = self._measure_momentum(df)
        vol_regime = self._volume_regime(df)

        strategies, side = self._recommend_strategies(regime, volatility)
        size_mult = self._position_size_multiplier(volatility, trend_strength)

        state = MarketState(
            regime=regime,
            volatility=volatility,
            trend_strength=trend_strength,
            momentum_score=momentum,
            volume_regime=vol_regime,
            recommended_strategies=strategies,
            recommended_side=side,
            position_size_mult=size_mult,
            description=self._describe(regime, volatility, trend_strength, momentum),
        )

        log.info(f"Market regime: {state.regime.value} | Vol: {state.volatility.value} | "
                 f"Trend: {state.trend_strength:.0f} | Mom: {state.momentum_score:.0f} | "
                 f"Side: {state.recommended_side} | Size: {state.position_size_mult:.1f}x")

        return state

    def _detect_regime(self, df: pd.DataFrame) -> Regime:
        """Classify trend regime using EMA stack + price position."""
        last = df.iloc[-1]
        price = last["close"]

        ema_20 = last["ema_20"]
        ema_50 = last["ema_50"]
        ema_200 = last["ema_200"]
        adx_val = last["adx"]

        # EMA alignment score: +3 strong bull, -3 strong bear
        alignment = 0
        if price > ema_20:
            alignment += 1
        else:
            alignment -= 1
        if ema_20 > ema_50:
            alignment += 1
        else:
            alignment -= 1
        if ema_50 > ema_200:
            alignment += 1
        else:
            alignment -= 1

        # Slope of EMA 50 over last 10 bars
        ema50_slope = (df["ema_50"].iloc[-1] - df["ema_50"].iloc[-10]) / df["ema_50"].iloc[-10] * 100

        # Strong trend requires ADX > 25 AND full EMA alignment
        if alignment == 3 and adx_val > 25 and ema50_slope > 0.5:
            return Regime.STRONG_UPTREND
        elif alignment >= 2 and adx_val > 20:
            return Regime.WEAK_UPTREND
        elif alignment == -3 and adx_val > 25 and ema50_slope < -0.5:
            return Regime.STRONG_DOWNTREND
        elif alignment <= -2 and adx_val > 20:
            return Regime.WEAK_DOWNTREND
        else:
            return Regime.RANGING

    def _detect_volatility(self, df: pd.DataFrame) -> Volatility:
        """Classify volatility using ATR and BB width percentile."""
        bb_width = df["bb_width"].iloc[-1]
        bb_width_avg = df["bb_width"].tail(50).mean()
        bb_width_std = df["bb_width"].tail(50).std()

        atr_val = df["atr"].iloc[-1]
        atr_avg = df["atr"].tail(50).mean()

        # Z-score of current BB width
        if bb_width_std > 0:
            z_score = (bb_width - bb_width_avg) / bb_width_std
        else:
            z_score = 0

        atr_ratio = atr_val / atr_avg if atr_avg > 0 else 1

        if z_score > 2 or atr_ratio > 2:
            return Volatility.EXTREME
        elif z_score > 1 or atr_ratio > 1.5:
            return Volatility.HIGH
        elif z_score < -1 or atr_ratio < 0.6:
            return Volatility.LOW
        else:
            return Volatility.NORMAL

    def _measure_trend_strength(self, df: pd.DataFrame) -> float:
        """Measure trend strength 0-100 using ADX."""
        adx_val = df["adx"].iloc[-1]
        if pd.isna(adx_val):
            return 0
        return min(float(adx_val), 100)

    def _measure_momentum(self, df: pd.DataFrame) -> float:
        """
        Measure momentum -100 to +100.
        Combines RSI, MACD, and price momentum.
        """
        last = df.iloc[-1]

        # RSI contribution (-50 to +50)
        rsi_val = last["rsi"]
        rsi_score = (rsi_val - 50)  # -50 to +50

        # MACD histogram direction
        macd_hist = last["macd_hist"]
        prev_hist = df["macd_hist"].iloc[-2]
        macd_accel = 25 if macd_hist > prev_hist else -25

        # Price momentum (% change over 10 bars)
        price_mom = (last["close"] - df["close"].iloc[-10]) / df["close"].iloc[-10] * 100
        price_score = max(min(price_mom * 5, 25), -25)

        total = rsi_score + macd_accel + price_score
        return max(min(total, 100), -100)

    def _volume_regime(self, df: pd.DataFrame) -> str:
        """Classify volume trend."""
        vol_recent = df["volume"].tail(5).mean()
        vol_older = df["volume"].tail(20).head(15).mean()

        if vol_older <= 0:
            return "stable"

        ratio = vol_recent / vol_older
        if ratio > 1.3:
            return "increasing"
        elif ratio < 0.7:
            return "decreasing"
        return "stable"

    def _recommend_strategies(self, regime: Regime, volatility: Volatility) -> tuple:
        """Recommend strategies and direction based on regime."""

        strategy_map = {
            Regime.STRONG_UPTREND: (["trend_follow", "scalp_momentum", "breakout_volume"], "long"),
            Regime.WEAK_UPTREND: (["scalp_momentum", "breakout_volume", "swing"], "long"),
            Regime.RANGING: (["mean_revert", "breakout_volume"], "both"),
            Regime.WEAK_DOWNTREND: (["scalp_momentum", "breakout_volume", "swing"], "short"),
            Regime.STRONG_DOWNTREND: (["trend_follow", "scalp_momentum", "breakout_volume"], "short"),
        }

        strategies, side = strategy_map.get(regime, (["mean_revert"], "both"))

        # In extreme volatility, prefer breakout and reduce strategy count
        if volatility == Volatility.EXTREME:
            strategies = ["breakout_volume"]
        elif volatility == Volatility.LOW:
            # Low vol = squeeze imminent, prefer breakout
            if "breakout_volume" not in strategies:
                strategies.append("breakout_volume")

        return strategies, side

    def _position_size_multiplier(self, volatility: Volatility, trend_strength: float) -> float:
        """
        Adjust position size based on conditions.
        Returns multiplier 0.3-1.5.
        """
        base = 1.0

        # Reduce in high volatility
        vol_mult = {
            Volatility.LOW: 1.1,
            Volatility.NORMAL: 1.0,
            Volatility.HIGH: 0.7,
            Volatility.EXTREME: 0.4,
        }
        base *= vol_mult.get(volatility, 1.0)

        # Increase in strong trend
        if trend_strength > 40:
            base *= 1.2
        elif trend_strength < 15:
            base *= 0.8

        return max(0.3, min(base, 1.5))

    def _describe(self, regime: Regime, volatility: Volatility,
                  trend: float, momentum: float) -> str:
        """Human-readable market description."""
        parts = []

        regime_desc = {
            Regime.STRONG_UPTREND: "Strong uptrend",
            Regime.WEAK_UPTREND: "Weak uptrend",
            Regime.RANGING: "Ranging/Sideways",
            Regime.WEAK_DOWNTREND: "Weak downtrend",
            Regime.STRONG_DOWNTREND: "Strong downtrend",
        }
        parts.append(regime_desc.get(regime, "Unknown"))
        parts.append(f"vol={volatility.value}")
        parts.append(f"ADX={trend:.0f}")

        if momentum > 30:
            parts.append("bullish momentum")
        elif momentum < -30:
            parts.append("bearish momentum")

        return " | ".join(parts)

    def _default_state(self) -> MarketState:
        """Return conservative default state when data is insufficient."""
        return MarketState(
            regime=Regime.RANGING,
            volatility=Volatility.NORMAL,
            trend_strength=0,
            momentum_score=0,
            volume_regime="stable",
            recommended_strategies=["mean_revert"],
            recommended_side="both",
            position_size_mult=0.5,
            description="Insufficient data — conservative mode",
        )
