import json
from pathlib import Path
import tempfile
import unittest
import pandas as pd
from trading_analysis.data.akshare_provider import DataBundle,DataUnavailable
from trading_analysis.studies.dividend_low_vol.pipeline import snapshot_from_data,run_snapshot,clean
from trading_analysis.studies.dividend_low_vol.__main__ import compare

def prices():
    return pd.DataFrame({'date':pd.to_datetime(['2026-11-05','2026-11-06']),
        'open':[1,1],'high':[1.2,1.2],'low':[.9,.9],'close':[1.1,1.1],'volume':[100,100]})

class PipelineTests(unittest.TestCase):
    def test_eod_cannot_claim_midday(self):
        with self.assertRaises(DataUnavailable):
            snapshot_from_data(DataBundle(prices(),{'bar_kind':'daily'}),asof='2026-11-06 11:30')

    def test_partial_bar_must_match_cutoff(self):
        with self.assertRaises(DataUnavailable):
            snapshot_from_data(DataBundle(prices(),{'bar_kind':'partial_day','asof':'2026-11-06 15:00'}),asof='2026-11-06 11:30')

    def test_future_snapshot_is_not_synthesized(self):
        with self.assertRaises(DataUnavailable):run_snapshot('2099-01-01 11:30')

    def test_compare_unavailable_is_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=root/'snapshot.json';o=root/'observed.csv'
            s.write_text(json.dumps({'asof':'2026-11-06 11:30','metrics':{
                'price':{'value':1.229,'status':'computed'},'pb':{'value':None,'status':'unavailable'},
                'score_precise':{'value':28.,'status':'experimental'}}}))
            o.write_text('metric,observed_value\nprice,1.229\npb,0.9\nscore_precise,31.7\n')
            result=compare(s,o,root/'comparison.csv')
            self.assertEqual(result['within_tolerance'],1)
            self.assertEqual(result['failed'],1)
            self.assertEqual(result['unavailable_or_no_threshold'],1)

    def test_json_nonfinite_is_missing(self):
        self.assertEqual(clean({'x':float('nan'),'y':float('inf'),'z':0}),{'x':None,'y':None,'z':0})

    def test_macd_snapshot_retains_missing_warmup_and_formula_metadata(self):
        result,_=snapshot_from_data(DataBundle(prices(),{'bar_kind':'daily'}),
                                    asof='2026-11-06 15:00',include_statistics=False)
        self.assertEqual(len(result['metrics']),55)
        for key in ['macd_dif','macd_dea','macd_histogram']:
            metric=result['metrics'][key]
            self.assertIsNone(metric['value'])
            self.assertEqual(metric['status'],'insufficient_history')
            self.assertEqual(metric['unit'],'元')
            self.assertEqual(metric['source']['histogram_multiplier'],2)
            self.assertIsNone(metric['tolerance'])

if __name__=='__main__':unittest.main()
