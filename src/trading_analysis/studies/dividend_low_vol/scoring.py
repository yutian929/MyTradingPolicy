"""Frozen, explicitly approximate score model and independent conditional returns.

The author's 20+ feature/power-score model is not identified. This small surrogate
was fitted to published scores dated through 2026-10-30, selected only by expanding
validation inside that interval. It consumes calculated indicators, never a date
lookup or the current author's score. It is not an executable trading policy.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

import numpy as np
import pandas as pd

from .analysis import compute_indicators, grade_score

MODEL_VERSION = "published-score-surrogate-20261030-v1"
TRAINED_THROUGH = "2026-10-30"
FEATURES = ("rsi14", "bias_250_pct", "kdj_j", "bollinger_percent_b_pct")
ALIASES = {"bias_250_pct": "ma250_bias_pct", "bollinger_percent_b_pct": "bollinger_20d_position_pct"}
MEAN = np.array([56.932352941176475, 2.5594117647058825, 59.91764705882353, 64.55882352941177])
SCALE = np.array([7.097668241307692, 1.3372974089040894, 37.03563046412782, 28.87008545034175])
COEF = np.array([-0.31755112390976487, -0.13040376866119663, -0.5778962592278876, -0.06375395325981197, -0.1489175973722252])
LOW = np.array([45.5, .53, -2.6, 15.0])
HIGH = np.array([66.9, 4.93, 117.1, 102.0])
CONDITIONAL_ERROR_BAND = 5.0  # declared diagnostic tolerance, not a confidence interval


def _features(row: Mapping) -> tuple[np.ndarray, list[str]]:
    values, missing = [], []
    for key in FEATURES:
        raw = row.get(key, row.get(ALIASES.get(key, "")))
        try:
            value = float(raw)
        except (ValueError, TypeError):
            value = math.nan
        if not math.isfinite(value):
            missing.append(key)
        values.append(value)
    return np.array(values), missing


def _raw_prediction(values: np.ndarray) -> np.ndarray:
    z = COEF[0] + ((values - MEAN) / SCALE) @ COEF[1:]
    return 100 / (1 + np.exp(-np.clip(z, -700, 700)))


def observed_grade_proxy(score: float) -> str:
    """20-point bins fit all observed grades; the unobserved A boundary is assumed."""
    score = float(score)
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("score must be finite and in [0, 100]")
    return ("E", "D", "C", "B", "A")[sum(score >= t for t in (20, 40, 60, 80))]


def _action(score: float) -> str | None:
    # Cut points are hypotheses within gaps between observed values, not recovered code.
    if score < 30: return "减仓"
    if score < 45: return "谨慎买入"
    if score < 55: return "持有观望"
    if score < 70: return "可适当加仓"
    if score < 80: return "较好买入"
    return None  # No >=80 sample: do not invent the author's action.


def predict_proxy_score(indicators: Mapping, *, as_of: str | None = None) -> dict:
    """Estimate a score from freshly computed features, preserving uncertainty.

    The output is always named ``score_proxy``. A numerical extrapolation is shown
    for research, but actions are suppressed outside the observed input box and
    near action boundaries. An as_of before the model freeze date is rejected.
    """
    if as_of is not None and pd.Timestamp(as_of).date() <= pd.Timestamp(TRAINED_THROUGH).date():
        raise ValueError("Frozen surrogate was not available before 2026-10-31")
    values, missing = _features(indicators)
    base = {"model_version": MODEL_VERSION, "trained_through": TRAINED_THROUGH,
            "is_original_algorithm": False, "feature_names": list(FEATURES),
            "validation": {"kind": "independent_akshare_1130_holdout",
                "train_rows": 34, "holdout_dates": ["2026-11-02", "2026-11-06"],
                "holdout_rows": 5, "holdout_mae_points": 1.4026526929276375,
                "holdout_max_error_points": 3.6349694566164956,
                "declared_error_tolerance_points": CONDITIONAL_ERROR_BAND,
                "end_to_end_real_market_data_validated": True,
                "input_timing": "AkShare morning-only OHLCV through 11:30",
                "independent_calibration_dates": 22,
                "independent_calibration_max_error_points": 7.287677782989945,
                "all_independent_dates_within_tolerance": False,
                "conditional_published_input_holdout_mae": 1.4002582774244552},
            "assumptions": ["Original weights/features are undisclosed; this is a fitted surrogate.",
                "20-point actual grade bins fit observed outputs; A threshold 80 is unobserved.",
                "Action cut points 30/45/55/70 are inferred from sparse samples.",
                "Five-point error band is a declared tolerance, not a statistical confidence interval."]}
    if missing:
        return {**base, "status": "unavailable_missing_inputs", "missing_features": missing,
                "domain_warnings": [], "metrics": {"score_proxy": None, "score_original": None,
                "grade_proxy": None, "printed_legend_grade": None, "action_proxy": None}}
    score = float(_raw_prediction(values))
    outside = [key for key, value, lo, hi in zip(FEATURES, values, LOW, HIGH) if not lo <= value <= hi]
    warnings = ["outside_training_range:" + key for key in outside]
    low, high = max(0, score - CONDITIONAL_ERROR_BAND), min(100, score + CONDITIONAL_ERROR_BAND)
    action = _action(score)
    near = any(low <= t <= high for t in (30, 45, 55, 70, 80))
    if near: warnings.append("action_boundary_within_error_band")
    grade_near = any(low <= t <= high for t in (20, 40, 60, 80))
    if grade_near: warnings.append("grade_boundary_within_error_band")
    return {**base, "status": "experimental_extrapolation" if outside else "experimental_surrogate",
            "missing_features": [], "domain_warnings": warnings,
            "features": dict(zip(FEATURES, values.tolist())),
            "diagnostic_score_band": [low, high],
            "metrics": {"score_proxy": score, "score_original": None,
                "grade_proxy": observed_grade_proxy(score), "printed_legend_grade": grade_score(score),
                "action_proxy": None if outside or near else action,
                "action_proxy_candidate": action, "grade_proxy_uncertain": grade_near}}


def historical_conditional_returns(
    signal_prices: pd.DataFrame, return_prices: pd.DataFrame, *,
    as_of: str, current_score: float, return_adjustment: str,
    horizon: int = 60, bin_width: float = 10, include_extrapolated: bool = False,
) -> dict:
    """Independent retrospective same-score-bin statistics, with mature labels only.

    Signal OHLCV should follow the calibrated indicator convention (unadjusted).
    Returns MUST use a separately fetched qfq/hfq series; no raw-price return
    statistics are accepted across corporate actions. All rows on/after as_of's
    date are excluded, so future afternoon data cannot enter a morning report.
    This applies the currently frozen surrogate to historical observations. It is
    not a walk-forward strategy backtest or reproduction of the author's samples.
    """
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is not None: cutoff = cutoff.tz_localize(None)
    cutoff = cutoff.normalize()
    if cutoff.date() <= pd.Timestamp(TRAINED_THROUGH).date():
        raise ValueError("as_of must be after frozen model training cutoff")
    if return_adjustment not in {"qfq", "hfq"}:
        raise ValueError("Adjusted return prices are required (qfq/hfq)")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if not math.isfinite(float(bin_width)) or not 0 < bin_width <= 100:
        raise ValueError("bin_width must be in (0,100]")
    current_score = float(current_score)
    if not math.isfinite(current_score) or not 0 <= current_score <= 100:
        raise ValueError("current_score must be in [0,100]")
    def past(frame):
        out = frame.copy()
        out["date"] = pd.to_datetime(out["date"])
        if out.date.dt.tz is not None: out["date"] = out.date.dt.tz_localize(None)
        return out.loc[out.date < cutoff].reset_index(drop=True)
    signals, returns = past(signal_prices), past(return_prices)
    calculated = compute_indicators(signals)
    if returns.date.duplicated().any() or not returns.date.is_monotonic_increasing:
        raise ValueError("Return dates must be sorted and unique")
    if not calculated.date.equals(returns.date.reset_index(drop=True)):
        raise ValueError("Signal and adjusted-return sessions must match exactly")
    closes = pd.to_numeric(returns["close"], errors="raise").astype(float)
    if not np.isfinite(closes).all() or (closes <= 0).any():
        raise ValueError("Adjusted closes must be finite and positive")
    values = np.array([_features(row)[0] for _, row in calculated.iterrows()])
    scores = _raw_prediction(values)
    valid = np.isfinite(values).all(axis=1)
    in_domain = valid & ((values >= LOW) & (values <= HIGH)).all(axis=1)
    forward = (closes.shift(-horizon) / closes - 1) * 100
    ends = returns.date.shift(-horizon)
    lower = min(math.floor(current_score / bin_width) * bin_width, 100 - bin_width)
    upper = min(100.0, lower + bin_width)
    selected = valid & forward.notna().to_numpy() & (scores >= lower) & ((scores < upper) | ((upper == 100) & (scores <= 100)))
    if not include_extrapolated: selected &= in_domain
    samples = pd.DataFrame({"date": calculated.date, "score_proxy": scores,
                            "forward_return_pct": forward, "label_end_date": ends}).loc[selected]
    vals = samples.forward_return_pct.to_numpy()
    n = len(vals)
    stats = {"same_score_samples_proxy": n,
             **{f"forward_{horizon}d_{key}_pct_proxy": float(fn(vals)) if n else None
                for key, fn in [("mean", np.mean), ("median", np.median), ("min", np.min), ("max", np.max)]},
             "positive_return_ratio_pct_proxy": float(100 * (vals > 0).mean()) if n else None}
    bins = []
    if n:
        counts, edges = np.histogram(vals, bins=7)
        bins = [{"lower_pct": float(edges[i]), "upper_pct": float(edges[i+1]),
                 "count": int(count), "upper_inclusive": i == 6} for i, count in enumerate(counts)]
    records = [{"date": str(row.date.date()), "score_proxy": float(row.score_proxy),
                "forward_return_pct": float(row.forward_return_pct),
                "label_end_date": str(row.label_end_date.date())} for row in samples.itertuples()]
    return {"status": "independent_proxy_statistic" if n >= 30 else "independent_proxy_statistic_low_sample",
            "is_original_backtest": False, "is_walk_forward_backtest": False,
            "model_version": MODEL_VERSION, "as_of": str(cutoff.date()),
            "return_adjustment": return_adjustment, "horizon_sessions": horizon,
            "score_bin": {"lower": lower, "upper": upper, "upper_inclusive": upper == 100},
            "include_extrapolated_features": include_extrapolated,
            "historical_complete_feature_rows": int(valid.sum()), "historical_in_domain_rows": int(in_domain.sum()),
            "metrics": stats, "histogram": bins, "samples": records,
            "limitations": ["Fixed surrogate applied retrospectively; not original author scores.",
                "Only fully mature labels ending strictly before as_of are used.",
                "Overlapping observations; no execution, fees or portfolio accounting.",
                "Small calibration-domain support can materially reduce sample counts."]}
