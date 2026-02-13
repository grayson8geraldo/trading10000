"""
Mean Reversion Strategy.

Best for: 15m/1h timeframes, ranging markets.
Logic:
  Enters when price is at extremes of Bollinger Bands with RSI confirmation.
  Expects price to revert to the mean (middle band).

  LONG: Price at/below lower BB + RSI oversold + bullish candle pattern
  SHORT: Price at/above upper BB + RSI overbought + bearish candle pattern
"""

from typing import Optional
import pandas as pd
from strategies.base import BaseStrategy, Signal
from indicators.technical import compute_all_indicators
from config.settings import STRATEGY_PARAMS


class MeanRevertStrategy(BaseStrategy):

    def __init__(self):
        params = STRATEGY_PARAMS["mean_revert"]
        super().__init__("mean_revert", params)

    def _is_bullish_reversal(self, df: pd.DataFrame) -> bool:
        """Check for bullish reversal candle patterns."""
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Hammer / Pin bar
        body = abs(last["close"] - last["open"])
        lower_wick = min(last["open"], last["close"]) - last["low"]
        upper_wick = last["high"] - max(last["open"], last["close"])
        total_range = last["high"] - last["low"]

        is_hammer = (
            lower_wick > body * 2 and
            upper_wick < body * 0.5 and
            last["close"] > last["open"]
        ) if total_range > 0 else False

        # Bullish engulfing
        is_engulfing = (
            prev["close"] < prev["open"] and      # Previous was bearish
            last["close"] > last["open"] and       # Current is bullish
            last["close"] > prev["open"] and       # Current close > prev open
            last["open"] < prev["close"]           # Current open < prev close
        )

        return is_hammer or is_engulfing

    def _is_bearish_reversal(self, df: pd.DataFrame) -> bool:
        """Check for bearish reversal candle patterns."""
        last = df.iloc[-1]
        prev = df.iloc[-2]

        body = abs(last["close"] - last["open"])
        upper_wick = last["high"] - max(last["open"], last["close"])
        lower_wick = min(last["open"], last["close"]) - last["low"]
        total_range = last["high"] - last["low"]

        # Shooting star
        is_shooting_star = (
            upper_wick > body * 2 and
            lower_wick < body * 0.5 and
            last["close"] < last["open"]
        ) if total_range > 0 else False

        # Bearish engulfing
        is_engulfing = (
            prev["close"] > prev["open"] and
            last["close"] < last["open"] and
            last["close"] < prev["open"] and
            last["open"] > prev["close"]
        )

        return is_shooting_star or is_engulfing

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        df = compute_all_indicators(df, self.params)

        if len(df) < 30:
            return None

        last = df.iloc[-1]
        price = last["close"]
        rsi_val = last["rsi"]
        bb_upper = last["bb_upper"]
        bb_lower = last["bb_lower"]
        bb_mid = last["bb_mid"]
        adx_val = last["adx"]

        tp_pct = self.params["take_profit_pct"]
        sl_pct = self.params["stop_loss_pct"]

        # Skip if market is strongly trending (ADX > 30 means trend-follow is better)
        if adx_val > 35:
            return None

        # ============================================================
        # LONG: Price at lower BB + RSI oversold
        # ============================================================
        at_lower_bb = price <= bb_lower * 1.002
        rsi_oversold = rsi_val < self.params["rsi_oversold"]
        bullish_candle = self._is_bullish_reversal(df)

        long_conditions = [
            at_lower_bb,
            rsi_oversold,
            (bullish_candle or last["stoch_k"] < 20),
        ]

        long_bonus = [
            bullish_candle,
            last["williams_r"] < -80,
            last["vol_ratio"] > 1.3,
            last["macd_hist"] > df["macd_hist"].iloc[-2],
        ]

        if all(long_conditions):
            confidence = 0.55 + 0.1 * sum(long_bonus)
            return Signal(
                symbol=symbol,
                side="buy",
                strategy=self.name,
                confidence=min(confidence, 0.9),
                entry_price=price,
                stop_loss=price * (1 - sl_pct),
                take_profit=min(bb_mid, price * (1 + tp_pct)),
                timeframe=self.timeframe,
                reason=f"Mean reversion: price at lower BB, RSI {rsi_val:.0f}, "
                       f"{'bullish reversal candle' if bullish_candle else 'StochRSI oversold'}",
            )

        # ============================================================
        # SHORT: Price at upper BB + RSI overbought
        # ============================================================
        at_upper_bb = price >= bb_upper * 0.998
        rsi_overbought = rsi_val > self.params["rsi_overbought"]
        bearish_candle = self._is_bearish_reversal(df)

        short_conditions = [
            at_upper_bb,
            rsi_overbought,
            (bearish_candle or last["stoch_k"] > 80),
        ]

        short_bonus = [
            bearish_candle,
            last["williams_r"] > -20,
            last["vol_ratio"] > 1.3,
            last["macd_hist"] < df["macd_hist"].iloc[-2],
        ]

        if all(short_conditions):
            confidence = 0.55 + 0.1 * sum(short_bonus)
            return Signal(
                symbol=symbol,
                side="sell",
                strategy=self.name,
                confidence=min(confidence, 0.9),
                entry_price=price,
                stop_loss=price * (1 + sl_pct),
                take_profit=max(bb_mid, price * (1 - tp_pct)),
                timeframe=self.timeframe,
                reason=f"Mean reversion: price at upper BB, RSI {rsi_val:.0f}, "
                       f"{'bearish reversal candle' if bearish_candle else 'StochRSI overbought'}",
            )

        return None
