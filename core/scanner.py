"""
Market Scanner.

Scans all configured trading pairs across all active strategies
for the current phase and returns the best signals.
"""

from typing import List, Optional
from indicators.technical import ohlcv_to_dataframe
from strategies.base import Signal
from strategies import STRATEGY_MAP
from risk.manager import RiskManager
from core.exchange import ExchangeClient
from config.settings import TRADING_PAIRS
from utils.logger import log


class MarketScanner:
    """Scans markets for trading opportunities across multiple strategies."""

    def __init__(self, exchange: ExchangeClient, risk_manager: RiskManager):
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.last_signals: List[dict] = []

    def scan(self) -> List[Signal]:
        """
        Scan all pairs and strategies for signals.
        Returns signals sorted by confidence (highest first).
        """
        phase = self.risk_manager.get_current_phase()
        active_strategies = phase["strategies"]
        active_timeframes = phase["timeframes"]

        signals = []

        for strategy_name in active_strategies:
            if strategy_name not in STRATEGY_MAP:
                continue

            strategy = STRATEGY_MAP[strategy_name]()

            # Only use timeframes active in current phase
            if strategy.timeframe not in active_timeframes:
                continue

            for symbol in TRADING_PAIRS:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        symbol, strategy.timeframe, limit=200
                    )
                    if not ohlcv or len(ohlcv) < 50:
                        continue

                    df = ohlcv_to_dataframe(ohlcv)
                    signal = strategy.analyze(df, symbol)

                    if signal and signal.confidence >= 0.6:
                        signals.append(signal)
                        log.info(
                            f"Signal: {signal.side.upper()} {signal.symbol} "
                            f"[{signal.strategy}] conf={signal.confidence:.0%} "
                            f"RR={signal.risk_reward_ratio:.1f} - {signal.reason}"
                        )

                except Exception as e:
                    log.error(f"Error scanning {symbol} with {strategy_name}: {e}")
                    continue

        # Sort by confidence, then by R:R ratio
        signals.sort(key=lambda s: (s.confidence, s.risk_reward_ratio), reverse=True)

        # Store for dashboard display
        self.last_signals = [
            {
                "symbol": s.symbol,
                "side": s.side,
                "strategy": s.strategy,
                "confidence": s.confidence,
                "rr": s.risk_reward_ratio,
                "reason": s.reason,
            }
            for s in signals
        ]

        return signals

    def get_best_signal(self) -> Optional[Signal]:
        """Get the single best signal from the scan."""
        signals = self.scan()
        if signals:
            best = signals[0]
            log.info(f"Best signal: {best.side.upper()} {best.symbol} "
                     f"[{best.strategy}] conf={best.confidence:.0%}")
            return best
        return None
