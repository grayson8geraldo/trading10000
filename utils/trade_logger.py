"""Trade logging to CSV for performance tracking and analysis."""

import csv
import os
from datetime import datetime
from config.settings import TRADE_LOG_FILE

HEADERS = [
    "timestamp", "symbol", "side", "strategy", "entry_price", "exit_price",
    "quantity", "leverage", "pnl_usdt", "pnl_pct", "fee", "duration_min",
    "balance_after", "phase", "notes",
]


def init_trade_log():
    """Initialize the trade log CSV file if it doesn't exist."""
    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)


def log_trade(trade_data: dict):
    """Append a trade record to the CSV log."""
    init_trade_log()
    trade_data.setdefault("timestamp", datetime.utcnow().isoformat())
    row = [trade_data.get(h, "") for h in HEADERS]
    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def get_trade_stats() -> dict:
    """Calculate trading statistics from the log."""
    if not os.path.exists(TRADE_LOG_FILE):
        return {"total_trades": 0}

    trades = []
    with open(TRADE_LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        trades = list(reader)

    if not trades:
        return {"total_trades": 0}

    wins = [t for t in trades if float(t.get("pnl_usdt", 0)) > 0]
    losses = [t for t in trades if float(t.get("pnl_usdt", 0)) < 0]
    total_pnl = sum(float(t.get("pnl_usdt", 0)) for t in trades)
    win_pnl = sum(float(t.get("pnl_usdt", 0)) for t in wins) if wins else 0
    loss_pnl = abs(sum(float(t.get("pnl_usdt", 0)) for t in losses)) if losses else 0

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(win_pnl / len(wins), 2) if wins else 0,
        "avg_loss": round(loss_pnl / len(losses), 2) if losses else 0,
        "profit_factor": round(win_pnl / loss_pnl, 2) if loss_pnl > 0 else float("inf"),
        "best_trade": round(max(float(t.get("pnl_usdt", 0)) for t in trades), 2),
        "worst_trade": round(min(float(t.get("pnl_usdt", 0)) for t in trades), 2),
    }
