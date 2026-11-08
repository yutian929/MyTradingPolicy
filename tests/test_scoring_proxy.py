import unittest

import numpy as np
import pandas as pd

from trading_analysis.studies.dividend_low_vol.scoring import (
    historical_conditional_returns, predict_proxy_score, observed_grade_proxy,
)


class FrozenScoreTests(unittest.TestCase):
    def test_missing_and_nonfinite_inputs_never_invent_score(self):
        for row in [{}, {"rsi14": np.nan, "bias_250_pct": 2, "kdj_j": 40, "bollinger_percent_b_pct": 50}]:
            result = predict_proxy_score(row)
            self.assertIsNone(result["metrics"]["score_proxy"])
            self.assertEqual(result["status"], "unavailable_missing_inputs")

    def test_original_algorithm_is_not_claimed_and_boundary_action_abstains(self):
        result = predict_proxy_score({"rsi14": 55.1, "ma250_bias_pct": 4.19,
                                      "kdj_j": 46.4, "bollinger_20d_position_pct": 56})
        self.assertFalse(result["is_original_algorithm"])
        self.assertIsNone(result["metrics"]["score_original"])
        self.assertIsNone(result["metrics"]["action_proxy"])
        self.assertIn("action_boundary_within_error_band", result["domain_warnings"])

    def test_extrapolation_and_time_travel_are_explicit(self):
        row = {"rsi14": 25, "bias_250_pct": -10, "kdj_j": -20, "bollinger_percent_b_pct": -10}
        result = predict_proxy_score(row)
        self.assertEqual(result["status"], "experimental_extrapolation")
        self.assertIsNone(result["metrics"]["action_proxy"])
        with self.assertRaises(ValueError): predict_proxy_score(row, as_of="2026-10-29")
        self.assertEqual(observed_grade_proxy(57.3), "C")
        self.assertEqual(observed_grade_proxy(75.2), "B")

    def test_mature_return_labels_and_future_isolation(self):
        dates = pd.bdate_range(end="2026-12-01", periods=450)
        close = 100 * 1.001 ** np.arange(len(dates))
        frame = pd.DataFrame({"date": dates, "open": close, "high": close * 1.01,
                              "low": close * .99, "close": close, "volume": 1000.0})
        result = historical_conditional_returns(frame, frame, as_of="2026-11-09 11:30", current_score=50,
                    return_adjustment="qfq", bin_width=100, include_extrapolated=True)
        self.assertGreater(result["metrics"]["same_score_samples_proxy"], 0)
        self.assertAlmostEqual(result["metrics"]["forward_60d_mean_pct_proxy"], (1.001**60-1)*100, places=8)
        self.assertTrue(all(row["label_end_date"] < "2026-11-09" for row in result["samples"]))
        self.assertEqual(sum(b["count"] for b in result["histogram"]), len(result["samples"]))
        changed = frame.copy()
        for col in ["open", "high", "low", "close"]:
            changed.loc[changed.date >= "2026-11-09", col] *= 10
        future = historical_conditional_returns(changed, changed, as_of="2026-11-09 11:30", current_score=50,
                    return_adjustment="qfq", bin_width=100, include_extrapolated=True)
        self.assertEqual(result, future)
        with self.assertRaises(ValueError):
            historical_conditional_returns(frame, frame, as_of="2026-11-09", current_score=50,return_adjustment="")
        with self.assertRaises(ValueError):
            historical_conditional_returns(frame, frame.iloc[1:], as_of="2026-11-09", current_score=50,return_adjustment="qfq")


if __name__ == "__main__": unittest.main()
