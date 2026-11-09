import unittest
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from trading_analysis.dashboard.charts import build_chart
from trading_analysis.dashboard.data import add_averages
from trading_analysis.dashboard.similarity import find_similar_periods
from trading_analysis.data.akshare_provider import DataBundle


def history(values):
    close = np.asarray(values, dtype=float)
    return add_averages(pd.DataFrame(dict(date=pd.bdate_range("2020-01-01", periods=len(close)),
                                          close=close, open=close, high=close + 1,
                                          low=close - 1, volume=100)))


class SimilarityTests(unittest.TestCase):
    def test_scaled_match_and_sample_exclusion(self):
        frame = history([200, 204, 202, 208, 50, 40, 60, 30, 100, 102, 101, 104])
        matches = find_similar_periods(frame, 4, 20)
        self.assertAlmostEqual(matches[0].score, 1)
        self.assertEqual(matches[0].start, frame.date.iloc[0])
        self.assertEqual(matches[0].end, frame.date.iloc[3])
        for i, item in enumerate(matches):
            self.assertLess(item.end, frame.date.iloc[-4])
            for other in matches[i + 1:]:
                self.assertTrue(item.end < other.start or other.end < item.start)
        self.assertEqual([p.score for p in matches], sorted([p.score for p in matches], reverse=True))

    def test_boundary_range_invalid_and_flat_data(self):
        frame = history([100, 102, 101, 104] * 3)
        matches = find_similar_periods(frame.iloc[4:], 4, 5)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].start, frame.date.iloc[4])
        with self.assertRaisesRegex(ValueError, "2 × M"):
            find_similar_periods(frame.iloc[:7], 4, 1)
        for values in ([1] * 8, [1, 2, 3, 4, 1, np.nan, 3, 4],
                       [1, 2, 3, 4, 1, 0, 3, 4]):
            with self.assertRaisesRegex(ValueError, "无法计算"):
                find_similar_periods(history(values), 4, 1)
        self.assertEqual(find_similar_periods(history([1, 1, 1, 1, 1, 2, 3, 4]), 4, 1), [])
        self.assertEqual(find_similar_periods(history([4, 3, 2, 1, 1, 2, 3, 4]), 4, 1), [])
        for m, n in [(2, 1), (3, 0)]:
            with self.assertRaises(ValueError):
                find_similar_periods(frame, m, n)

    def test_chart_backgrounds_focus_and_nav(self):
        frame = history([100, 102, 101, 104] * 20)
        matches = find_similar_periods(frame, 4, 3)
        sample = (frame.date.iloc[-4], frame.date.iloc[-1])
        fig = build_chart(frame, [], similarities=matches, sample_range=sample, focus_rank=1)
        self.assertEqual(len(fig.layout.shapes), 4)
        self.assertTrue(all(s.yref == "paper" and s.xref == "x" for s in fig.layout.shapes))
        self.assertTrue(all((s.y0, s.y1) == tuple(fig.layout.yaxis.domain) for s in fig.layout.shapes))
        self.assertEqual([a.text for a in fig.layout.annotations], ["①", "②", "③", "当前样本"])
        self.assertIn("0.40", fig.layout.shapes[0].fillcolor)
        self.assertLess(pd.Timestamp(fig.layout.xaxis.range[1]), frame.date.iloc[-1])
        self.assertIn("Pearson", fig.data[-2].hovertemplate)
        self.assertEqual({trace.xaxis for trace in fig.data}, {"x"})
        overview = build_chart(frame, [], similarities=matches, sample_range=sample)
        original = build_chart(frame, [])
        self.assertEqual(tuple(overview.layout.yaxis.range), tuple(original.layout.yaxis.range))
        self.assertFalse(overview.layout.yaxis.autorange)
        self.assertEqual(pd.Timestamp(overview.layout.xaxis.range[1]), frame.date.iloc[-1])
        nav = build_chart(frame[["date", "close"]], [], nav=True, panels=[],
                          similarities=matches, sample_range=sample)
        self.assertEqual(len(nav.layout.shapes), 4)

    def test_ui_search_focus_reset_and_context_changes(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_data.clear()
        frame = history(100 + np.sin(np.arange(800) * 0.3) * 10)
        bundle = DataBundle(frame, {"nav": False, "api": "fixture"})
        path = Path(__file__).resolve().parents[1] / "src/trading_analysis/dashboard/app.py"
        with patch("trading_analysis.dashboard.data.load_history", return_value=bundle):
            app = AppTest.from_file(str(path)).run()
            app.number_input[0].set_value(10)
            app.number_input[1].set_value(3)
            next(b for b in app.button if b.label == "相关").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state["similarity_result"]["matches"]), 3)
            app.button(key="similarity_locate_2").click().run()
            self.assertEqual(app.session_state["similarity_focus"], 2)
            spec = json.loads(app.get("plotly_chart")[0].proto.spec)
            self.assertIn("0.40", spec["layout"]["shapes"][1]["fillcolor"])
            self.assertLess(pd.Timestamp(spec["layout"]["xaxis"]["range"][1]), frame.date.iloc[-1])
            app.multiselect[0].set_value([]).run()
            self.assertEqual(app.session_state["similarity_focus"], 2)
            next(b for b in app.button if b.label == "返回全景").click().run()
            self.assertNotIn("similarity_focus", app.session_state)
            spec = json.loads(app.get("plotly_chart")[0].proto.spec)
            self.assertEqual(pd.Timestamp(spec["layout"]["xaxis"]["range"][1]), frame.date.iloc[-1])
            app.radio[0].set_value("1年").run()
            self.assertNotIn("similarity_result", app.session_state)
            app.number_input[0].set_value(300)
            next(b for b in app.button if b.label == "相关").click().run()
            self.assertTrue(any("2 × M" in w.value for w in app.warning))
            self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
