"""
Global configuration for the Crypto Trading System.
Designed for aggressive growth from $100-150 to $10,000 in 30 days.

RISK WARNING: This configuration uses high leverage and aggressive position sizing.
Only use money you can afford to lose completely.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# EXCHANGE CONFIGURATION
# ============================================================
EXCHANGE = os.getenv("EXCHANGE", "bybit")  # bybit, binance
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")
TESTNET = os.getenv("TESTNET", "true").lower() == "true"

# ============================================================
# CAPITAL & GROWTH PLAN
# ============================================================
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "100"))
TARGET_CAPITAL = 10000.0
TRADING_DAYS = 30

# Compound growth phases (adapt leverage and risk as capital grows)
PHASES = [
    {
        "name": "Phase 1 - Micro Account",
        "capital_range": (0, 300),
        "max_leverage": 50,
        "risk_per_trade": 0.05,       # 5% of capital per trade
        "max_concurrent_trades": 2,
        "strategies": ["scalp_momentum", "breakout_volume"],
        "timeframes": ["5m", "15m"],
    },
    {
        "name": "Phase 2 - Growth",
        "capital_range": (300, 1000),
        "max_leverage": 30,
        "risk_per_trade": 0.04,       # 4% of capital per trade
        "max_concurrent_trades": 3,
        "strategies": ["scalp_momentum", "breakout_volume", "trend_follow"],
        "timeframes": ["5m", "15m", "1h"],
    },
    {
        "name": "Phase 3 - Acceleration",
        "capital_range": (1000, 3000),
        "max_leverage": 20,
        "risk_per_trade": 0.03,       # 3% of capital per trade
        "max_concurrent_trades": 3,
        "strategies": ["scalp_momentum", "breakout_volume", "trend_follow", "mean_revert"],
        "timeframes": ["15m", "1h", "4h"],
    },
    {
        "name": "Phase 4 - Capital Preservation",
        "capital_range": (3000, 100000),
        "max_leverage": 10,
        "risk_per_trade": 0.02,       # 2% of capital per trade
        "max_concurrent_trades": 4,
        "strategies": ["trend_follow", "breakout_volume", "mean_revert", "swing"],
        "timeframes": ["1h", "4h"],
    },
]

# ============================================================
# TRADING PAIRS (sorted by liquidity and volatility)
# ============================================================
TRADING_PAIRS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "DOGE/USDT",
    "XRP/USDT",
    "PEPE/USDT",
    "WIF/USDT",
    "ARB/USDT",
    "AVAX/USDT",
    "LINK/USDT",
]

# ============================================================
# RISK MANAGEMENT
# ============================================================
MAX_DAILY_LOSS_PCT = 0.15           # Stop trading if 15% daily loss
MAX_DRAWDOWN_PCT = 0.30             # Stop trading if 30% total drawdown
TRAILING_STOP_ACTIVATION = 0.015    # Activate trailing stop at 1.5% profit
TRAILING_STOP_CALLBACK = 0.005      # Trail by 0.5%
BREAK_EVEN_TRIGGER = 0.01           # Move SL to break-even at 1% profit

# ============================================================
# STRATEGY PARAMETERS
# ============================================================
STRATEGY_PARAMS = {
    "scalp_momentum": {
        "rsi_period": 7,
        "rsi_oversold": 25,
        "rsi_overbought": 75,
        "ema_fast": 9,
        "ema_slow": 21,
        "volume_threshold": 1.5,     # Volume must be 1.5x average
        "take_profit_pct": 0.015,    # 1.5% TP
        "stop_loss_pct": 0.007,      # 0.7% SL (2:1 RR)
        "timeframe": "5m",
    },
    "breakout_volume": {
        "lookback_period": 20,
        "volume_surge_mult": 2.0,    # Volume must be 2x average
        "atr_period": 14,
        "atr_multiplier_sl": 1.5,
        "atr_multiplier_tp": 3.0,    # 2:1 RR via ATR
        "min_consolidation_bars": 10,
        "timeframe": "15m",
    },
    "trend_follow": {
        "ema_fast": 12,
        "ema_mid": 26,
        "ema_slow": 50,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "adx_period": 14,
        "adx_threshold": 25,
        "take_profit_pct": 0.04,     # 4% TP
        "stop_loss_pct": 0.015,      # 1.5% SL
        "timeframe": "1h",
    },
    "mean_revert": {
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "take_profit_pct": 0.02,     # 2% TP
        "stop_loss_pct": 0.01,       # 1% SL
        "timeframe": "15m",
    },
    "swing": {
        "ema_fast": 20,
        "ema_slow": 50,
        "rsi_period": 14,
        "support_resistance_lookback": 50,
        "take_profit_pct": 0.06,     # 6% TP
        "stop_loss_pct": 0.025,      # 2.5% SL
        "timeframe": "4h",
    },
}

# ============================================================
# WEBHOOK / TRADINGVIEW
# ============================================================
WEBHOOK_HOST = "0.0.0.0"
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me_to_random_string")

# ============================================================
# LOGGING
# ============================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "trading_bot.log"
TRADE_LOG_FILE = "trades.csv"
