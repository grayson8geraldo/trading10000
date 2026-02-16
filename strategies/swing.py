"""
Swing Trading Strategy.

Best for: 4h timeframe, larger moves.
Logic:
  Combines EMA trend, RSI momentum, and support/resistance levels
  for medium-term positions targeting 4-6% moves.

  LONG: Price bounces off support, EMA bullish, RSI recovering
  SHORT: Price rejected from resistance, EMA bearish, RSI dropping
"""

from typing import Optional
import pandas as pd
from strategies.base import BaseStrategy, Signal
from indicators.technical import compute_all_indicators, find_support_resistance, pivot_points
from config.settings import STRATEGY_PARAMS


class SwingStrategy(BaseStrategy):

    def __init__(self):
        params = STRATEGY_PARAMS["swing"]
        super().__init__("swing", params)

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        df = compute_all_indicators(df, self.params)

        if len(df) < 60:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last["close"]

        if price <= 0:
            return None

        ema_fast = last["ema_21"]
        ema_slow = last["ema_50"]
        rsi_val = last["rsi"]
        atr_val = last["atr"]

        tp_pct = self.params["take_profit_pct"]
        sl_pct = self.params["stop_loss_pct"]

        supports, resistances = find_support_resistance(
            df, lookback=self.params["support_resistance_lookback"]
        )

        pivots = pivot_points(df)

        # ============================================================
        # LONG: Bounce off support in uptrend
        # ============================================================
        near_support = False
        support_level = None
        for s in supports:
            if s > 0 and abs(price - s) / price < 0.01:
                near_support = True
                support_level = s
                break

        for key in ["s1", "s2"]:
            pval = pivots[key]
            if pval > 0 and abs(price - pval) / price < 0.01:
                near_support = True
                if support_level is None:
                    support_level = pval

        long_conditions = [
            ema_fast > ema_slow,
            near_support,
            rsi_val > 35 and rsi_val < 65,
            rsi_val > prev["rsi"],
            last["macd_hist"] > prev["macd_hist"],
        ]

        long_bonus = [
            last["supertrend_dir"] == 1,
            last["adx"] > 20,
            last["vol_ratio"] > 1.2,
            last["stoch_k"] > last["stoch_d"],
        ]

        if all(long_conditions):
            confidence = 0.55 + 0.1 * sum(long_bonus)
            # Use max() for long SL — pick the LOWER (wider) stop for safety
            default_sl = price * (1 - sl_pct)
            sl = min(support_level * 0.99, default_sl) if support_level else default_sl
            return Signal(
                symbol=symbol,
                side="buy",
                strategy=self.name,
                confidence=min(confidence, 0.9),
                entry_price=price,
                stop_loss=sl,
                take_profit=price * (1 + tp_pct),
                timeframe=self.timeframe,
                reason=f"Swing long: support bounce at {support_level:.2f}, "
                       f"EMA bullish, RSI {rsi_val:.0f}",
            )

        # ============================================================
        # SHORT: Rejection from resistance in downtrend
        # ============================================================
        near_resistance = False
        resistance_level = None
        for r in resistances:
            if r > 0 and abs(price - r) / price < 0.01:
                near_resistance = True
                resistance_level = r
                break

        for key in ["r1", "r2"]:
            pval = pivots[key]
            if pval > 0 and abs(price - pval) / price < 0.01:
                near_resistance = True
                if resistance_level is None:
                    resistance_level = pval

        short_conditions = [
            ema_fast < ema_slow,
            near_resistance,
            rsi_val > 35 and rsi_val < 65,
            rsi_val < prev["rsi"],
            last["macd_hist"] < prev["macd_hist"],
        ]

        short_bonus = [
            last["supertrend_dir"] == -1,
            last["adx"] > 20,
            last["vol_ratio"] > 1.2,
            last["stoch_k"] < last["stoch_d"],
        ]

        if all(short_conditions):
            confidence = 0.55 + 0.1 * sum(short_bonus)
            # Use max() for short SL — pick the HIGHER (wider) stop for safety
            default_sl = price * (1 + sl_pct)
            sl = max(resistance_level * 1.01, default_sl) if resistance_level else default_sl
            return Signal(
                symbol=symbol,
                side="sell",
                strategy=self.name,
                confidence=min(confidence, 0.9),
                entry_price=price,
                stop_loss=sl,
                take_profit=price * (1 - tp_pct),
                timeframe=self.timeframe,
                reason=f"Swing short: resistance rejection at {resistance_level:.2f}, "
                       f"EMA bearish, RSI {rsi_val:.0f}",
            )

        return None
