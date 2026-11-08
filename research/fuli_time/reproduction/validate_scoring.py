"""Run the frozen score diagnostic; never refit on November holdout labels."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from trading_analysis.studies.dividend_low_vol.analysis import compute_indicators
from trading_analysis.studies.dividend_low_vol.scoring import (
    FEATURES, LOW, HIGH, MODEL_VERSION, TRAINED_THROUGH,
    historical_conditional_returns, observed_grade_proxy, predict_proxy_score,
)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/fuli_time_reproduction"
OUT.mkdir(parents=True, exist_ok=True)
archive = pd.read_csv(ROOT / "outputs/fuli_time_archive/daily_indicators.csv")
columns = {"日期":"date", "开盘":"open", "最高":"high", "最低":"low", "收盘":"close", "成交量":"volume"}
raw = pd.read_csv(ROOT / "data/raw/512890_daily_em_none.csv").rename(columns=columns)
adjusted = pd.read_csv(ROOT / "data/raw/512890_daily_em_qfq.csv").rename(columns=columns)
calculated = compute_indicators(raw).set_index("date")
minute_validation = pd.read_csv(OUT / "technical_validation.csv")
minute_validation = minute_validation.loc[(minute_validation["mode"] == "independent_1130") & minute_validation.metric.isin(FEATURES)]
if minute_validation.uses_author_input.astype(str).str.lower().eq("true").any():
    raise ValueError("Independent score validation cannot consume author-supplied feature values")
minute_features = minute_validation.pivot(index="date",columns="metric",values="calculated")
rows = []
for source in archive.to_dict("records"):
    day = source["date"]
    modes = [
        ("published_indicator_conditioned", source),
        ("independent_akshare_eod_not_midday", calculated.loc[pd.Timestamp(day)]),
    ]
    if day in minute_features.index:
        modes.append(("independent_akshare_1130", minute_features.loc[day]))
    for mode, features in modes:
        result = predict_proxy_score(features)
        predicted = result["metrics"]["score_proxy"]
        rows.append({"date":day, "mode":mode, "split":"train" if day<=TRAINED_THROUGH else "holdout",
            "uses_author_input":mode=="published_indicator_conditioned",
            "observed_score":source["score_precise"], "score_proxy":predicted,
            "error":predicted-source["score_precise"], "absolute_error":abs(predicted-source["score_precise"]),
            "observed_grade":source["score_grade"], "grade_proxy":result["metrics"]["grade_proxy"],
            "observed_action":source["score_action_text"], "action_proxy":result["metrics"]["action_proxy"],
            "action_proxy_candidate":result["metrics"]["action_proxy_candidate"],
            "status":result["status"], "domain_warnings":";".join(result["domain_warnings"]),
            "input_timing":"published 11:30 indicators" if mode.startswith("published") else "real AkShare morning-only OHLCV at 11:30" if mode.endswith("1130") else "real full-day close; incompatible with 11:30 reference",
            "source_url":source["source_url"]})
validation = pd.DataFrame(rows)
validation.to_csv(OUT / "score_validation.csv", index=False, encoding="utf-8-sig")
summaries = []
for (mode, split), group in validation.groupby(["mode", "split"]):
    summaries.append({"mode":mode,"split":split,"n":len(group),"mae":float(group.absolute_error.mean()),
        "max_absolute_error":float(group.absolute_error.max()),
        "grade_accuracy":float((group.grade_proxy==group.observed_grade).mean()),
        "candidate_action_accuracy":float((group.action_proxy_candidate==group.observed_action).mean()),
        "action_abstentions":int(group.action_proxy.isna().sum()),
        "same_timing_independent_validation":mode=="independent_akshare_1130"})

stats_rows = []
for source in archive.loc[archive.date > TRAINED_THROUGH].to_dict("records"):
    # Conditional on published indicator inputs isolates the statistical reconstruction
    # from quote-time differences. Returns still come solely from real AkShare qfq data.
    score = predict_proxy_score(source)["metrics"]["score_proxy"]
    report = historical_conditional_returns(raw, adjusted, as_of=source["date"], current_score=score,
                                             return_adjustment="qfq")
    record = {"date":source["date"], "score_proxy":score, "status":report["status"],
              "is_original_backtest":False, "score_input":"published_indicator_conditioned",
              **report["metrics"], "observed_same_score_samples":source["same_score_samples"],
              "observed_forward_60d_mean_pct":source["forward_60d_mean_pct"]}
    record["mean_absolute_error_pp"] = abs(record["forward_60d_mean_pct_proxy"]-source["forward_60d_mean_pct"]) if record["forward_60d_mean_pct_proxy"] is not None else None
    stats_rows.append(record)
    (OUT / f"proxy_conditional_returns_{source['date']}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
pd.DataFrame(stats_rows).to_csv(OUT / "proxy_return_statistics_comparison.csv",index=False,encoding="utf-8-sig")
findings = {
    "model_version":MODEL_VERSION, "original_algorithm_identified":False,
    "frozen_training_end":TRAINED_THROUGH, "training_dates":34, "holdout_dates":5,
    "features":list(FEATURES), "observed_feature_min":LOW.tolist(), "observed_feature_max":HIGH.tolist(),
    "selection":{"criterion":"lowest expanding-window score MAE on training dates only",
        "folds":"train first 18/22/26/30 dates, validate next 4 each",
        "features":list(FEATURES), "transform":"logit", "degree":1,"ridge":.01,
        "train_cv_mae":.6291958768124798,"train_cv_max_error":1.6221471029789285,
        "audit_note":"Initial two-feature baselines also received one holdout diagnostic; candidate selection did not use those holdout results."},
    "validation":summaries,
    "grade_observation":{"actual_grade_matches_20point_bins":int(sum(observed_grade_proxy(s)==g for s,g in zip(archive.score_precise,archive.score_grade))),
        "n":39,"status":"inferred_from_observed_outputs_not_recovered_code",
        "thresholds_hypothesis":[20,40,60,80],"unobserved_boundary":80,
        "printed_legend_thresholds":[25,40,55,70],
        "unresolved":"Observed scores do not tightly identify exact boundaries; the 20-point hypothesis fits all samples."},
    "actions":{"hypothesis_thresholds":[30,45,55,70],"score80plus_action":None,
        "n":39,"note":"Action boundaries are inferred within gaps; predicted actions are withheld when ±5 score band crosses one."},
    "conditional_returns":{"implemented":True,"source":"real AkShare 512890 qfq returns",
        "original_statistics_reproduced":False,"point_in_time_label_guard":"end strictly before report date",
        "adjustment_evidence":{"published_distinct_extremes":16,"qfq_matches_display_precision":15,
            "raw_matches_display_precision":8,"unmatched_extreme_pct":-6.98,
            "status":"strong_support_for_qfq_60session_returns_not_proof_of_sample_membership",
            "evidence_file":"research/fuli_time/reproduction/return_extreme_identity.json"},
        "construction":"apply frozen proxy retrospectively, same 10-point score bin, only complete 60-session returns; default drop out-of-domain features",
        "comparison":stats_rows},
    "crowding":{"original_formula_identified":False,"reason":"Image names A-share capital concentration but does not publish numerator, denominator, universe or lookback; no OHLC-only proxy is labelled as original crowding."},
    "limits":["Published-input score error does not include errors of independently fetched market indicators.",
        "Independent 11:30 validation uses calculated values from technical_validation.csv; published column is not a feature input.",
        "Five holdout dates are a narrow sample; tomorrow may enter a new regime.",
        "Historical distributions have different sample counts/returns from author; not accepted as original reconstruction.",
        "No frozen author-return histogram or date lookup is used to make forecasts."]}
(ROOT / "research/fuli_time/reproduction/score_findings.json").write_text(json.dumps(findings,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"score_validation":summaries,"return_comparison":stats_rows},ensure_ascii=False,indent=2))
