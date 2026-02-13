"""
Scalp Momentum Strategy.

Best for: 5m/15m timeframes, high-volume periods.
Logic:
  LONG: RSI recovering from oversold + EMA fast > slow + volume surge + MACD histogram turning positive
  SHORT: RSI dropping from overbought + EMA fast < slow + volume surge + MACD histogram turning negative

Target: 1-2% moves with tight stops. High win rate needed.
"""

from typing import Optional
import pandas as pd
from strategies.base import BaseStrategy, Signal
from indicators.technical import compute_all_indicators
from config.settings import STRATEGY_PARAMS


class ScalpMomentumStrategy(BaseStrategy):

    def __init__(self):
        params = STRATEGY_PARAMS["scalp_momentum"]
        super().__init__("scalp_momentum", params)

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        df = compute_all_indicators(df, self.params)

        if len(df) < 50:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last["close"]

        rsi_val = last["rsi_7"]
        rsi_prev = prev["rsi_7"]
        ema_fast = last["ema_9"]
        ema_slow = last["ema_21"]
        macd_hist = last["macd_hist"]
        macd_hist_prev = prev["macd_hist"]
        vol_ratio = last["vol_ratio"]
        supertrend_dir = last["supertrend_dir"]

        tp_pct = self.params["take_profit_pct"]
        sl_pct = self.params["stop_loss_pct"]
        vol_threshold = self.params["volume_threshold"]

        # ============================================================
        # LONG CONDITIONS
        # ============================================================
        long_conditions = [
            rsi_val > self.params["rsi_oversold"],      # RSI above oversold
            rsi_val < 60,                                 # Not overbought
            rsi_val > rsi_prev,                           # RSI rising
            ema_fast > ema_slow,                          # Bullish EMA cross
            macd_hist > macd_hist_prev,                   # MACD momentum increasing
            vol_ratio > vol_threshold,                    # Volume confirmation
            price > last["ema_50"],                       # Above 50 EMA (trend filter)
        ]

        # Bonus conditions (increase confidence)
        long_bonus = [
            supertrend_dir == 1,
            last["stoch_k"] > last["stoch_d"],
            last["cvd"] > df["cvd"].iloc[-5],
        ]

        if all(long_conditions):
            confidence = 0.6 + 0.1 * sum(long_bonus)
            return Signal(
                symbol=symbol,
                side="buy",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=price * (1 - sl_pct),
                take_profit=price * (1 + tp_pct),
                timeframe=self.timeframe,
                reason=f"RSI momentum recovery ({rsi_val:.0f}), EMA bullish, "
                       f"volume surge {vol_ratio:.1f}x, MACD acceleration",
            )

        # ============================================================
        # SHORT CONDITIONS
        # ============================================================
        short_conditions = [
            rsi_val < self.params["rsi_overbought"],     # RSI below overbought
            rsi_val > 40,                                  # Not oversold
            rsi_val < rsi_prev,                            # RSI falling
            ema_fast < ema_slow,                           # Bearish EMA cross
            macd_hist < macd_hist_prev,                    # MACD momentum decreasing
            vol_ratio > vol_threshold,                     # Volume confirmation
            price < last["ema_50"],                        # Below 50 EMA
        ]

        short_bonus = [
            supertrend_dir == -1,
            last["stoch_k"] < last["stoch_d"],
            last["cvd"] < df["cvd"].iloc[-5],
        ]

        if all(short_conditions):
            confidence = 0.6 + 0.1 * sum(short_bonus)
            return Signal(
                symbol=symbol,
                side="sell",
                strategy=self.name,
                confidence=min(confidence, 0.95),
                entry_price=price,
                stop_loss=price * (1 + sl_pct),
                take_profit=price * (1 - tp_pct),
                timeframe=self.timeframe,
                reason=f"RSI momentum drop ({rsi_val:.0f}), EMA bearish, "
                       f"volume surge {vol_ratio:.1f}x, MACD deceleration",
            )

        return None
