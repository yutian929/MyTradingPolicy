import unittest
from unittest.mock import Mock, patch
from pathlib import Path

import pandas as pd

from trading_analysis.data.akshare_provider import DataBundle, DataUnavailable
from trading_analysis.dashboard.data import add_averages, select_range, load_history, PERIODS
from trading_analysis.dashboard.charts import build_chart


class DashboardTests(unittest.TestCase):
    def history(self):
        dates = pd.bdate_range('2020-01-01', '2026-11-06')
        close = pd.Series(range(1, len(dates) + 1), dtype=float)
        return add_averages(pd.DataFrame(dict(date=dates, open=close, high=close + 1,
                                             low=close - 1, close=close, volume=100)))

    def test_range_preserves_warmup(self):
        full = self.history()
        one = select_range(full, 1)
        self.assertGreaterEqual(one.date.min(), full.date.max() - pd.DateOffset(years=1))
        first_index = one.index[0]
        self.assertEqual(one.iloc[0].MA120, full.close.iloc[first_index-119:first_index+1].mean())
        self.assertTrue(full.MA120.iloc[:119].isna().all())
        pd.testing.assert_frame_equal(select_range(full, 10), full)
        self.assertLess(len(select_range(full, 1)), len(select_range(full, 5)))

    def test_chart_hides_all_or_some_averages(self):
        frame = self.history()
        self.assertEqual(len(build_chart(frame, []).data), 2)
        self.assertEqual([t.name for t in build_chart(frame, [5, 120]).data],
                         ['日 K', 'MA5', 'MA120', '成交量（手）'])
        self.assertEqual(build_chart(frame, [], nav=True).data[0].type, 'scatter')

    def test_routes_and_full_history_request(self):
        for kind, api in [('股票（A股）', 'stock_zh_a_hist'), ('指数', 'index_zh_a_hist'),
                          ('基金（ETF）', 'fund_etf_hist_em'), ('基金（LOF）', 'fund_lof_hist_em')]:
            provider = Mock()
            provider._read.return_value = DataBundle(self.history(), {})
            load_history('000001', kind, provider=provider)
            args = provider._read.call_args.args
            self.assertEqual(args[0], api)
            self.assertEqual(args[1]['start_date'], '19000101')
            self.assertEqual('adjust' in args[1], kind != '指数')

    def test_nav_and_invalid_code(self):
        provider = Mock()
        provider._read.return_value = DataBundle(pd.DataFrame({'净值日期': ['2026-11-05', '2026-11-06'],
                                                              '单位净值': [1.1, 1.2]}), {})
        bundle = load_history('050025', '基金（场外）', provider=provider)
        self.assertTrue(bundle.metadata['nav'])
        self.assertNotIn('open', bundle.frame)
        self.assertEqual(provider._read.call_args.args[1]['period'], '成立来')
        with self.assertRaises(ValueError):
            load_history('bad', '指数', provider=provider)

    def test_ui_controls_with_fixture(self):
        from streamlit.testing.v1 import AppTest
        frame = self.history()
        bundle = DataBundle(frame, {'nav': False, 'api': 'test', 'fetched_at': 'test'})
        with patch('trading_analysis.dashboard.data.load_history', return_value=bundle):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/trading_analysis/dashboard/app.py')).run()
            self.assertFalse(app.exception)
            app.radio[0].set_value('1年').run()
            self.assertFalse(app.exception)
            app.multiselect[0].set_value([]).run()
            self.assertFalse(app.exception)
            app.selectbox[0].set_value('股票（A股）').run()
            app.text_input[0].set_value('600519')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['request'][0], '600519')


if __name__ == '__main__':
    unittest.main()
