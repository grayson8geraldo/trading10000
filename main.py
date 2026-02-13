#!/usr/bin/env python3
"""
Crypto Futures Trading Bot - Main Entry Point.

Usage:
    python main.py --mode paper          # Paper trading (default)
    python main.py --mode live           # Live trading
    python main.py --mode scan           # One-time market scan
    python main.py --mode backtest       # Run backtest
    python main.py --mode webhook        # Start with TradingView webhook

WARNING: This bot uses high leverage futures trading.
Only use money you can afford to lose completely.
"""

import argparse
import sys
from utils.logger import log


def run_paper():
    """Run in paper trading mode."""
    from core.bot import TradingBot
    bot = TradingBot(live_mode=False)
    bot.start()


def run_live():
    """Run in live trading mode."""
    from config.settings import API_KEY, API_SECRET, TESTNET

    if not API_KEY or not API_SECRET:
        log.error("API_KEY and API_SECRET must be set in .env file")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("  ⚠ LIVE TRADING MODE ⚠")
    print("  This will execute REAL trades with REAL money!")
    if TESTNET:
        print("  (Running on TESTNET)")
    else:
        print("  ⚠ MAINNET - REAL FUNDS AT RISK!")
    print("=" * 50)

    confirm = input("\nType 'YES' to confirm: ")
    if confirm != "YES":
        print("Cancelled.")
        sys.exit(0)

    from core.bot import TradingBot
    bot = TradingBot(live_mode=True)
    bot.start()


def run_live_with_webhook():
    """Run live trading with TradingView webhook integration."""
    from config.settings import API_KEY, API_SECRET

    if not API_KEY or not API_SECRET:
        log.error("API_KEY and API_SECRET must be set in .env file")
        sys.exit(1)

    from core.bot import TradingBot
    bot = TradingBot(live_mode=True, use_webhook=True)
    bot.start(use_webhook=True)


def run_scan():
    """Run a one-time market scan and display results."""
    from core.exchange import ExchangeClient
    from core.scanner import MarketScanner
    from risk.manager import RiskManager
    from config.settings import INITIAL_CAPITAL

    print("\nScanning markets...\n")

    exchange = ExchangeClient()
    risk_mgr = RiskManager(INITIAL_CAPITAL)
    scanner = MarketScanner(exchange, risk_mgr)

    signals = scanner.scan()

    if not signals:
        print("No signals found.")
        return

    print(f"Found {len(signals)} signal(s):\n")
    for i, s in enumerate(signals, 1):
        print(f"  {i}. {s.side.upper():5s} {s.symbol:12s} [{s.strategy}]")
        print(f"     Confidence: {s.confidence:.0%} | R:R = {s.risk_reward_ratio:.1f}")
        print(f"     Entry: {s.entry_price:.4f} | SL: {s.stop_loss:.4f} | TP: {s.take_profit:.4f}")
        print(f"     Reason: {s.reason}")
        print()


def run_backtest():
    """Run backtesting."""
    from backtest.runner import run_full_backtest
    run_full_backtest()


def main():
    parser = argparse.ArgumentParser(
        description="Crypto Futures Trading Bot - $100 to $10,000 Challenge"
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live", "scan", "backtest", "webhook"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    args = parser.parse_args()

    if args.mode == "paper":
        run_paper()
    elif args.mode == "live":
        run_live()
    elif args.mode == "scan":
        run_scan()
    elif args.mode == "backtest":
        run_backtest()
    elif args.mode == "webhook":
        run_live_with_webhook()


if __name__ == "__main__":
    main()
