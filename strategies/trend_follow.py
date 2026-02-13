"""
Trend Following Strategy.

Best for: 1h/4h timeframes, trending markets.
Logic:
  Uses EMA stack + ADX to identify strong trends, then enters on pullbacks.

  LONG: EMA 12 > 26 > 50, ADX > 25, price pulls back to EMA 12-26 zone, RSI not overbought
  SHORT: EMA 12 < 26 < 50, ADX > 25, price pulls back to EMA 12-26 zone, RSI not oversold
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

        ema_fast = last[f"ema_{self.params.get('ema_fast', 9)}"] if f"ema_{self.params.get('ema_fast', 9)}" in df.columns else last["ema_9"]
        ema_mid = last["ema_21"]
        ema_slow = last["ema_50"]
        adx_val = last["adx"]
        rsi_val = last["rsi"]
        macd_hist = last["macd_hist"]
        prev_macd_hist = prev["macd_hist"]

        tp_pct = self.params["take_profit_pct"]
        sl_pct = self.params["stop_loss_pct"]
        adx_threshold = self.params["adx_threshold"]

        # ============================================================
        # LONG: Uptrend pullback entry
        # ============================================================
        uptrend = ema_fast > ema_mid > ema_slow
        pullback_to_ema_long = (
            price >= ema_fast * 0.998 and          # Price near or above fast EMA
            price <= ema_fast * 1.01 and            # Not too far from fast EMA
            df["low"].iloc[-1] <= ema_fast * 1.002  # Wick touched EMA zone
        )
        # Alternative: bouncing off mid EMA
        bounce_mid_long = (
            price > ema_mid and
            df["low"].iloc[-1] <= ema_mid * 1.003 and
            prev["low"] > ema_mid * 0.998
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
            return Signal(
                symbol=symbol,
                side="buy",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=price * (1 - sl_pct),
                take_profit=price * (1 + tp_pct),
                timeframe=self.timeframe,
                reason=f"Uptrend pullback: EMA stack bullish, ADX {adx_val:.0f}, "
                       f"RSI {rsi_val:.0f}, MACD accelerating",
            )

        # ============================================================
        # SHORT: Downtrend pullback entry
        # ============================================================
        downtrend = ema_fast < ema_mid < ema_slow
        pullback_to_ema_short = (
            price <= ema_fast * 1.002 and
            price >= ema_fast * 0.99 and
            df["high"].iloc[-1] >= ema_fast * 0.998
        )
        bounce_mid_short = (
            price < ema_mid and
            df["high"].iloc[-1] >= ema_mid * 0.997 and
            prev["high"] < ema_mid * 1.002
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
            return Signal(
                symbol=symbol,
                side="sell",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=price * (1 + sl_pct),
                take_profit=price * (1 - tp_pct),
                timeframe=self.timeframe,
                reason=f"Downtrend pullback: EMA stack bearish, ADX {adx_val:.0f}, "
                       f"RSI {rsi_val:.0f}, MACD decelerating",
            )

        return None
