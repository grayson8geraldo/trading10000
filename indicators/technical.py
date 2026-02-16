"""
Technical Analysis Indicators.
Optimized for crypto futures scalping and swing trading.
All functions are NaN-safe with division-by-zero protection.
"""

import numpy as np
import pandas as pd


def ohlcv_to_dataframe(ohlcv: list) -> pd.DataFrame:
    """Convert CCXT OHLCV data to a pandas DataFrame with validation."""
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    # Drop rows with any NaN in OHLCV
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    return df


def _safe_div(numerator, denominator, fill=0.0):
    """Safe division that handles zero denominators."""
    if isinstance(denominator, pd.Series):
        return numerator / denominator.replace(0, np.nan).fillna(fill)
    if denominator == 0:
        return fill
    return numerator / denominator


# ============================================================
# MOVING AVERAGES
# ============================================================

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def vwma(df: pd.DataFrame, period: int) -> pd.Series:
    """Volume Weighted Moving Average."""
    vol_sum = df["volume"].rolling(period).sum()
    return _safe_div((df["close"] * df["volume"]).rolling(period).sum(), vol_sum)


# ============================================================
# MOMENTUM INDICATORS
# ============================================================

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = _safe_div(avg_gain, avg_loss)
    return 100 - (100 / (1 + rs))


def stochastic_rsi(series: pd.Series, rsi_period: int = 14, stoch_period: int = 14,
                    k_period: int = 3, d_period: int = 3) -> tuple:
    """Stochastic RSI - K and D lines. Division-by-zero safe."""
    rsi_vals = rsi(series, rsi_period)
    rsi_min = rsi_vals.rolling(stoch_period).min()
    rsi_max = rsi_vals.rolling(stoch_period).max()
    denom = (rsi_max - rsi_min).replace(0, np.nan)
    stoch_rsi = ((rsi_vals - rsi_min) / denom).fillna(0.5)
    k = stoch_rsi.rolling(k_period).mean() * 100
    d = k.rolling(d_period).mean()
    return k, d


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD - Line, Signal, and Histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R. Division-by-zero safe."""
    highest_high = df["high"].rolling(period).max()
    lowest_low = df["low"].rolling(period).min()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    return ((-100 * (highest_high - df["close"])) / denom).fillna(-50)


# ============================================================
# VOLATILITY INDICATORS
# ============================================================

def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple:
    """Bollinger Bands - Upper, Middle, Lower."""
    middle = sma(series, period)
    std = series.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift(1))
    low_close = abs(df["low"] - df["close"].shift(1))
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


def keltner_channels(df: pd.DataFrame, ema_period: int = 20,
                      atr_period: int = 14, atr_mult: float = 2.0) -> tuple:
    """Keltner Channels."""
    middle = ema(df["close"], ema_period)
    atr_val = atr(df, atr_period)
    upper = middle + (atr_val * atr_mult)
    lower = middle - (atr_val * atr_mult)
    return upper, middle, lower


def squeeze_momentum(df: pd.DataFrame, bb_period: int = 20, bb_std: float = 2.0,
                      kc_period: int = 20, kc_mult: float = 1.5) -> tuple:
    """
    Squeeze Momentum Indicator (LazyBear style).
    Returns: (squeeze_on, momentum_values)
    squeeze_on: True when BB is inside KC (low volatility, potential breakout)
    """
    bb_upper, bb_mid, bb_lower = bollinger_bands(df["close"], bb_period, bb_std)
    kc_upper, kc_mid, kc_lower = keltner_channels(df, kc_period, kc_period, kc_mult)

    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

    # Momentum: linear regression of (close - average of HL midline)
    highest = df["high"].rolling(kc_period).max()
    lowest = df["low"].rolling(kc_period).min()
    m1 = (highest + lowest) / 2
    val = df["close"] - (m1 + kc_mid) / 2

    momentum = val.rolling(kc_period).mean()

    return squeeze_on, momentum


# ============================================================
# VOLUME INDICATORS
# ============================================================

def volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Volume Simple Moving Average."""
    return df["volume"].rolling(window=period).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direction = np.where(df["close"] > df["close"].shift(1), 1,
                np.where(df["close"] < df["close"].shift(1), -1, 0))
    return (df["volume"] * direction).cumsum()


def volume_profile(df: pd.DataFrame, bins: int = 50) -> pd.DataFrame:
    """Simple volume profile (volume at price levels)."""
    price_range = np.linspace(df["low"].min(), df["high"].max(), bins)
    vol_at_price = []
    for i in range(len(price_range) - 1):
        mask = (df["close"] >= price_range[i]) & (df["close"] < price_range[i+1])
        vol_at_price.append({
            "price": (price_range[i] + price_range[i+1]) / 2,
            "volume": df.loc[mask, "volume"].sum(),
        })
    return pd.DataFrame(vol_at_price)


def cvd(df: pd.DataFrame) -> pd.Series:
    """Cumulative Volume Delta (approximation using candle body)."""
    body_ratio = (df["close"] - df["open"]) / (df["high"] - df["low"]).replace(0, np.nan)
    body_ratio = body_ratio.fillna(0).clip(-1, 1)
    delta = df["volume"] * body_ratio
    return delta.cumsum()


