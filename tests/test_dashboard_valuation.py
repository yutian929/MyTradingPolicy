import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from trading_analysis.data.akshare_provider import AkShareProvider, DataBundle, DataUnavailable
from trading_analysis.dashboard.valuation import (
    CSI_PE, DIVIDEND, PB, PE, PREMIUM, Valuation, dividend_history,
    historical_percentile, load_valuation, premium_history, valuation_options,
    valuation_position, values,
)


class ValuationTests(unittest.TestCase):
    def test_type_specific_options_and_reject_unsupported_metric(self):
        self.assertEqual(valuation_options('600519', '股票（A股）'), [PE, PB, DIVIDEND])
        self.assertEqual(valuation_options('000300', '指数'), [PE, PB, DIVIDEND])
        self.assertEqual(valuation_options('000001', '指数'), [CSI_PE, DIVIDEND])
        self.assertEqual(valuation_options('518880', '基金（ETF）'), [PREMIUM])
        self.assertEqual(valuation_options('510300', '基金（ETF）'), [PREMIUM])
        self.assertEqual(valuation_options('050025', '基金（场外）'), [])
        read = Mock()
        with self.assertRaises(ValueError):
            load_valuation('518880', '基金（ETF）', PE, reader=read)
        read.assert_not_called()

    def test_nonpositive_pe_and_missing_latest_not_replaced(self):
        raw = pd.DataFrame({'日期': pd.date_range('2020-01-01', periods=400), 'pe': 10.})
        raw.loc[398:, 'pe'] = [0, -3]
        frame = values(raw, '日期', 'pe')
        self.assertTrue(frame.value.iloc[-2:].isna().all())
        rank = historical_percentile(frame, 1)
        self.assertIsNone(rank['value'])
        self.assertIn('最近记录', rank['reason'])
        duplicate = pd.concat([raw, raw.iloc[-1:]])
        with self.assertRaises(DataUnavailable):
            values(duplicate, '日期', 'pe')

    def test_percentile_hand_calculation_coverage_and_direction(self):
        frame = pd.DataFrame({'date': pd.date_range('2025-01-01', '2026-01-01', periods=100),
                              'value': list(range(1, 100)) + [25]})
        rank = historical_percentile(frame, 1)
        self.assertEqual(rank['count'], 100)
        self.assertAlmostEqual(rank['value'], 26.)  # 1..25 and the current 25
        self.assertIsNone(historical_percentile(frame, 5)['value'])
        self.assertIsNone(historical_percentile(frame.tail(20), 1)['value'])
        self.assertEqual(valuation_position(PE, 10), '相对历史估值偏低')
        self.assertEqual(valuation_position(DIVIDEND, 10), '相对历史估值偏高')
        frame['value'] = 0.
        self.assertTrue(historical_percentile(frame, 1)['constant'])

    def test_gapped_history_cannot_masquerade_as_full_window(self):
        dates = pd.date_range('2025-01-01', periods=40).append(pd.date_range('2025-12-01', '2026-01-01'))
        frame = pd.DataFrame({'date': dates, 'value': 10.})
        rank = historical_percentile(frame, 1)
        self.assertIsNone(rank['value'])
        self.assertIn('缺口', rank['reason'])

    def test_premium_joins_same_date_and_excludes_today(self):
        prices = pd.DataFrame({'日期': ['2026-11-05', '2026-11-06', '2026-11-09'],
                               '收盘': [10.2, 9.8, 20.]})
        navs = pd.DataFrame({'净值日期': ['2026-11-05', '2026-11-09'], '单位净值': [10., 10.]})
        result = premium_history(prices, navs, today='2026-11-09')
        self.assertEqual(len(result), 1)  # neither yesterday's NAV nor unfinished today
        self.assertAlmostEqual(result.value.iloc[0], 2.)
        navs = pd.DataFrame({'净值日期': ['2026-11-05', '2026-11-06'], '单位净值': [0., 10.]})
        result = premium_history(prices, navs, today='2026-11-09')
        self.assertTrue(np.isnan(result.value.iloc[0]))
        self.assertAlmostEqual(result.value.iloc[1], -2.)

    def test_premium_loader_always_requests_raw_prices(self):
        prices = pd.DataFrame({'日期': ['2026-01-02'], '收盘': [9.8]})
        navs = pd.DataFrame({'净值日期': ['2026-01-02'], '单位净值': [10.]})
        read = Mock(side_effect=[DataBundle(prices, {}), DataBundle(navs, {})])
        got = load_valuation('518880', '基金（ETF）', PREMIUM, reader=read)
        self.assertEqual(read.call_args_list[0].args[1]['adjust'], '')
        self.assertAlmostEqual(got.frame.value.iloc[0], -2.)

    def test_dividends_use_per_ten_shares_implemented_ex_dates(self):
        prices = pd.DataFrame({'数据日期': ['2025-06-01', '2025-06-02', '2025-12-02', '2026-06-02'],
                               '当日收盘价': 10.})
        dividends = pd.DataFrame({
            '公告日期': ['2025-05-20', '2025-11-20', '2025-05-25'],
            '除权除息日': ['2025-06-02', '2025-12-02', '2025-06-01'],
            '派息': [10., 5., 100.], '送股': 0., '转增': 0., '进度': ['实施', '实施', '预案']})
        got = dividend_history(prices, dividends, pd.DataFrame())
        np.testing.assert_allclose(got.value, [0., 10., 15., 5.])
        # Announced but not yet ex-dividend must not change the past.
        pd.testing.assert_frame_equal(
            dividend_history(prices.iloc[:2], dividends.iloc[:1], pd.DataFrame()), got.iloc[:2])

    def test_corporate_action_windows_and_missing_fields_are_not_estimated(self):
        prices = pd.DataFrame({'数据日期': ['2025-06-02', '2025-07-02', '2026-07-02'], '当日收盘价': 10.})
        dividends = pd.DataFrame({'公告日期': ['2025-05-20'], '除权除息日': ['2025-06-02'],
                                  '派息': [10.], '送股': [5.], '转增': [0.], '进度': ['实施']})
        got = dividend_history(prices, dividends, pd.DataFrame())
        self.assertTrue(got.value.iloc[:2].isna().all())
        self.assertEqual(got.value.iloc[2], 0.)
        dividends['送股'] = 0.
        got = dividend_history(prices, dividends, pd.DataFrame({'除权日': ['2025-07-02']}))
        self.assertEqual(got.value.iloc[0], 10.)
        self.assertTrue(np.isnan(got.value.iloc[1]))
        with self.assertRaises(DataUnavailable):
            dividend_history(prices, dividends.drop(columns='派息'), pd.DataFrame())

    def test_index_does_not_substitute_equal_weight_or_pe2(self):
        read = Mock(return_value=DataBundle(pd.DataFrame({'日期': ['2026-01-02'],
                    '滚动市盈率': [12.], '等权滚动市盈率': [40.]}), {}))
        got = load_valuation('000300', '指数', PE, reader=read)
        self.assertEqual(got.frame.value.iloc[0], 12.)
        self.assertEqual(read.call_args.args, ('stock_index_pe_lg', {'symbol': '沪深300'}))
        read.return_value = DataBundle(pd.DataFrame({'日期': ['2026-01-02'], '指数代码': [300],
                                                    '股息率1': [3.], '股息率2': [4.]}), {})
        self.assertEqual(load_valuation('000300', '指数', DIVIDEND, reader=read).frame.value.iloc[0], 3.)
        with self.assertRaises(DataUnavailable):
            load_valuation('000001', '指数', DIVIDEND, reader=read)

    def test_empty_corporate_action_table_is_opt_in(self):
        response = {'ok': True, 'akshare_version': 'test',
                    'table': json.loads(pd.DataFrame().to_json(orient='table'))}
        with tempfile.TemporaryDirectory() as tmp, patch('subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(response))):
            provider = AkShareProvider(tmp)
            with self.assertRaises(DataUnavailable):
                provider._read('stock_history_dividend_detail', {'symbol': '600519'})
            got = provider._read('stock_history_dividend_detail', {'symbol': '600519'}, allow_empty=True)
            self.assertTrue(got.frame.empty)
            self.assertEqual(got.metadata['provider'], 'Sina via AkShare')


class ValuationUITests(unittest.TestCase):
    def test_valuation_subplots_share_crosshair_and_preserve_missing_dates(self):
        from trading_analysis.dashboard.charts import build_chart
        dates = pd.bdate_range('2026-01-01', periods=5)
        prices = pd.DataFrame(dict(date=dates, open=10., high=11., low=9., close=10., volume=100.))
        items = [Valuation(metric, pd.DataFrame({'date': dates[[0, 2, 3]], 'value': [1., 2., np.nan]}),
                           unit, 'formula', 'note')
                 for metric, unit in [(PREMIUM, '%'), (PE, '倍'), (PB, '倍'), (DIVIDEND, '%')]]
        for panels in ([], ['成交量']):
            fig = build_chart(prices, [], panels=panels, valuations=items)
            self.assertEqual({t.xaxis for t in fig.data}, {'x'})
            self.assertEqual(len({t.yaxis for t in fig.data}), 1 + len(panels) + len(items))
            self.assertEqual(fig.layout.xaxis.anchor, f'y{1 + len(panels) + len(items)}')
            self.assertEqual(fig.layout.hoversubplots, 'axis')
            for item, trace in zip(items, fig.data[-4:]):
                self.assertEqual(trace.name, item.metric)
                self.assertEqual(list(pd.to_datetime(trace.x)), list(dates))
                np.testing.assert_allclose(trace.y, [1., np.nan, 2., np.nan, np.nan], equal_nan=True)
                self.assertFalse(trace.connectgaps)
                self.assertFalse(trace.showlegend)
            self.assertEqual(fig.layout.shapes[0].yref, f'y{2 + len(panels)}')
            self.assertEqual(fig.layout.shapes[0].xref, 'x domain')
        empty = build_chart(prices.iloc[-1:], [], panels=[], valuations=items)
        self.assertTrue(all(np.isnan(t.y).all() for t in empty.data[-4:]))

    def test_lazy_loading_failure_isolation_and_asset_switch(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from trading_analysis.dashboard.data import add_averages
        from trading_analysis.common.indicators import macd
        st.cache_data.clear()
        prices = add_averages(pd.DataFrame({'date': pd.bdate_range('2020-01-01', '2026-01-02'),
                                           'open': 100., 'high': 101., 'low': 99., 'close': 100., 'volume': 100}))
        prices = prices.join(macd(prices.close))
        bundle = DataBundle(prices, {'nav': False, 'api': 'fixture'})

        def load(symbol, kind, metric, **kwargs):
            if metric == PB:
                raise DataUnavailable('fixture: unavailable PB')
            return Valuation(metric, pd.DataFrame({'date': prices.date, 'value': np.arange(len(prices)) + 1.}),
                             '%' if metric == PREMIUM else '倍', 'fixture formula', 'fixture note')

        app_file = Path(__file__).resolve().parents[1] / 'src/trading_analysis/dashboard/app.py'
        with patch.dict('os.environ', {'MTP_VIEWER_SYMBOL': '000300', 'MTP_VIEWER_TYPE': 'index'}), \
             patch('trading_analysis.dashboard.data.load_history', return_value=bundle), \
             patch('trading_analysis.dashboard.valuation_view.load_valuation', side_effect=load) as loader:
            app = AppTest.from_file(str(app_file)).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.multiselect), 2)
            self.assertEqual(app.multiselect[1].label, '副图指标')
            self.assertEqual(app.multiselect[1].value, ['成交量'])
            loader.assert_not_called()
            app.multiselect[1].set_value(['成交量', 'MACD', PE, PB]).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('PB 暂不可用' in w.value for w in app.warning))
            self.assertTrue(any(m.label == '近5年历史分位' for m in app.metric))
            self.assertEqual(len(app.get('plotly_chart')), 1)
            chart = json.loads(app.get('plotly_chart')[0].proto.spec)
            self.assertIn(PE, [t['name'] for t in chart['data']])
            self.assertNotIn(PB, [t['name'] for t in chart['data']])
            next(w for w in app.selectbox if w.label == '标的类型').set_value('基金（ETF）').run()
            # Applied valuation options follow the submitted request, not a half-edited form.
            self.assertIn(PE, app.multiselect[1].options)
            app.text_input[0].set_value('518880')
            next(w for w in app.button if w.label == '查询行情').click().run()
            self.assertEqual(app.multiselect[1].options, ['成交量', 'MACD', 'RSI', PREMIUM])
            self.assertEqual(app.multiselect[1].value, ['成交量'])
            app.multiselect[1].set_value(['成交量', PREMIUM]).run()
            self.assertFalse(app.exception)
            self.assertFalse(any(c.label == '显示历史分位' for c in app.checkbox))
            self.assertEqual(len(app.get('plotly_chart')), 1)
            chart = json.loads(app.get('plotly_chart')[0].proto.spec)
            premium = next(t for t in chart['data'] if t['name'] == PREMIUM)
            self.assertEqual(premium['xaxis'], 'x')
            self.assertEqual(premium['yaxis'], 'y3')
            self.assertFalse(any(s.value == '估值参考' for s in app.subheader))
            self.assertTrue(any(e.label == '副图指标说明与数据' for e in app.expander))
            loader.reset_mock()
            app.multiselect[1].set_value([]).run()
            self.assertFalse(app.exception)
            loader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
