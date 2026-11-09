import unittest
from unittest.mock import Mock, patch
from pathlib import Path

import pandas as pd

from trading_analysis.common.indicators import macd, rsi_wilder
from trading_analysis.data.akshare_provider import DataBundle, DataUnavailable
from trading_analysis.dashboard.data import add_averages, select_range, load_history, PERIODS
from trading_analysis.dashboard.charts import available_panels, build_chart


class DashboardTests(unittest.TestCase):
    def history(self):
        dates = pd.bdate_range('2020-01-01', '2026-11-06')
        close = pd.Series(range(1, len(dates) + 1), dtype=float)
        frame = add_averages(pd.DataFrame(dict(date=dates, open=close, high=close + 1,
                                             low=close - 1, close=close, volume=100)))
        return frame.join(macd(frame.close)).assign(rsi14=rsi_wilder(frame.close))

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

    def test_panel_combinations_and_shared_time_axes(self):
        frame = self.history()
        for panels, axes, trace_count in [((), 1, 1), (("成交量",), 2, 2),
                                          (("MACD",), 2, 4), (("MACD", "成交量"), 3, 5),
                                          (("RSI",), 2, 2), (("成交量", "MACD", "RSI"), 4, 6)]:
            fig = build_chart(frame, [], panels=panels)
            self.assertEqual(len(fig.data), trace_count)
            self.assertEqual(len({trace.yaxis for trace in fig.data}), axes)
            for trace in fig.data:
                if trace.type == 'bar':
                    self.assertEqual(trace.marker.line.width, 1)
                    self.assertEqual(trace.marker.line.color, trace.marker.color)
            self.assertEqual({trace.xaxis for trace in fig.data}, {"x"})
            self.assertEqual(fig.layout.hoversubplots, "axis")
            self.assertEqual(fig.layout.xaxis.spikemode, "across")
            self.assertEqual(fig.layout.xaxis.anchor, f"y{axes}" if axes > 1 else "y")
            self.assertTrue(fig.layout.xaxis.showticklabels)
            for row in range(1, axes + 1):
                yaxis = fig.layout["yaxis" if row == 1 else f"yaxis{row}"]
                self.assertEqual(yaxis.anchor, "x")
                self.assertLess(yaxis.domain[0], yaxis.domain[1])
            if "MACD" in panels:
                histogram = next(t for t in fig.data if t.name == "MACD 柱")
                pd.testing.assert_series_equal(pd.Series(histogram.y), frame.macd_histogram,
                                               check_names=False)
        nav = frame[["date", "close", "macd_dif", "macd_dea", "macd_histogram"]]
        self.assertEqual(available_panels(nav, nav=True), ["MACD", "RSI"])
        fig = build_chart(nav, [], nav=True, panels=("成交量", "MACD"))
        self.assertEqual([t.name for t in fig.data], ["单位净值", "MACD 柱", "DIF", "DEA"])

    def test_macd_load_warmup_range_and_no_future_leak(self):
        frame = self.history()
        provider = Mock()
        provider._read.return_value = DataBundle(frame, {})
        full = load_history('000300', '指数', provider=provider).frame
        columns = ['macd_dif', 'macd_dea', 'macd_histogram']
        self.assertTrue(full[columns].iloc[:33].isna().all().all())
        self.assertTrue(full[columns].iloc[33:].notna().all().all())
        one = select_range(full, 1)
        pd.testing.assert_frame_equal(one[columns], full.loc[one.index, columns])
        pd.testing.assert_frame_equal(macd(full.close.iloc[:100]), full[columns].iloc[:100])

    def test_rsi_full_history_warmup_range_and_reference_lines(self):
        frame = self.history()
        # Oscillating prices expose reinitialization when selecting a shorter range.
        frame['close'] = [100 + (i % 17) for i in range(len(frame))]
        frame['open'] = frame.close
        frame['high'] = frame.close + 1
        frame['low'] = frame.close - 1
        provider = Mock()
        provider._read.return_value = DataBundle(frame, {})
        full = load_history('000300', '指数', provider=provider).frame
        self.assertTrue(full.rsi14.iloc[:14].isna().all())
        self.assertTrue(full.rsi14.iloc[14:].between(0, 100).all())
        one = select_range(full, 1)
        pd.testing.assert_series_equal(one.rsi14, full.loc[one.index, 'rsi14'])
        pd.testing.assert_series_equal(rsi_wilder(full.close.iloc[:100]), full.rsi14.iloc[:100], check_names=False)
        fig = build_chart(one, [], panels=['RSI'])
        self.assertEqual(fig.data[-1].name, 'RSI (14)')
        self.assertFalse(fig.data[-1].showlegend)
        self.assertEqual(tuple(fig.layout.yaxis2.range), (0, 100))
        self.assertEqual({shape.y0 for shape in fig.layout.shapes}, {30, 70})
        self.assertTrue(all(shape.yref == 'y2' for shape in fig.layout.shapes))
        nav = full[['date', 'close', 'rsi14']]
        self.assertEqual(len(build_chart(nav, [], nav=True, panels=['RSI']).data), 2)

    def test_rsi_monotonic_and_flat_prices(self):
        self.assertEqual(rsi_wilder(pd.Series(range(20), dtype=float)).iloc[-1], 100.)
        self.assertEqual(rsi_wilder(pd.Series(range(20, 0, -1), dtype=float)).iloc[-1], 0.)
        self.assertTrue(rsi_wilder(pd.Series([100.] * 20)).isna().all())

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
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_data.clear()
        frame = self.history()
        bundle = DataBundle(frame, {'nav': False, 'api': 'test', 'fetched_at': 'test'})
        with patch('trading_analysis.dashboard.data.load_history', return_value=bundle):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/trading_analysis/dashboard/app.py')).run()
            self.assertFalse(app.exception)
            app.radio[0].set_value('1年').run()
            self.assertFalse(app.exception)
            app.multiselect[0].set_value([]).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.multiselect[1].value, ['成交量'])
            for panels in (['成交量', 'MACD', 'RSI'], ['RSI'], ['MACD'], []):
                app.multiselect[1].set_value(panels).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.multiselect[1].value, panels)
            app.selectbox[0].set_value('股票（A股）').run()
            app.text_input[0].set_value('600519')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['request'][0], '600519')

    def test_nav_ui_only_offers_macd_with_short_history(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_data.clear()
        frame = self.history().iloc[:20]
        bundle = DataBundle(frame, {'nav': True, 'api': 'test', 'fetched_at': 'test'})
        with patch.dict('os.environ', {'MTP_VIEWER_SYMBOL': '050025', 'MTP_VIEWER_TYPE': 'fund'}), \
             patch('trading_analysis.dashboard.data.load_history', return_value=bundle):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/trading_analysis/dashboard/app.py')).run()
            self.assertEqual(app.multiselect[1].options, ['MACD', 'RSI'])
            self.assertEqual(app.multiselect[1].value, [])
            app.multiselect[1].set_value(['MACD']).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('不足 34 条' in item.value for item in app.info))


if __name__ == '__main__':
    unittest.main()