# ============================================================
# TREND INDICATORS
# ============================================================

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index."""
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr_val = atr(df, period)

    plus_di = _safe_div(100 * ema(plus_dm, period), atr_val)
    minus_di = _safe_div(100 * ema(minus_dm, period), atr_val)

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = (100 * abs(plus_di - minus_di) / di_sum).fillna(0)
    adx_val = ema(dx, period)

    return adx_val


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> tuple:
    """
    Supertrend indicator.
    Returns: (supertrend_line, direction) where direction 1 = up, -1 = down
    """
    atr_val = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper_band = hl2 + (multiplier * atr_val)
    lower_band = hl2 - (multiplier * atr_val)

    supertrend_vals = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    if len(df) == 0:
        return supertrend_vals, direction

    supertrend_vals.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = 1

    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            supertrend_vals.iloc[i] = max(lower_band.iloc[i],
                                           supertrend_vals.iloc[i - 1] if direction.iloc[i - 1] == 1
                                           else lower_band.iloc[i])
        else:
            supertrend_vals.iloc[i] = min(upper_band.iloc[i],
                                           supertrend_vals.iloc[i - 1] if direction.iloc[i - 1] == -1
                                           else upper_band.iloc[i])

    return supertrend_vals, direction


# ============================================================
# SUPPORT & RESISTANCE
# ============================================================

def pivot_points(df: pd.DataFrame) -> dict:
    """Calculate classic pivot points from the last completed candle."""
    if len(df) < 2:
        return {"pivot": 0, "r1": 0, "r2": 0, "r3": 0, "s1": 0, "s2": 0, "s3": 0}

    h = df["high"].iloc[-2]
    l = df["low"].iloc[-2]
    c = df["close"].iloc[-2]

    pivot = (h + l + c) / 3
    r1 = 2 * pivot - l
    s1 = 2 * pivot - h
    r2 = pivot + (h - l)
    s2 = pivot - (h - l)
    r3 = h + 2 * (pivot - l)
    s3 = l - 2 * (h - pivot)

    return {"pivot": pivot, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}


def find_support_resistance(df: pd.DataFrame, lookback: int = 50, threshold: float = 0.002) -> tuple:
    """
    Find support and resistance levels based on price clustering.
    Returns: (support_levels, resistance_levels)
    """
    if len(df) < 3:
        return [], []

    recent = df.tail(lookback)
    highs = recent["high"].values
    lows = recent["low"].values
    close = df["close"].iloc[-1]

    levels = np.concatenate([highs, lows])
    levels.sort()

    if len(levels) == 0:
        return [], []

    clusters = []
    current_cluster = [levels[0]]

    for i in range(1, len(levels)):
        if current_cluster[-1] > 0 and abs(levels[i] - current_cluster[-1]) / current_cluster[-1] < threshold:
            current_cluster.append(levels[i])
        else:
            if len(current_cluster) >= 3:
                clusters.append(np.mean(current_cluster))
            current_cluster = [levels[i]]

    if len(current_cluster) >= 3:
        clusters.append(np.mean(current_cluster))

    support = [l for l in clusters if l < close]
    resistance = [l for l in clusters if l > close]

    return sorted(support, reverse=True)[:3], sorted(resistance)[:3]


# ============================================================
# COMPOSITE ANALYSIS
# ============================================================

def compute_all_indicators(df: pd.DataFrame, params: dict = None) -> pd.DataFrame:
    """
    Compute all relevant indicators and add them to the dataframe.
    This is the main function used by strategies.
    Includes ALL standard EMA periods so strategies can reference any of them.
    """
    if params is None:
        params = {}

    # EMAs — compute all commonly used periods
    for period in [9, 12, 20, 21, 26, 50, 200]:
        col = f"ema_{period}"
        if col not in df.columns:
            df[col] = ema(df["close"], period)

    # RSI
    df["rsi"] = rsi(df["close"], params.get("rsi_period", 14))
    df["rsi_7"] = rsi(df["close"], 7)

    # Stochastic RSI
    df["stoch_k"], df["stoch_d"] = stochastic_rsi(df["close"])

    # MACD
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(df["close"])

    # Bollinger Bands
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(df["close"])
    bb_denom = df["bb_mid"].replace(0, np.nan)
    df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / bb_denom).fillna(0)

    # ATR
    df["atr"] = atr(df)

    # Volume
    df["vol_sma"] = volume_sma(df)
    df["vol_ratio"] = _safe_div(df["volume"], df["vol_sma"])

    # OBV
    df["obv"] = obv(df)

    # ADX
    df["adx"] = adx(df)

    # Supertrend
    df["supertrend"], df["supertrend_dir"] = supertrend(df)

    # Williams %R
    df["williams_r"] = williams_r(df)

    # CVD
    df["cvd"] = cvd(df)

    # Squeeze
    df["squeeze_on"], df["squeeze_mom"] = squeeze_momentum(df)

    return df
