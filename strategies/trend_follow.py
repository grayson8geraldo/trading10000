"""
Trend Following Strategy.

Best for: 1h/4h timeframes, trending markets.
Logic:
  Uses EMA stack + ADX to identify strong trends, then enters on pullbacks.

  LONG: EMA 12 > 26 > 50, ADX > 25, price pulls back to EMA zone, RSI not overbought
  SHORT: EMA 12 < 26 < 50, ADX > 25, price pulls back to EMA zone, RSI not oversold
"""

from typing import Optional
import pandas as pd
from strategies.base import BaseStrategy, Signal
from indicators.technical import compute_all_indicators
from config.settings import STRATEGY_PARAMS


class TrendFollowStrategy(BaseStrategy):

    def __init__(self):
        params = STRATEGY_PARAMS["trend_follow"]
        super().__init__("trend_follow", params)

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        df = compute_all_indicators(df, self.params)

        if len(df) < 60:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last["close"]

        # Use correct EMA columns — all periods computed in compute_all_indicators
        ema_fast = last["ema_12"]
        ema_mid = last["ema_26"]
        ema_slow = last["ema_50"]
        adx_val = last["adx"]
        rsi_val = last["rsi"]
        macd_hist = last["macd_hist"]
        prev_macd_hist = prev["macd_hist"]
        atr_val = last["atr"]

        tp_pct = self.params["take_profit_pct"]
        sl_pct = self.params["stop_loss_pct"]
        adx_threshold = self.params["adx_threshold"]

        # ============================================================
        # LONG: Uptrend pullback entry
        # ============================================================
        uptrend = ema_fast > ema_mid > ema_slow

        # Wider pullback zone: price within 2% of fast EMA or touching mid EMA
        pullback_to_ema_long = (
            price >= ema_fast * 0.98 and            # Not too far below fast EMA
            price <= ema_fast * 1.015 and            # Not too far above
            df["low"].iloc[-1] <= ema_fast * 1.005   # Wick touched EMA zone
        )
        # Alternative: bouncing off mid EMA
        bounce_mid_long = (
            price > ema_mid and
            df["low"].iloc[-1] <= ema_mid * 1.005 and
            last["close"] > last["open"]             # Current candle is bullish
        )

        long_conditions = [
            uptrend,
            adx_val > adx_threshold,
            (pullback_to_ema_long or bounce_mid_long),
            rsi_val < 70,
            rsi_val > 40,
            macd_hist > prev_macd_hist,  # MACD turning up
        ]

        long_bonus = [
            last["supertrend_dir"] == 1,
            last["vol_ratio"] > 1.2,
            last["obv"] > df["obv"].iloc[-5],
            rsi_val > 50,
        ]

        if all(long_conditions):
            confidence = 0.6 + 0.08 * sum(long_bonus)
            # Use ATR-based stops for better adaptability
            sl = max(price - atr_val * 2.5, price * (1 - sl_pct))
            tp = price + atr_val * 5
            return Signal(
                symbol=symbol,
                side="buy",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                timeframe=self.timeframe,
                reason=f"Uptrend pullback: EMA stack bullish, ADX {adx_val:.0f}, "
                       f"RSI {rsi_val:.0f}, MACD accelerating",
            )

        # ============================================================
        # SHORT: Downtrend pullback entry
        # ============================================================
        downtrend = ema_fast < ema_mid < ema_slow
        pullback_to_ema_short = (
            price <= ema_fast * 1.02 and
            price >= ema_fast * 0.985 and
            df["high"].iloc[-1] >= ema_fast * 0.995
        )
        bounce_mid_short = (
            price < ema_mid and
            df["high"].iloc[-1] >= ema_mid * 0.995 and
            last["close"] < last["open"]             # Current candle is bearish
        )

        short_conditions = [
            downtrend,
            adx_val > adx_threshold,
            (pullback_to_ema_short or bounce_mid_short),
            rsi_val > 30,
            rsi_val < 60,
            macd_hist < prev_macd_hist,
        ]

        short_bonus = [
            last["supertrend_dir"] == -1,
            last["vol_ratio"] > 1.2,
            last["obv"] < df["obv"].iloc[-5],
            rsi_val < 50,
        ]

        if all(short_conditions):
            confidence = 0.6 + 0.08 * sum(short_bonus)
            sl = min(price + atr_val * 2.5, price * (1 + sl_pct))
            tp = price - atr_val * 5
            return Signal(
                symbol=symbol,
                side="sell",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                timeframe=self.timeframe,
                reason=f"Downtrend pullback: EMA stack bearish, ADX {adx_val:.0f}, "
                       f"RSI {rsi_val:.0f}, MACD decelerating",
            )

        return None
