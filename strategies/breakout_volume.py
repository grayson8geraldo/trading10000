"""
Breakout Volume Strategy.

Best for: 15m/1h timeframes, after consolidation periods.
Logic:
  Detects price consolidation (squeeze) then enters on breakout with volume confirmation.
  Uses ATR for dynamic SL/TP placement.

  LONG: Price breaks above resistance + volume surge + squeeze release
  SHORT: Price breaks below support + volume surge + squeeze release
"""

from typing import Optional
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, Signal
from indicators.technical import compute_all_indicators, find_support_resistance
from config.settings import STRATEGY_PARAMS


class BreakoutVolumeStrategy(BaseStrategy):

    def __init__(self):
        params = STRATEGY_PARAMS["breakout_volume"]
        super().__init__("breakout_volume", params)

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        df = compute_all_indicators(df, self.params)

        if len(df) < self.params["lookback_period"] + 20:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last["close"]
        atr_val = last["atr"]

        if pd.isna(atr_val) or atr_val <= 0:
            return None

        vol_surge = self.params["volume_surge_mult"]
        atr_sl = self.params["atr_multiplier_sl"]
        atr_tp = self.params["atr_multiplier_tp"]

        # Squeeze detection — use scalar boolean values safely
        squeeze_prev = bool(prev["squeeze_on"]) if not pd.isna(prev["squeeze_on"]) else False
        squeeze_curr = bool(last["squeeze_on"]) if not pd.isna(last["squeeze_on"]) else False
        squeeze_released = squeeze_prev and not squeeze_curr

        # BB width narrowing
        bb_width_current = last["bb_width"]
        bb_width_avg = df["bb_width"].tail(20).mean()
        is_narrow_bb = bb_width_current < bb_width_avg * 0.8

        # Find support/resistance levels
        supports, resistances = find_support_resistance(
            df, lookback=self.params["lookback_period"]
        )

        # Check for consolidation period
        lookback = self.params["min_consolidation_bars"]
        recent_range = df["high"].tail(lookback).max() - df["low"].tail(lookback).min()
        avg_range = atr_val * lookback
        is_consolidated = recent_range < avg_range * 0.6

        vol_ratio = last["vol_ratio"]
        if pd.isna(vol_ratio):
            vol_ratio = 0

        # ============================================================
        # LONG BREAKOUT
        # ============================================================
        if resistances:
            nearest_resistance = resistances[0]
            breakout_up = (
                price > nearest_resistance and
                prev["close"] <= nearest_resistance
            )
        else:
            recent_high = df["high"].tail(self.params["lookback_period"]).max()
            breakout_up = price >= recent_high and prev["close"] < recent_high

        long_conditions = [
            breakout_up,
            vol_ratio > vol_surge,
            last["macd_hist"] > 0,
            (is_consolidated or squeeze_released or is_narrow_bb),
        ]

        long_bonus = [
            last["adx"] > 20,
            last["supertrend_dir"] == 1,
            last["rsi"] > 50 and last["rsi"] < 75,
            squeeze_released,
        ]

        if all(long_conditions):
            confidence = 0.6 + 0.08 * sum(long_bonus)
            sl = price - (atr_val * atr_sl)
            tp = price + (atr_val * atr_tp)
            return Signal(
                symbol=symbol,
                side="buy",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                timeframe=self.timeframe,
                reason=f"Breakout above resistance, volume {vol_ratio:.1f}x, "
                       f"{'squeeze release' if squeeze_released else 'consolidation breakout'}, "
                       f"ATR-based targets",
            )

        # ============================================================
        # SHORT BREAKOUT
        # ============================================================
        if supports:
            nearest_support = supports[0]
            breakout_down = (
                price < nearest_support and
                prev["close"] >= nearest_support
            )
        else:
            recent_low = df["low"].tail(self.params["lookback_period"]).min()
            breakout_down = price <= recent_low and prev["close"] > recent_low

        short_conditions = [
            breakout_down,
            vol_ratio > vol_surge,
            last["macd_hist"] < 0,
            (is_consolidated or squeeze_released or is_narrow_bb),
        ]

        short_bonus = [
            last["adx"] > 20,
            last["supertrend_dir"] == -1,
            last["rsi"] < 50 and last["rsi"] > 25,
            squeeze_released,
        ]

        if all(short_conditions):
            confidence = 0.6 + 0.08 * sum(short_bonus)
            sl = price + (atr_val * atr_sl)
            tp = price - (atr_val * atr_tp)
            return Signal(
                symbol=symbol,
                side="sell",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                timeframe=self.timeframe,
                reason=f"Breakdown below support, volume {vol_ratio:.1f}x, "
                       f"{'squeeze release' if squeeze_released else 'consolidation breakdown'}, "
                       f"ATR-based targets",
            )

        return None
