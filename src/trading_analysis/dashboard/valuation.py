"""Type-specific valuation with explicit source dates and no stale/as-of price mixing."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import os

import numpy as np
import pandas as pd

from trading_analysis.data.akshare_provider import AkShareProvider, DataUnavailable, TZ

PE = "PE（TTM）"
PB = "PB"
DIVIDEND = "股息率"
CSI_PE = "PE（中证口径）"
PREMIUM = "折溢价率（日终）"
INDEX_NAMES = {
    "000016": "上证50", "000300": "沪深300", "000009": "上证380",
    "399673": "创业板50", "000905": "中证500", "000010": "上证180",
    "399324": "深证红利", "399330": "深证100", "000852": "中证1000",
    "000015": "上证红利", "000903": "中证100", "000906": "中证800",
}


@dataclass
class Valuation:
    metric: str
    frame: pd.DataFrame  # date, value; may retain calculation inputs
    unit: str
    formula: str
    note: str
    sources: list[dict] = field(default_factory=list)


def valuation_options(symbol, kind):
    if kind == "股票（A股）":
        return [PE, PB, DIVIDEND]
    if kind == "指数":
        return [PE, PB, DIVIDEND] if symbol in INDEX_NAMES else [CSI_PE, DIVIDEND]
    if kind in ("基金（ETF）", "基金（LOF）"):
        return [PREMIUM]
    return []


def read_source(api, params):
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "my-trading-policy" / "valuation"
    return AkShareProvider(cache_dir=cache, timeout_seconds=30)._read(
        api, params, allow_empty=api == "stock_history_dividend_detail")


def dated(frame, date_column):
    result = frame.rename(columns={date_column: "date"}).copy()
    if "date" not in result:
        raise DataUnavailable("数据源未提供日期。")
    result["date"] = pd.to_datetime(result.date, errors="coerce")
    if result.date.dt.tz is not None:
        result["date"] = result.date.dt.tz_convert(TZ).dt.tz_localize(None)
    result["date"] = result.date.dt.normalize()
    if result.date.isna().any() or result.date.duplicated().any():
        raise DataUnavailable("数据源存在缺失或重复日期，无法确认估值口径。")
    return result.sort_values("date").reset_index(drop=True)


def values(frame, date_column, value_column, *, allow_zero=False):
    result = dated(frame, date_column)
    if value_column not in result:
        raise DataUnavailable(f"数据源未提供 {value_column}。")
    numeric = pd.to_numeric(result[value_column], errors="coerce")
    valid = np.isfinite(numeric) & (numeric.ge(0) if allow_zero else numeric.gt(0))
    result["value"] = numeric.where(valid)
    return result[["date", "value"]]


def dividend_history(prices, dividends, rights):
    """Tax-before trailing cash dividends per share / contemporaneous raw price.

    Corporate-action windows are left missing instead of guessing share conversion.
    Empty upstream tables explicitly mean no recorded distributions/rights issues.
    """
    result = dated(prices, "数据日期")[["date", "当日收盘价"]].rename(columns={"当日收盘价": "price"})
    price = pd.to_numeric(result.price, errors="coerce")
    cash = np.zeros(len(result))
    unsafe = np.zeros(len(result), dtype=bool)
    dates = result.date
    # Full trailing calendar year, (t - 1 year, t]; include only implemented events.
    cutoff = dates - pd.DateOffset(years=1)
    if not dividends.empty:
        required = {"进度", "除权除息日", "公告日期", "派息", "送股", "转增"}
        if not required.issubset(dividends):
            raise DataUnavailable("分红数据字段不完整。")
        if dividends.duplicated(subset=sorted(required)).any():
            raise DataUnavailable("分红记录重复，不能重复计入派息。")
        for _, event in dividends.loc[dividends["进度"] == "实施"].iterrows():
            ex_date = pd.to_datetime(event["除权除息日"], errors="coerce")
            announcement = pd.to_datetime(event["公告日期"], errors="coerce")
            if pd.isna(ex_date) or pd.isna(announcement) or announcement > ex_date:
                raise DataUnavailable("已实施分红的公告/除息日期不完整或不一致。")
            applies = (dates >= ex_date) & (cutoff < ex_date)
            numbers = pd.to_numeric(event[["派息", "送股", "转增"]], errors="coerce")
            if not np.isfinite(numbers).all() or (numbers < 0).any():
                unsafe |= applies.to_numpy()
                continue
            cash += applies.to_numpy() * float(numbers["派息"]) / 10
            if numbers["送股"] or numbers["转增"]:
                unsafe |= applies.to_numpy()
    if not rights.empty:
        if "除权日" not in rights:
            raise DataUnavailable("配股数据缺少除权日，不能核对每股分红口径。")
        for ex_date in pd.to_datetime(rights["除权日"], errors="coerce"):
            if pd.isna(ex_date):
                raise DataUnavailable("配股除权日缺失，不能核对每股分红口径。")
            unsafe |= ((dates >= ex_date) & (cutoff < ex_date)).to_numpy()
    result["cash_dividend_12m"] = cash
    result["value"] = (cash / price * 100).where(np.isfinite(price) & price.gt(0) & ~unsafe)
    return result


def premium_history(prices, navs, *, today=None):
    today = pd.Timestamp(today or datetime.now(TZ).date()).normalize()
    price = dated(prices, "日期")[["date", "收盘"]].rename(columns={"收盘": "price"})
    nav = dated(navs, "净值日期")[["date", "单位净值"]].rename(columns={"单位净值": "nav"})
    # Exact same-date join only; never forward-fill NAV or use adjusted prices.
    result = price.loc[price.date < today].merge(nav, on="date", how="inner", validate="one_to_one")
    for col in ("price", "nav"):
        result[col] = pd.to_numeric(result[col], errors="coerce")
    valid = np.isfinite(result[["price", "nav"]]).all(axis=1) & result.price.gt(0) & result.nav.gt(0)
    result["value"] = ((result.price / result.nav - 1) * 100).where(valid)
    if result.empty:
        raise DataUnavailable("未取得同一天的收盘价与单位净值，无法计算日终折溢价。")
    return result


def load_valuation(symbol, kind, metric, *, reader=read_source):
    if metric not in valuation_options(symbol, kind):
        raise ValueError("该标的类型不适用此估值指标。")
    sources = []

    def read(api, **params):
        bundle = reader(api, params)
        sources.append(bundle.metadata)
        return bundle.frame

    if kind == "股票（A股）":
        raw = read("stock_value_em", symbol=symbol)
        if metric in (PE, PB):
            column = "PE(TTM)" if metric == PE else "市净率"
            frame = values(raw, "数据日期", column)
            formula = "股价 ÷ 最近四季度每股收益" if metric == PE else "股价 ÷ 最近报告期每股净资产"
            note = "东方财富历史估值；使用源提供的 TTM / MRQ 口径。非正值或缺失值不参与历史分位。"
        else:
            dividends = read("stock_history_dividend_detail", symbol=symbol, indicator="分红")
            rights = read("stock_history_dividend_detail", symbol=symbol, indicator="配股")
            frame = dividend_history(raw, dividends, rights)
            formula = "近12个月已实施的税前每股现金分红合计 ÷ 当日未复权价格 × 100%"
            note = "按除息日计入，新浪每10股派息金额除以10。窗口内有送转股、配股或字段不全时留空，不估算股本换算。"
    elif kind == "指数":
        if metric in (PE, PB):
            api = "stock_index_pe_lg" if metric == PE else "stock_index_pb_lg"
            column = "滚动市盈率" if metric == PE else "市净率"
            frame = values(read(api, symbol=INDEX_NAMES[symbol]), "日期", column)
            formula = "乐咕乐股公布的指数滚动市盈率（整体法）" if metric == PE else "乐咕乐股公布的指数市净率（整体法）"
            note = "使用整体法序列，不与等权或中位数口径混用；上游可能稀疏或不等频采样。分位是源返回观测的排名，不代表全部交易日排名，不插值成日频。"
        else:
            raw = read("stock_zh_index_value_csindex", symbol=symbol)
            if "指数代码" not in raw or not raw["指数代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6).eq(symbol).all():
                raise DataUnavailable("返回的指数代码与查询不一致。")
            column = "市盈率1" if metric == CSI_PE else "股息率1"
            frame = values(raw, "日期", column, allow_zero=metric == DIVIDEND)
            formula = f"中证指数公布的{column}（总股本加权口径）"
            note = "中证接口仅提供近期记录，通常不足以计算长期历史分位；与其他平台或调整股本口径可能不同。"
    else:
        end = datetime.now(TZ).strftime("%Y%m%d")
        api = "fund_etf_hist_em" if kind == "基金（ETF）" else "fund_lof_hist_em"
        raw = read(api, symbol=symbol, period="daily", start_date="19000101", end_date=end, adjust="")
        nav = read("fund_open_fund_info_em", symbol=symbol, indicator="单位净值走势", period="成立来")
        frame = premium_history(raw, nav)
        formula = "（同日未复权收盘价 ÷ 同日单位净值 − 1）× 100%"
        note = "正数为溢价、负数为折价；仅匹配已完成交易日，不含当日，不是盘中 IOPV 折溢价。黄金 ETF 的折溢价不代表黄金本身的高估或低估。"
    if frame.empty:
        raise DataUnavailable("数据源未返回估值记录。")
    if frame.date.max() > pd.Timestamp(datetime.now(TZ).date()):
        raise DataUnavailable("数据源返回了未来日期，暂不展示。")
    unit = "%" if metric in (DIVIDEND, PREMIUM) else "倍"
    return Valuation(metric, frame, unit, formula, note, sources)


def historical_percentile(frame, years=5):
    """Rank latest valid economic observation against a covered calendar window.

    Do not replace an invalid latest observation with a stale earlier value.
    A one-month start tolerance accommodates weekly/month-end publication dates.
    """
    if years not in (1, 3, 5, 10):
        raise ValueError("历史分位窗口必须为1、3、5或10年。")
    latest = frame.iloc[-1]
    cutoff = latest.date - pd.DateOffset(years=years)
    window = frame.loc[frame.date >= cutoff]
    valid = window.loc[np.isfinite(window.value)]
    result = {"value": None, "count": len(valid), "start": valid.date.min(),
              "constant": valid.value.nunique() <= 1,
              "end": latest.date, "years": years, "reason": ""}
    if not np.isfinite(latest.value):
        result["reason"] = "最近记录无有效估值，不以更早数值代替。"
    elif len(valid) < 30 or valid.date.min() > cutoff + pd.Timedelta(days=31):
        result["reason"] = f"有效历史不足{years}年或少于30个样本，暂不计算分位。"
    elif valid.date.diff().max() > pd.Timedelta(days=120):
        result["reason"] = "有效历史存在超过120天的缺口，暂不计算分位。"
    else:
        result["value"] = float(valid.value.le(latest.value).mean() * 100)
    return result


def valuation_position(metric, percentile):
    if percentile is None:
        return ""
    cheap = percentile >= 80 if metric == DIVIDEND else percentile <= 20
    expensive = percentile <= 20 if metric == DIVIDEND else percentile >= 80
    return "相对历史估值偏低" if cheap else "相对历史估值偏高" if expensive else "历史估值中间区间"
