"""Full-history reads and range-independent moving averages."""
from datetime import datetime
import os
from pathlib import Path
import re

import numpy as np
import pandas as pd

from trading_analysis.common.indicators import macd, rsi_wilder
from trading_analysis.data.akshare_provider import AkShareProvider, DataUnavailable, TZ, normalize_ohlcv

PERIODS = (5, 10, 20, 30, 60, 120)
KINDS = {"股票（A股）": "stock_zh_a_hist", "指数": "index_zh_a_hist",
         "基金（ETF）": "fund_etf_hist_em", "基金（LOF）": "fund_lof_hist_em",
         "基金（场外）": "fund_open_fund_info_em"}


def load_history(symbol, kind, adjust="", provider=None):
    symbol = symbol.strip()
    if not re.fullmatch(r"\d{6}", symbol):
        raise ValueError("请输入六位代码，例如 600519、000300、510300 或 050025。")
    if kind not in KINDS or adjust not in ("", "qfq", "hfq"):
        raise ValueError("不支持的标的类型或复权方式。")
    nav = kind == "基金（场外）"
    if adjust and (nav or kind == "指数"):
        raise ValueError("指数和场外基金不支持复权选择。")
    params = {"symbol": symbol}
    if nav:
        params.update(indicator="单位净值走势", period="成立来")
    else:
        params.update(period="daily", start_date="19000101",
                      end_date=datetime.now(TZ).strftime("%Y%m%d"))
        if kind != "指数":
            params["adjust"] = adjust
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "my-trading-policy" / "dashboard"
    provider = provider or AkShareProvider(cache_dir=cache_dir, timeout_seconds=60)
    bundle = provider._read(KINDS[kind], params)
    raw = bundle.frame.rename(columns={"净值日期": "date", "单位净值": "close"})
    frame = normalize_ohlcv(raw)
    columns = ["close"] if nav else ["open", "high", "low", "close"]
    if frame.empty or any(c not in frame for c in columns):
        raise DataUnavailable("数据源未返回完整价格数据，请检查代码及标的类型。")
    if frame.date.isna().any() or frame.date.duplicated().any():
        raise DataUnavailable("数据源返回缺失或重复日期。")
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all():
        raise DataUnavailable("数据源返回无效价格。")
    if not nav and ((frame.high < frame[columns].max(axis=1)).any()
                    or (frame.low > frame[columns].min(axis=1)).any()):
        raise DataUnavailable("数据源返回不一致的日 K 价格。")
    bundle.frame = add_averages(frame)
    macd_values = macd(bundle.frame.close)
    bundle.frame[macd_values.columns] = macd_values
    bundle.frame["rsi14"] = rsi_wilder(bundle.frame.close)
    bundle.metadata.update(symbol=symbol, kind=kind, nav=nav,
                           price_adjustment=adjust or "none")
    return bundle


def add_averages(frame):
    result = frame.sort_values("date").reset_index(drop=True).copy()
    for period in PERIODS:
        result[f"MA{period}"] = result.close.rolling(period, min_periods=period).mean()
    return result


def select_range(frame, years=None):
    """Calendar years ending at the latest available observation, inclusive."""
    if years is None or frame.empty:
        return frame.copy()
    if years not in (1, 5, 10):
        raise ValueError("范围必须是全部、1年、5年或10年。")
    return frame.loc[frame.date >= frame.date.max() - pd.DateOffset(years=years)].copy()
