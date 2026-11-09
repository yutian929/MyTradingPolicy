"""Shared price indicators; callers supply the full chronological history."""
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Seed with mean gains/losses over period changes, then Wilder smoothing."""
    delta = close.diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    result = pd.Series(float("nan"), index=close.index, dtype=float)
    if len(close) <= period:
        return result
    avg_gain, avg_loss = gains.iloc[1:period + 1].mean(), losses.iloc[1:period + 1].mean()
    for i in range(period, len(close)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains.iloc[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses.iloc[i]) / period
        # An entirely flat history has no defined gain/loss ratio; keep it missing.
        if avg_gain + avg_loss > 0:
            result.iloc[i] = 100 * avg_gain / (avg_gain + avg_loss)
    return result


def macd(close: pd.Series) -> pd.DataFrame:
    """MACD(12,26,9), first-close EMA seed, double histogram, 34-row warm-up."""
    dif = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    result = pd.DataFrame({"macd_dif": dif, "macd_dea": dea,
                           "macd_histogram": 2 * (dif - dea)})
    result.iloc[:33] = float("nan")
    return result
