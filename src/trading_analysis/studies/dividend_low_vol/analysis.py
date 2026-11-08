"""公开公式的透明实现。

这是公开指标的研究实现，不声称等同于原作者的行情口径、综合评分或交易策略。
算法默认值及未公开细节见同目录 README.md。
"""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorConfig:
    """显式记录无法由图片唯一确定的参数，便于以后逐项校准。"""

    price_position_window: int = 252
    bollinger_std_multiple: float = 2.0
    std_ddof: int = 1
    annualization_days: int = 252
    kdj_seed: float = 50.0
    price_position_basis: str = "ohlc"
    volume_numerator_window: int = 1

    def __post_init__(self) -> None:
        for name in ("price_position_window", "annualization_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 2:
                raise ValueError(f"{name} must be an integer >= 2")
        if self.std_ddof not in (0, 1):
            raise ValueError("std_ddof must be 0 or 1")
        if not math.isfinite(self.bollinger_std_multiple) or self.bollinger_std_multiple <= 0:
            raise ValueError("bollinger_std_multiple must be finite and positive")
        if not math.isfinite(self.kdj_seed) or not 0 <= self.kdj_seed <= 100:
            raise ValueError("kdj_seed must be between 0 and 100")
        if self.price_position_basis not in ("ohlc", "close"):
            raise ValueError("price_position_basis must be 'ohlc' or 'close'")
        if (isinstance(self.volume_numerator_window, bool)
                or not isinstance(self.volume_numerator_window, int)
                or not 1 <= self.volume_numerator_window <= 20):
            raise ValueError("volume_numerator_window must be an integer in [1, 20]")


def calibrated_config() -> IndicatorConfig:
    """2026-09/10校准后固定的候选口径；11月2–6日仅作留出验证。

    52周收盘极值、MA5量/MA20量、年化250均为数据支持的推断，
    其中后两者与图中文字口径不同。252日窗口长度本身未唯一识别。
    此函数只返回固定参数，不读取作者档案，也不查表返回指标。
    """
    return IndicatorConfig(price_position_basis="close", volume_numerator_window=5,
                           annualization_days=250)


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def grade_score(score: float) -> str:
    """仅对已有评分分档，不计算或推断原作者评分；边界采用左闭右开。"""
    score = _finite(score, "score")
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    return ("E", "D", "C", "B", "A")[sum(score >= x for x in (25, 40, 55, 70))]


def yield_spread(dividend_yield_pct: float, treasury_yield_pct: float) -> float:
    """输入为百分数数值，例如 4.70 与 1.60；输出 3.10 个百分点。"""
    return _finite(dividend_yield_pct, "dividend_yield_pct") - _finite(
        treasury_yield_pct, "treasury_yield_pct"
    )


def indicator_band(indicator: str, value: float) -> str:
    """图片中的区间名称；精确阈值处的归属是本实现的显式约定。"""
    bands = {
        "rsi14": ((30, 50, 70, 80), ("超卖", "接近超卖", "中性", "接近超买", "超买")),
        "ma250_bias_pct": ((-3, 0, 5, 10, 15), ("远低于年线", "低于年线", "贴近年线", "略高于年线", "高于年线", "远高于年线")),
        "kdj_j": ((0, 20, 80, 100), ("极度超卖", "超卖", "中性", "超买", "极度超买")),
        "yield_spread_pp": ((1, 2, 3, 4), ("极不划算", "偏不划算", "中性", "划算", "极划算")),
    }
    if indicator not in bands:
        raise ValueError(f"Unknown indicator: {indicator}")
    value = _finite(value, indicator)
    thresholds, labels = bands[indicator]
    return labels[sum(value >= threshold for threshold in thresholds)]


def _validated_prices(prices: pd.DataFrame) -> pd.DataFrame:
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = set(required) - set(prices.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if prices.empty:
        raise ValueError("prices is empty")
    df = prices.loc[:, required].copy().reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    if df["date"].isna().any() or df["date"].duplicated().any():
        raise ValueError("Dates must be present and unique")
    if not df["date"].is_monotonic_increasing:
        raise ValueError("Dates must be sorted in ascending order")
    for column in required[1:]:
        df[column] = pd.to_numeric(df[column], errors="raise").astype(float)
    if not np.isfinite(df[required[1:]].to_numpy()).all():
        raise ValueError("OHLCV must contain only finite numbers")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (df["volume"] < 0).any():
        raise ValueError("Volume must be nonnegative")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("High is below another OHLC price")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Low is above another OHLC price")
    return df


def _rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """先用 period 个涨跌幅的简单均值初始化，然后 Wilder 递推。"""
    delta = close.diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    result = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) <= period:
        return result
    avg_gain, avg_loss = gains.iloc[1:period + 1].mean(), losses.iloc[1:period + 1].mean()
    for i in range(period, len(close)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains.iloc[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses.iloc[i]) / period
        # 平价且从未涨跌时 RSI 不可定义，保留 NaN。
        if avg_gain + avg_loss > 0:
            result.iloc[i] = 100 * avg_gain / (avg_gain + avg_loss)
    return result


def _kdj(df: pd.DataFrame, seed: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    low, high = df["low"].rolling(9).min(), df["high"].rolling(9).max()
    rsv = 100 * (df["close"] - low) / (high - low).replace(0, np.nan)
    k, d = pd.Series(np.nan, index=df.index), pd.Series(np.nan, index=df.index)
    previous_k = previous_d = seed
    for i, value in enumerate(rsv):
        if pd.notna(value):
            previous_k = (2 * previous_k + value) / 3
            previous_d = (2 * previous_d + previous_k) / 3
            k.iloc[i], d.iloc[i] = previous_k, previous_d
    return k, d, 3 * k - 2 * d


def compute_indicators(prices: pd.DataFrame, config: IndicatorConfig | None = None) -> pd.DataFrame:
    """在按日期递增的日 OHLCV 上计算指标，返回行情和指标列。

    不联网，不估填缺失输入，不回填预热期，不输出综合评分或交易指令。
    不将收盘数据声称为原作者的午间快照；调用者负责标的及复权口径。
    """
    config = config or IndicatorConfig()
    df = _validated_prices(prices)
    close = df["close"]
    returns = close.pct_change(fill_method=None)
    df["daily_return_pct"] = returns * 100
    df["ma5"] = close.rolling(5).mean()
    df["ma20"] = close.rolling(20).mean()
    df["ma250"] = close.rolling(250).mean()
    df["ma250_bias_pct"] = (close / df["ma250"] - 1) * 100
    df["rsi14"] = _rsi_wilder(close)
    # MACD(12,26,9): recursive EMA seeded with the first close; DEA starts at 0.
    # Publish only after 34 observations, without backfilling the warm-up period.
    dif = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    warmed = np.arange(len(df)) >= 33
    df["macd_dif"] = dif.where(warmed)
    df["macd_dea"] = dea.where(warmed)
    df["macd_histogram"] = (2 * (dif - dea)).where(warmed)
    for days in (5, 10, 20):
        df[f"momentum_{days}d_pct"] = close.pct_change(days, fill_method=None) * 100
    df["kdj_k"], df["kdj_d"], df["kdj_j"] = _kdj(df, config.kdj_seed)
    df["volatility_20d_ann_pct"] = returns.rolling(20).std(ddof=config.std_ddof) * math.sqrt(config.annualization_days) * 100
    mean_volume = df["volume"].rolling(20).mean().replace(0, np.nan)
    df["volume_ratio_today_20d"] = df["volume"] / mean_volume
    df["volume_ratio_5d_20d"] = df["volume"].rolling(5).mean() / mean_volume
    df["volume_ratio_20d"] = df["volume"].rolling(config.volume_numerator_window).mean() / mean_volume
    mid = close.rolling(20).mean()
    half_width = config.bollinger_std_multiple * close.rolling(20).std(ddof=config.std_ddof)
    df["bollinger_20d_lower"] = mid - half_width
    df["bollinger_20d_upper"] = mid + half_width
    df["bollinger_20d_position_pct"] = 100 * (close - (mid - half_width)) / (2 * half_width).replace(0, np.nan)
    low_source = df["low"] if config.price_position_basis == "ohlc" else close
    high_source = df["high"] if config.price_position_basis == "ohlc" else close
    low = low_source.rolling(config.price_position_window).min()
    high = high_source.rolling(config.price_position_window).max()
    df["price_52w_low"] = low
    df["price_52w_high"] = high
    df["price_52w_position_pct"] = 100 * (close - low) / (high - low).replace(0, np.nan)
    streak = np.full(len(df), np.nan)
    current = 0
    for i in range(1, len(df)):
        direction = int(np.sign(close.iloc[i] - close.iloc[i - 1]))
        current = current + direction if direction and np.sign(current) == direction else direction
        streak[i] = current
    df["close_change_streak"] = streak
    df.attrs["reproduction_status"] = "partial_public_indicators_only"
    df.attrs["composite_score_available"] = False
    return df


def compute_weekly_indicators(prices: pd.DataFrame, *, as_of=None,
                              config: IndicatorConfig | None = None) -> pd.DataFrame:
    """按截止时刻可见日线聚合周K；当前周允许未完成，并明确标记。

    不先计算完整未来周再前向填充。若要复盘历史某天，必须传as_of或
    事先截断输入；本函数在聚合之前过滤，因此不会读到截止日之后行情。
    as_of只过滤交易日期，不能将已完成日K倒推成午间K；盘中调用者必须
    先以真实分钟数据构造当日部分K线。
    周K具体口径仅有9月14日一条J值可对照，不能称作已充分验证。
    """
    config = config or calibrated_config()
    daily = _validated_prices(prices)
    if as_of is not None:
        daily = daily[daily["date"] <= pd.Timestamp(as_of)].copy()
        if daily.empty:
            raise ValueError("No prices at or before as_of")
    daily["week_end"] = daily["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    weeks = daily.groupby("week_end", sort=True).agg(
        date=("date", "max"), open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
        observed_sessions=("date", "size"),
    ).reset_index()
    weeks["week_incomplete_by_calendar"] = weeks["date"] < weeks["week_end"]
    weeks["weekly_kdj_k"], weeks["weekly_kdj_d"], weeks["weekly_kdj_j"] = _kdj(weeks, config.kdj_seed)
    weeks["weekly_rsi14"] = _rsi_wilder(weeks["close"])
    weeks["weekly_ma5"] = weeks["close"].rolling(5).mean()
    weeks["weekly_ma20"] = weeks["close"].rolling(20).mean()
    half = config.bollinger_std_multiple * weeks["close"].rolling(20).std(ddof=config.std_ddof)
    weeks["weekly_bollinger_lower"] = weeks["weekly_ma20"] - half
    weeks["weekly_bollinger_upper"] = weeks["weekly_ma20"] + half
    weeks["weekly_bollinger_position_pct"] = 100 * (weeks["close"] - weeks["weekly_bollinger_lower"]) / (2 * half).replace(0, np.nan)
    weeks.attrs["as_of"] = str(daily["date"].iloc[-1])
    weeks.attrs["status"] = "candidate_weekly_formula_not_fully_validated"
    return weeks
