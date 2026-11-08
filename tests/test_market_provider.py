import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import pandas as pd
from trading_analysis.data.akshare_provider import AkShareProvider,DataUnavailable,build_asof_ohlcv
from trading_analysis.studies.dividend_low_vol.valuation import valuation_snapshot,roe_from_pe_pb

class AsOfTests(unittest.TestCase):
    def setUp(self):
        self.daily=pd.DataFrame([['2026-11-05',1,1.1,.9,1.05,100],['2026-11-06',1,99,.1,88,99999]],columns=['date','open','high','low','close','volume'])
        times=pd.date_range('2026-11-06 09:30',periods=121,freq='min')
        self.minutes=pd.DataFrame({'datetime':times,'open':1.,'high':1.1,'low':.9,'close':1.05,'volume':10.})
        self.minutes.loc[0,'open']=0
        self.minutes.loc[0,'close']=1
    def test_no_afternoon_or_daily_future_leak(self):
        future=pd.DataFrame([{'datetime':pd.Timestamp('2026-11-06 15:00'),'open':1,'high':999,'low':.01,'close':888,'volume':999999}])
        result=build_asof_ohlcv(self.daily,pd.concat([self.minutes,future]),'2026-11-06 11:30').frame
        self.assertEqual(len(result),2);self.assertEqual(result.iloc[-1]['close'],1.05)
        self.assertEqual(result.iloc[-1]['high'],1.1);self.assertEqual(result.iloc[-1]['volume'],1210)
        self.assertEqual(result.iloc[-1]['open'],1)
    def test_missing_minutes_or_cutoff_fail(self):
        with self.assertRaises(DataUnavailable):build_asof_ohlcv(self.daily,self.minutes.drop(50),'2026-11-06 11:30')
        with self.assertRaises(DataUnavailable):build_asof_ohlcv(self.daily,self.minutes,'2026-11-06 15:00')
    def test_absent_requested_date_never_reuses_last_day(self):
        with self.assertRaises(DataUnavailable):build_asof_ohlcv(self.daily,self.minutes,'2026-11-09 11:30')
    def test_unsupported_adjustment_is_explicit(self):
        with self.assertRaises(ValueError):AkShareProvider().minutes(adjust='qfq',period='1')

class CacheTests(unittest.TestCase):
    def test_cache_integrity_and_no_implicit_stale_fallback(self):
        frame=pd.DataFrame({'日期':['2026-11-06'],'开盘':[1],'最高':[1.1],'最低':[.9],'收盘':[1.05],'成交量':[100]})
        response={'ok':True,'akshare_version':'test','table':json.loads(frame.to_json(orient='table'))}
        with tempfile.TemporaryDirectory() as tmp:
            p=AkShareProvider(tmp)
            with patch('subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(response))):
                got=p.daily(end_date='2026-11-06')
            cached=AkShareProvider(tmp,cache_only=True).daily(end_date='2026-11-06')
            self.assertTrue(cached.metadata['cache_read']);self.assertEqual(cached.frame.iloc[0]['close'],1.05)
            with patch('subprocess.run',return_value=SimpleNamespace(stdout='{"ok":false,"error":"network down"}')):
                with self.assertRaises(DataUnavailable):p.daily(end_date='2026-11-06')
            Path(got.metadata['cache_path']).write_text('corrupted')
            with self.assertRaises(DataUnavailable):AkShareProvider(tmp,cache_only=True).daily(end_date='2026-11-06')

class ValuationTests(unittest.TestCase):
    def test_prior_published_date_and_missing_pb(self):
        val=pd.DataFrame({'date':['2026-11-05','2026-11-06'],'dividend_yield_total_shares_pct':[4.7,8],
                          'dividend_yield_calculation_shares_pct':[4.83,9],'pe_total_shares':[8.52,10],'pe_calculation_shares':[8,11]})
        bonds=pd.DataFrame({'date':['2026-11-05','2026-11-06'],'bond_yield_10y_pct':[1.6038,8]})
        s=valuation_snapshot(val,bonds,'2026-11-06 11:30')
        self.assertEqual(s['values']['dividend_yield_pct'],4.7)
        self.assertAlmostEqual(s['values']['equity_bond_spread_pp'],3.0962)
        self.assertIsNone(s['values']['pb']);self.assertIsNone(s['values']['pe_ttm'])
        self.assertEqual(s['diagnostics']['csi_valuation']['pe_total_shares'],8.52)
        self.assertIn('No ten-year',s['missing_reasons']['pe_percentile_10y'])
    def test_roe_identity_requires_consistent_inputs(self):
        self.assertAlmostEqual(roe_from_pe_pb(10,1),10)
        with self.assertRaises(ValueError):roe_from_pe_pb(0,1)

if __name__=='__main__':unittest.main()
