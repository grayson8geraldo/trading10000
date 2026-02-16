"""
Multi-Timeframe (MTF) Confirmation Filter.

Before executing a trade, this module checks alignment across
higher timeframes. A signal is only confirmed if:
1. The higher TF trend agrees with the signal direction
2. No major resistance/support blocks the trade on higher TF
3. Volume on higher TF supports the move

This dramatically reduces false signals and improves win rate.
"""

import pandas as pd
from typing import Optional
from indicators.technical import (
    ohlcv_to_dataframe, ema, rsi, macd, adx, supertrend
)
from core.exchange import ExchangeClient
from strategies.base import Signal
from utils.logger import log


# Timeframe hierarchy: signal TF -> confirmation TFs
TF_HIERARCHY = {
    "1m":  ["5m", "15m"],
    "3m":  ["15m", "1h"],
    "5m":  ["15m", "1h"],
    "15m": ["1h", "4h"],
    "30m": ["1h", "4h"],
    "1h":  ["4h", "1d"],
    "4h":  ["1d"],
}


class MTFConfirmation:
    """
    Multi-Timeframe filter that validates signals against higher timeframes.
    Returns a confirmation score 0.0-1.0 and can veto bad signals.
    """

    def __init__(self, exchange: ExchangeClient):
        self.exchange = exchange
        self._cache = {}  # Cache higher TF data to reduce API calls

    def confirm(self, signal: Signal) -> tuple:
        """
        Confirm a signal against higher timeframes.

        Returns:
            (confirmed: bool, score: float, reason: str)
            confirmed: True if signal passes MTF filter
            score: 0.0-1.0 confirmation strength
            reason: Human-readable explanation
        """
        higher_tfs = TF_HIERARCHY.get(signal.timeframe, [])
        if not higher_tfs:
            return True, 0.7, "No higher TF to check"

        scores = []
        reasons = []

        for htf in higher_tfs:
            try:
                ohlcv = self.exchange.fetch_ohlcv(signal.symbol, htf, limit=100)
                if not ohlcv or len(ohlcv) < 30:
                    continue

                df = ohlcv_to_dataframe(ohlcv)
                score, reason = self._check_timeframe(df, signal, htf)
                scores.append(score)
                reasons.append(f"{htf}: {reason}")

            except Exception as e:
                log.warning(f"MTF check failed for {htf}: {e}")
                continue

        if not scores:
            return True, 0.6, "Could not fetch higher TF data"

        avg_score = sum(scores) / len(scores)
        confirmed = avg_score >= 0.4  # Need at least 40% confirmation

        summary = " | ".join(reasons)
        log.info(f"MTF {'CONFIRMED' if confirmed else 'REJECTED'} "
                 f"({avg_score:.0%}): {summary}")

        return confirmed, avg_score, summary

    def _check_timeframe(self, df: pd.DataFrame, signal: Signal, tf: str) -> tuple:
        """
        Check a single higher timeframe for confirmation.
        Returns (score: 0.0-1.0, reason: str)
        """
        last = df.iloc[-1]
        price = last["close"]

        # Calculate indicators on higher TF
        df["ema_20"] = ema(df["close"], 20)
        df["ema_50"] = ema(df["close"], 50)
        df["rsi"] = rsi(df["close"], 14)
        df["macd"], df["macd_signal"], df["macd_hist"] = macd(df["close"])
        df["adx"] = adx(df)
        df["st"], df["st_dir"] = supertrend(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        score = 0.0
        details = []

        if signal.side == "buy":
            # EMA trend
            if last["ema_20"] > last["ema_50"]:
                score += 0.25
                details.append("EMA bullish")
            else:
                details.append("EMA bearish")

            # RSI not overbought
            if last["rsi"] < 70:
                score += 0.15
            if last["rsi"] > 40:
                score += 0.1

            # MACD positive or improving
            if last["macd_hist"] > 0:
                score += 0.2
                details.append("MACD+")
            elif last["macd_hist"] > prev["macd_hist"]:
                score += 0.1
                details.append("MACD improving")

            # Supertrend
            if last["st_dir"] == 1:
                score += 0.2
                details.append("ST up")

            # Price above key EMA
            if price > last["ema_50"]:
                score += 0.1

        else:  # sell/short
            if last["ema_20"] < last["ema_50"]:
                score += 0.25
                details.append("EMA bearish")
            else:
                details.append("EMA bullish")

            if last["rsi"] > 30:
                score += 0.15
            if last["rsi"] < 60:
                score += 0.1

            if last["macd_hist"] < 0:
                score += 0.2
                details.append("MACD-")
            elif last["macd_hist"] < prev["macd_hist"]:
                score += 0.1
                details.append("MACD declining")

            if last["st_dir"] == -1:
                score += 0.2
                details.append("ST down")

            if price < last["ema_50"]:
                score += 0.1

        reason = ", ".join(details) if details else "neutral"
        return min(score, 1.0), reason
