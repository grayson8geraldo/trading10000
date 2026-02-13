"""
Terminal Dashboard for monitoring the trading bot.
Shows real-time status, positions, and performance metrics.
"""

import os
from datetime import datetime
from tabulate import tabulate
from colorama import init, Fore, Style

init(autoreset=True)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    print(Fore.CYAN + Style.BRIGHT + """
  ╔═══════════════════════════════════════════════════════════╗
  ║           CRYPTO FUTURES TRADING BOT v1.0                ║
  ║           Target: $100 → $10,000 in 30 days              ║
  ╚═══════════════════════════════════════════════════════════╝
    """ + Style.RESET_ALL)


def print_capital_progress(risk_status: dict):
    """Display capital and growth progress."""
    capital = risk_status["capital"]
    initial = risk_status["initial_capital"]
    target = 10000.0

    progress = min((capital - initial) / (target - initial) * 100, 100) if capital > initial else 0
    bar_len = 40
    filled = int(bar_len * progress / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    color = Fore.GREEN if capital >= initial else Fore.RED
    print(f"\n  {Fore.WHITE}Phase: {Fore.YELLOW}{risk_status['phase']}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Capital: {color}${capital:.2f}{Style.RESET_ALL} "
          f"(Peak: ${risk_status['peak_capital']:.2f})")
    print(f"  {Fore.WHITE}Growth:  {color}{risk_status['total_growth']}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Daily:   {risk_status['daily_pnl']}")
    print(f"\n  Progress to $10,000:")
    print(f"  ${initial:.0f} [{Fore.GREEN}{bar}{Style.RESET_ALL}] $10,000 ({progress:.1f}%)")

    if risk_status["trading_halted"]:
        print(f"\n  {Fore.RED}⚠ TRADING HALTED: {risk_status['halt_reason']}{Style.RESET_ALL}")


def print_risk_info(risk_status: dict):
    """Display risk management parameters."""
    print(f"\n  {Fore.WHITE}─── Risk Management ───{Style.RESET_ALL}")
    data = [
        ["Max Leverage", f"{risk_status['max_leverage']}x"],
        ["Risk per Trade", risk_status["risk_per_trade"]],
        ["Max Positions", f"{risk_status['open_positions']}/{risk_status['max_positions']}"],
        ["Drawdown", risk_status["drawdown"]],
    ]
    print(tabulate(data, tablefmt="simple", colalign=("left", "right")))


def print_positions(positions: list):
    """Display open positions."""
    print(f"\n  {Fore.WHITE}─── Open Positions ───{Style.RESET_ALL}")
    if not positions:
        print(f"  {Fore.YELLOW}No open positions{Style.RESET_ALL}")
        return

    table_data = []
    for p in positions:
        side_color = Fore.GREEN if p.get("side") == "long" else Fore.RED
        pnl = float(p.get("unrealizedPnl", 0))
        pnl_color = Fore.GREEN if pnl >= 0 else Fore.RED
        table_data.append([
            p.get("symbol", ""),
            f"{side_color}{p.get('side', '').upper()}{Style.RESET_ALL}",
            f"{p.get('leverage', '')}x",
            f"${float(p.get('entryPrice', 0)):.4f}",
            f"${float(p.get('markPrice', 0)):.4f}",
            f"{pnl_color}${pnl:.2f}{Style.RESET_ALL}",
        ])

    headers = ["Symbol", "Side", "Lev", "Entry", "Mark", "uPnL"]
    print(tabulate(table_data, headers=headers, tablefmt="simple"))


def print_signals(signals: list):
    """Display recent signals."""
    print(f"\n  {Fore.WHITE}─── Recent Signals ───{Style.RESET_ALL}")
    if not signals:
        print(f"  {Fore.YELLOW}No signals{Style.RESET_ALL}")
        return

    for s in signals[-5:]:
        side_color = Fore.GREEN if s.get("side") == "buy" else Fore.RED
        print(f"  {side_color}{s.get('side', '').upper():5s}{Style.RESET_ALL} "
              f"{s.get('symbol', ''):12s} "
              f"[{s.get('strategy', '')}] "
              f"conf: {s.get('confidence', 0):.0%} "
              f"- {s.get('reason', '')[:50]}")


def print_trade_stats(stats: dict):
    """Display trading performance statistics."""
    print(f"\n  {Fore.WHITE}─── Performance Stats ───{Style.RESET_ALL}")
    if stats.get("total_trades", 0) == 0:
        print(f"  {Fore.YELLOW}No completed trades yet{Style.RESET_ALL}")
        return

    data = [
        ["Total Trades", stats["total_trades"]],
        ["Win Rate", f"{stats['win_rate']:.1f}%"],
        ["Total PnL", f"${stats['total_pnl']:.2f}"],
        ["Profit Factor", f"{stats['profit_factor']:.2f}"],
        ["Avg Win", f"${stats['avg_win']:.2f}"],
        ["Avg Loss", f"${stats['avg_loss']:.2f}"],
        ["Best Trade", f"${stats['best_trade']:.2f}"],
        ["Worst Trade", f"${stats['worst_trade']:.2f}"],
    ]
    print(tabulate(data, tablefmt="simple", colalign=("left", "right")))


def print_dashboard(risk_status: dict, positions: list, signals: list, stats: dict):
    """Print the complete dashboard."""
    clear_screen()
    print_header()
    print(f"  {Fore.WHITE}Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC{Style.RESET_ALL}")
    print_capital_progress(risk_status)
    print_risk_info(risk_status)
    print_positions(positions)
    print_signals(signals)
    print_trade_stats(stats)
    print(f"\n  {Fore.WHITE}Press Ctrl+C to stop the bot{Style.RESET_ALL}\n")
