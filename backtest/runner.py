"""
Backtest Runner.

Runs backtests for all strategies across multiple symbols and timeframes.
Generates a comprehensive performance report.
"""

import sys
from datetime import datetime
from backtest.engine import BacktestEngine
from core.exchange import ExchangeClient
from strategies import STRATEGY_MAP
from config.settings import TRADING_PAIRS, INITIAL_CAPITAL
from utils.logger import log


def run_single_backtest(
    strategy_name: str,
    symbol: str = "BTC/USDT",
    initial_capital: float = INITIAL_CAPITAL,
    days: int = 30,
):
    """Run backtest for a single strategy on a single symbol."""
    if strategy_name not in STRATEGY_MAP:
        print(f"Unknown strategy: {strategy_name}")
        print(f"Available: {list(STRATEGY_MAP.keys())}")
        return

    strategy = STRATEGY_MAP[strategy_name]()
    exchange = ExchangeClient()
    engine = BacktestEngine(initial_capital=initial_capital)

    # Calculate limit based on timeframe and days
    tf_minutes = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15,
        "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
    }
    minutes_per_bar = tf_minutes.get(strategy.timeframe, 60)
    limit = min(int(days * 24 * 60 / minutes_per_bar), 1000)

    print(f"\nFetching {limit} bars of {strategy.timeframe} data for {symbol}...")
    ohlcv = exchange.fetch_ohlcv(symbol, strategy.timeframe, limit=limit)

    if not ohlcv:
        print("Failed to fetch data")
        return

    print(f"Running backtest: {strategy_name} on {symbol}...")
    report = engine.run(strategy, ohlcv, symbol)
    engine.print_report(report)

    return report


def run_full_backtest(initial_capital: float = INITIAL_CAPITAL, days: int = 30):
    """
    Run backtests for all strategies across key symbols.
    Produces a comparison report.
    """
    exchange = ExchangeClient()
    results = []

    # Test key symbols
    test_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    strategies_to_test = list(STRATEGY_MAP.keys())

    print("\n" + "=" * 70)
    print("  COMPREHENSIVE BACKTEST")
    print(f"  Capital: ${initial_capital} | Period: {days} days")
    print("=" * 70)

    for strategy_name in strategies_to_test:
        strategy = STRATEGY_MAP[strategy_name]()

        for symbol in test_symbols:
            try:
                # Calculate data requirements
                tf_minutes = {
                    "1m": 1, "3m": 3, "5m": 5, "15m": 15,
                    "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
                }
                minutes_per_bar = tf_minutes.get(strategy.timeframe, 60)
                limit = min(int(days * 24 * 60 / minutes_per_bar), 1000)

                ohlcv = exchange.fetch_ohlcv(symbol, strategy.timeframe, limit=limit)
                if not ohlcv or len(ohlcv) < 250:
                    continue

                engine = BacktestEngine(initial_capital=initial_capital)
                report = engine.run(strategy, ohlcv, symbol)

                if report.get("total_trades", 0) > 0:
                    results.append({
                        "strategy": strategy_name,
                        "symbol": symbol,
                        "timeframe": strategy.timeframe,
                        **report,
                    })
                    print(f"\n  {strategy_name:20s} | {symbol:12s} | "
                          f"Trades: {report['total_trades']:3d} | "
                          f"WR: {report['win_rate']:5.1f}% | "
                          f"Return: {report['return_pct']:+7.1f}% | "
                          f"PF: {report['profit_factor']:5.2f} | "
                          f"MaxDD: {report['max_drawdown']:5.1f}%")

            except Exception as e:
                log.error(f"Backtest error {strategy_name}/{symbol}: {e}")
                continue

    # Summary
    if results:
        print("\n" + "=" * 70)
        print("  SUMMARY - Best Performing Combinations")
        print("=" * 70)

        # Sort by return
        results.sort(key=lambda x: x.get("return_pct", 0), reverse=True)

        for i, r in enumerate(results[:10], 1):
            print(f"  {i:2d}. {r['strategy']:20s} {r['symbol']:12s} {r['timeframe']:4s} | "
                  f"Return: {r['return_pct']:+7.1f}% | WR: {r['win_rate']:.0f}% | "
                  f"PF: {r['profit_factor']:.2f} | Trades: {r['total_trades']}")

        # Best overall
        best = results[0]
        print(f"\n  Best: {best['strategy']} on {best['symbol']} "
              f"({best['return_pct']:+.1f}% return)")
    else:
        print("\n  No valid backtest results. Check exchange connection and data.")

    print()
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        strategy = sys.argv[1]
        symbol = sys.argv[2] if len(sys.argv) > 2 else "BTC/USDT"
        run_single_backtest(strategy, symbol)
    else:
        run_full_backtest()
