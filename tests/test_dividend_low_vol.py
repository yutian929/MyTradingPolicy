"""关键数值、边界、预热期及未来数据隔离的离线测试。"""

import math
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from trading_analysis.studies.dividend_low_vol.analysis import (
    IndicatorConfig, compute_indicators, grade_score, indicator_band, yield_spread,
)


def prices(close):
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "date": pd.bdate_range("2020-01-01", periods=len(close)),
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.full(len(close), 100.0),
    })


class IndicatorTests(unittest.TestCase):
    def test_macd_warmup_and_flat_prices(self):
        result = compute_indicators(prices(np.full(40, 100)))
        columns = ["macd_dif", "macd_dea", "macd_histogram"]
        self.assertTrue(result[columns].iloc[:33].isna().all().all())
        self.assertTrue((result[columns].iloc[33:] == 0).all().all())

    def test_macd_price_shock_has_correct_signal_and_double_histogram(self):
        # After a flat history, a one-unit move changes EMA12 by 2/13,
        # EMA26 by 2/27, and DEA by one fifth of their difference.
        for direction in (-1, 1):
            result = compute_indicators(prices([100] * 40 + [100 + direction]))
            last = result.iloc[-1]
            expected_dif = direction * (2 / 13 - 2 / 27)
            self.assertAlmostEqual(last.macd_dif, expected_dif)
            self.assertAlmostEqual(last.macd_dea, expected_dif / 5)
            self.assertAlmostEqual(last.macd_histogram, expected_dif * 1.6)

    def test_grade_november_6_boundaries(self):
        for score, expected in [(0, "E"), (24.99, "E"), (25, "D"), (31.7, "D"),
                                (40, "C"), (55, "B"), (70, "A"), (100, "A")]:
            self.assertEqual(grade_score(score), expected)
        for value in [-1, 101, math.nan, math.inf]:
            with self.assertRaises(ValueError):
                grade_score(value)

    def test_yield_units_and_dashboard_bands(self):
        self.assertAlmostEqual(yield_spread(4.70, 1.60), 3.10)
        self.assertEqual(indicator_band("yield_spread_pp", 3.10), "划算")
        self.assertEqual(indicator_band("ma250_bias_pct", 4.19), "贴近年线")
        self.assertEqual(indicator_band("kdj_j", 46.4), "中性")
        self.assertEqual(indicator_band("rsi14", 55.1), "中性")
        self.assertEqual(indicator_band("rsi14", 70), "接近超买")
        self.assertEqual(indicator_band("rsi14", 80), "超买")

    def test_wilder_seed_and_recursion(self):
        # First 14 changes are seven +1 and seven -1: seeded averages both 0.5.
        close = [100]
        for delta in [1, -1] * 7 + [2]:
            close.append(close[-1] + delta)
        result = compute_indicators(prices(close))
        self.assertTrue(result.rsi14.iloc[:14].isna().all())
        self.assertAlmostEqual(result.rsi14.iloc[14], 50)
        gain, loss = (0.5 * 13 + 2) / 14, 0.5 * 13 / 14
        self.assertAlmostEqual(result.rsi14.iloc[15], 100 * gain / (gain + loss))

    def test_kdj_seed_at_first_complete_window(self):
        result = compute_indicators(prices(np.full(15, 100)))
        self.assertTrue(result.kdj_k.iloc[:8].isna().all())
        self.assertAlmostEqual(result.kdj_k.iloc[8], 50)
        self.assertAlmostEqual(result.kdj_d.iloc[8], 50)
        self.assertAlmostEqual(result.kdj_j.iloc[8], 50)

    def test_ma_momentum_volume_and_volatility(self):
        source = prices(np.arange(100, 400))
        result = compute_indicators(source)
        self.assertTrue(result.ma250.iloc[:249].isna().all())
        self.assertAlmostEqual(result.ma250.iloc[249], (100 + 349) / 2)
        self.assertAlmostEqual(result.ma250_bias_pct.iloc[249], (349 / 224.5 - 1) * 100)
        self.assertAlmostEqual(result.momentum_5d_pct.iloc[5], 5)
        self.assertTrue(result.volatility_20d_ann_pct.iloc[:20].isna().all())
        changes = np.arange(101, 121) / np.arange(100, 120) - 1
        expected = np.std(changes, ddof=1) * np.sqrt(252) * 100
        self.assertAlmostEqual(result.volatility_20d_ann_pct.iloc[20], expected)
        self.assertTrue(result.volume_ratio_20d.iloc[:19].isna().all())
        self.assertAlmostEqual(result.volume_ratio_20d.iloc[19], 1)
        self.assertTrue(result.price_52w_position_pct.iloc[:251].isna().all())
        self.assertAlmostEqual(result.price_52w_position_pct.iloc[251], 100 * (351 - 99) / (352 - 99))

    def test_zero_denominators_remain_unknown(self):
        source = prices(np.full(260, 100))
        source[["open", "high", "low", "close"]] = 100
        source["volume"] = 0
        result = compute_indicators(source)
        for name in ["rsi14", "kdj_k", "volume_ratio_20d", "bollinger_20d_position_pct", "price_52w_position_pct"]:
            self.assertTrue(result[name].isna().all(), name)
        self.assertEqual(result.ma250_bias_pct.iloc[-1], 0)
        self.assertEqual(result.volatility_20d_ann_pct.iloc[-1], 0)

    def test_future_data_does_not_change_past_features(self):
        source = prices(100 + np.arange(300) / 10 + np.sin(np.arange(300)))
        before = compute_indicators(source.iloc[:270])
        after = compute_indicators(source)
        assert_frame_equal(before, after.iloc[:270])
        self.assertFalse(after.attrs["composite_score_available"])
        self.assertNotIn("score", after)

    def test_invalid_dates_and_ohlcv_rejected(self):
        base = prices([100, 101, 102])
        cases = [base.iloc[::-1], base.drop(columns="close")]
        for column, value in [("date", base.date.iloc[0]), ("high", 99),
                              ("low", 104), ("volume", -1), ("close", np.nan)]:
            altered = base.copy()
            altered.loc[1, column] = value
            cases.append(altered)
        for source in cases:
            with self.assertRaises(ValueError):
                compute_indicators(source)

    def test_configuration_validation(self):
        with self.assertRaises(ValueError):
            IndicatorConfig(price_position_window=0)
        with self.assertRaises(ValueError):
            IndicatorConfig(bollinger_std_multiple=-2)


if __name__ == "__main__":
    unittest.main()
