"""按时间划分的技术指标验证；作者档案只作标签或明确命名的输入诊断。

Run from repository root:
  .venv/bin/python -m trading_analysis.studies.dividend_low_vol.technical_validation
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import calibrated_config, compute_indicators, compute_weekly_indicators

ROOT = Path(__file__).resolve().parents[4]
HOLDOUT_START = pd.Timestamp("2026-11-02")
CN_COLUMNS = {"日期":"date", "时间":"time", "开盘":"open", "最高":"high",
              "最低":"low", "收盘":"close", "成交量":"volume"}
# Absolute tolerances, fixed to the displayed precision plus a small floating-point margin.
METRICS = {
    "price": ("close", .001, "source_price_unit_unknown"),
    "daily_return_pct": ("daily_return_pct", .01, "percentage_points"),
    "bias_250_pct": ("ma250_bias_pct", .01, "percentage_points"),
    "rsi14": ("rsi14", .10, "index_points"),
    "kdj_k": ("kdj_k", .10, "index_points"),
    "kdj_d": ("kdj_d", .10, "index_points"),
    "kdj_j": ("kdj_j", .10, "index_points"),
    "return_5d_pct": ("momentum_5d_pct", .01, "percentage_points"),
    "return_10d_pct": ("momentum_10d_pct", .01, "percentage_points"),
    "return_20d_pct": ("momentum_20d_pct", .01, "percentage_points"),
    "annualized_volatility_20d_pct": ("volatility_20d_ann_pct", .06, "percentage_points"),
    "bollinger_percent_b_pct": ("bollinger_20d_position_pct", .55, "percentage_points"),
    "position_52w_pct": ("price_52w_position_pct", .55, "percentage_points"),
    "volume_ratio": ("volume_ratio_20d", .01, "multiple"),
    "streak": ("close_change_streak", 0, "days"),
}


def read_daily(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path).rename(columns=CN_COLUMNS)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame[["date", "open", "high", "low", "close", "volume"]].sort_values("date").reset_index(drop=True)


def read_morning(path: Path, period: int) -> dict[pd.Timestamp, dict]:
    """Only complete 09:30/09:35–11:30 sessions; never use afternoon rows."""
    if not path.exists():
        return {}
    frame = pd.read_csv(path).rename(columns=CN_COLUMNS)
    frame["time"] = pd.to_datetime(frame["time"])
    frame = frame.sort_values("time")
    clock = frame["time"].dt.strftime("%H:%M")
    frame = frame[(clock >= "09:30") & (clock <= "11:30")].copy()
    result = {}
    for day, rows in frame.groupby(frame["time"].dt.normalize()):
        expected = 121 if period == 1 else 24
        if len(rows) != expected or rows["time"].iloc[-1].strftime("%H:%M") != "11:30":
            continue
        first = rows.iloc[0]
        # AkShare's 09:30 one-minute open is zero; its close is the observed auction price.
        opening = first["open"] if first["open"] > 0 else first["close"]
        result[day] = dict(date=day, open=float(opening), high=float(rows["high"].max()),
                           low=float(rows.loc[rows["low"] > 0, "low"].min()),
                           close=float(rows["close"].iloc[-1]), volume=float(rows["volume"].sum()),
                           period_minutes=period, bars=len(rows), snapshot_time="11:30",
                           source_file=str(path))
    return result


def _snapshot_history(daily, day, values):
    columns = ["date", "open", "high", "low", "close", "volume"]
    before = daily[daily["date"] < day].copy()
    return pd.concat([before, pd.DataFrame([{k:values[k] for k in columns}])], ignore_index=True)


def candidate_calibration(daily, observations, mornings):
    """Candidate scores use September/October only. Holdout values never enter selection."""
    train = observations[observations.date < HOLDOUT_START]
    errors = {}
    def add(name, error):
        errors.setdefault(name, []).append(float(error))
    for _, observed in train.iterrows():
        history = daily[daily.date <= observed.date].copy()
        # Price-dependent candidate comparison is explicitly an author-price diagnostic.
        history.loc[history.index[-1], "close"] = observed.price
        for basis in ["ohlc", "close"]:
            for window in [240, 250, 252, 260, 365]:
                part = history[history.date > observed.date-pd.Timedelta(days=365)] if window == 365 else history.tail(window)
                lo = part.low.min() if basis == "ohlc" else part.close.min()
                hi = part.high.max() if basis == "ohlc" else part.close.max()
                add(f"position/{basis}/{window}", 100*(observed.price-lo)/(hi-lo)-observed.position_52w_pct)
        for ddof in [0, 1]:
            close = history.close.tail(20)
            sd = close.std(ddof=ddof)
            add(f"bollinger/ddof{ddof}", 100*(observed.price-close.mean()+2*sd)/(4*sd)-observed.bollinger_percent_b_pct)
            for annual_days in [240, 244, 250, 252]:
                for returns_kind in ["simple", "log"]:
                    changes = history.close.pct_change(fill_method=None) if returns_kind == "simple" else np.log(history.close).diff()
                    pred = changes.tail(20).std(ddof=ddof)*np.sqrt(annual_days)*100
                    add(f"volatility/{returns_kind}/ddof{ddof}/annual{annual_days}", pred-observed.annualized_volatility_20d_pct)
        if observed.date in mornings:
            volume = history.volume.copy()
            volume.iloc[-1] = mornings[observed.date]["volume"]
            for short in [1, 3, 5, 10]:
                for long in [20, 60]:
                    for lag in [0, 1]:
                        values = volume if lag == 0 else volume.iloc[:-1]
                        add(f"volume/ma{short}/ma{long}/lag{lag}",values.tail(short).mean()/values.tail(long).mean()-observed.volume_ratio)
    return [{"candidate":name, "training_n":len(vals), "mae":float(np.mean(np.abs(vals))),
             "max_abs_error":float(np.max(np.abs(vals)))} for name,vals in sorted(errors.items())]


def run(daily_path: Path, archive_path: Path, minute5_path: Path, minute1_path: Path,
        output_dir: Path) -> dict:
    daily = read_daily(daily_path)
    observed = pd.read_csv(archive_path, parse_dates=["date"])
    morning5 = read_morning(minute5_path, 5)
    mornings = {**morning5, **read_morning(minute1_path, 1)}
    candidates = candidate_calibration(daily, observed, mornings)
    config = calibrated_config()
    records = []
    for _, target in observed.iterrows():
        day = target.date
        daily_prefix = daily[daily.date <= day].copy()
        if daily_prefix.empty or daily_prefix.date.iloc[-1] != day:
            continue
        assisted = daily_prefix.copy()
        assisted.loc[assisted.index[-1], "close"] = target.price
        assisted.loc[assisted.index[-1], "high"] = max(assisted.iloc[-1].high, target.price)
        assisted.loc[assisted.index[-1], "low"] = min(assisted.iloc[-1].low, target.price)
        modes = [
            ("independent_daily_close", daily_prefix, "15:00", "daily_ohlcv", False),
            ("author_price_diagnostic", assisted, "author_price_only", "author_price_plus_full_day_high_low_volume", True),
        ]
        if day in mornings:
            snapshot = mornings[day]
            modes.append(("independent_1130", _snapshot_history(daily, day, snapshot), "11:30",
                          f"akshare_{snapshot['period_minutes']}min_morning_ohlcv", False))
        for mode, frame, at, inputs, assisted_flag in modes:
            last = compute_indicators(frame, config).iloc[-1]
            for archive_key, (column, tolerance, unit) in METRICS.items():
                actual = target.get(archive_key)
                predicted = last[column]
                if pd.isna(actual) or pd.isna(predicted):
                    continue
                error = float(predicted-actual)
                records.append(dict(date=str(day.date()), split="holdout" if day >= HOLDOUT_START else "calibration",
                                    mode=mode, input_dependency=inputs, uses_author_input=assisted_flag,
                                    computed_at=at, metric=archive_key, calculated=float(predicted), published=float(actual),
                                    error=error, absolute_error=abs(error), absolute_tolerance=tolerance,
                                    within_tolerance=abs(error) <= tolerance+1e-12, unit=unit,
                                    source_url=target.source_url))
    result = pd.DataFrame(records)
    summaries = []
    for (mode, split, metric), rows in result.groupby(["mode", "split", "metric"]):
        summaries.append(dict(mode=mode, split=split, metric=metric, n=len(rows),
                              mae=float(rows.absolute_error.mean()), max_abs_error=float(rows.absolute_error.max()),
                              absolute_tolerance=float(rows.absolute_tolerance.iloc[0]),
                              passed=int(rows.within_tolerance.sum()), pass_rate=float(rows.within_tolerance.mean())))
    weekly_day = pd.Timestamp("2026-09-14")
    weekly_history = daily[daily.date <= weekly_day].copy()
    weekly_history.loc[weekly_history.index[-1], "close"] = 1.207
    weekly = compute_weekly_indicators(weekly_history, as_of=weekly_day, config=config).iloc[-1]
    report = {
        "config":asdict(config), "holdout_start":str(HOLDOUT_START.date()),
        "training_dates":int((observed.date < HOLDOUT_START).sum()), "holdout_dates":int((observed.date >= HOLDOUT_START).sum()), "independent_morning_dates":len({r['date'] for r in records if r['mode']=='independent_1130'}),
        "selection_rule":"Choose candidates by September/October mean absolute error only; all November 2–6 data excluded from selection.",
        "input_warning":"Author-price diagnostic uses a published target input and full-day high/low/volume: it is not an independent intraday validation. Daily close is also a mismatched-time diagnostic.",
        "inferences":[
            "52-week position uses rolling close extrema; all tested 240/250/252/260-session and 365-calendar-day windows tie in this sample. 252 sessions remains unidentifiable and explicit.",
            "Volume ratio fits MA5(volume)/MA20(volume), including morning cumulative volume, rather than the printed today-volume/20-day-mean definition.",
            "Annualized volatility fits 20 simple returns, sample standard deviation and sqrt(250), rather than the printed sqrt(252).",
            "Bollinger bands fit 20 closes, 2 sample standard deviations (ddof=1); Wilder RSI14 and recursive KDJ(9,3,3) supported.",
            "October 28–30 show material published-history/snapshot discrepancies across several metrics; retained as failures, never removed or overwritten.",
        ],
        "weekly_diagnostic":{"date":"2026-09-14", "author_price_input":1.207, "published_weekly_kdj_j":96.39,
                             "computed_weekly_kdj_j":float(weekly.weekly_kdj_j),
                             "absolute_error":abs(float(weekly.weekly_kdj_j)-96.39),
                             "status":"one_author_price_assisted_sample_only_not_independent_validation"},
        "candidates":candidates, "summary":summaries,
        "sources":[{"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in [daily_path,archive_path,minute5_path,minute1_path] if p.exists()],
    }
    output_dir.mkdir(parents=True,exist_ok=True)
    result.to_csv(output_dir/"technical_validation.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(summaries).to_csv(output_dir/"technical_summary.csv",index=False,encoding="utf-8-sig")
    (output_dir/"technical_validation_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    calibration_dir=ROOT/"research/fuli_time/reproduction";calibration_dir.mkdir(parents=True,exist_ok=True)
    (calibration_dir/"technical_calibration.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-file",type=Path,default=ROOT/"data/raw/512890_daily_em_none.csv")
    parser.add_argument("--archive-file",type=Path,default=ROOT/"outputs/fuli_time_archive/daily_indicators.csv")
    parser.add_argument("--minute5-file",type=Path,default=ROOT/"data/raw/dividend_low_vol/fund_etf_hist_min_em_5.csv")
    parser.add_argument("--minute1-file",type=Path,default=ROOT/"data/raw/dividend_low_vol/fund_etf_hist_min_em_1.csv")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"outputs/fuli_time_reproduction")
    args=parser.parse_args()
    result=run(args.daily_file,args.archive_file,args.minute5_file,args.minute1_file,args.output_dir)
    print(json.dumps({"independent_morning_dates":result['independent_morning_dates'],
                      "holdout":[s for s in result['summary'] if s['mode']=='independent_1130' and s['split']=='holdout']},ensure_ascii=False))


if __name__ == "__main__":
    main()
