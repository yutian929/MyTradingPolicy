"""Candidate-formula and cutoff-isolation tests independent of the archive values."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from trading_analysis.studies.dividend_low_vol.analysis import (
    IndicatorConfig, calibrated_config, compute_indicators, compute_weekly_indicators,
)
from trading_analysis.studies.dividend_low_vol.technical_validation import read_morning


def prices(n=320):
    close=100+np.arange(n)/20+np.sin(np.arange(n)/4)
    return pd.DataFrame(dict(date=pd.bdate_range('2025-01-06',periods=n),open=close,
                             high=close+2,low=close-2,close=close,
                             volume=100+np.arange(n)*3))


class CalibratedTechnicalTests(unittest.TestCase):
    def test_close_extrema_do_not_use_daily_wicks(self):
        frame=prices()
        result=compute_indicators(frame,calibrated_config())
        window=frame.close.tail(252)
        expected=100*(window.iloc[-1]-window.min())/(window.max()-window.min())
        self.assertAlmostEqual(result.price_52w_position_pct.iloc[-1],expected)
        changed=frame.copy();changed['high']+=200;changed['low']/=2
        other=compute_indicators(changed,calibrated_config())
        self.assertAlmostEqual(other.price_52w_position_pct.iloc[-1],expected)
        self.assertNotEqual(result.price_52w_position_pct.iloc[-1],compute_indicators(frame).price_52w_position_pct.iloc[-1])

    def test_smoothed_volume_keeps_printed_alternative(self):
        frame=prices();frame.loc[frame.index[-1],'volume']*=5
        result=compute_indicators(frame,calibrated_config()).iloc[-1]
        self.assertAlmostEqual(result.volume_ratio_20d,frame.volume.tail(5).mean()/frame.volume.tail(20).mean())
        self.assertAlmostEqual(result.volume_ratio_today_20d,frame.volume.iloc[-1]/frame.volume.tail(20).mean())
        self.assertNotAlmostEqual(result.volume_ratio_20d,result.volume_ratio_today_20d)

    def test_calibrated_annualization_and_future_prefix(self):
        frame=prices();result=compute_indicators(frame,calibrated_config())
        expected=frame.close.pct_change().tail(20).std(ddof=1)*np.sqrt(250)*100
        self.assertAlmostEqual(result.volatility_20d_ann_pct.iloc[-1],expected)
        assert_frame_equal(compute_indicators(frame.iloc[:290],calibrated_config()),result.iloc[:290])

    def test_weekly_asof_prevents_future_week_and_future_day_leakage(self):
        frame=prices();cutoff=frame.date.iloc[-5]
        expected=compute_weekly_indicators(frame[frame.date<=cutoff])
        actual=compute_weekly_indicators(frame,as_of=cutoff)
        assert_frame_equal(expected,actual)
        mutated=frame.copy();mask=mutated.date>cutoff
        mutated.loc[mask,['open','high','low','close']]*=10
        assert_frame_equal(expected,compute_weekly_indicators(mutated,as_of=cutoff))
        self.assertEqual(actual.date.iloc[-1],cutoff)

    def test_morning_uses_actual_auction_and_ignores_afternoon(self):
        times=pd.date_range('2026-11-02 09:30',periods=121,freq='min')
        frame=pd.DataFrame({'时间':times,'开盘':0.,'最高':1.2,'最低':1.1,'收盘':1.15,'成交量':100})
        frame.loc[0,['最高','最低','收盘']]=1.16
        afternoon=pd.DataFrame([{'时间':pd.Timestamp('2026-11-02 13:01'),'开盘':9,'最高':9,'最低':9,'收盘':9,'成交量':999999}])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'minute.csv';pd.concat([frame,afternoon]).to_csv(path,index=False)
            row=read_morning(path,1)[pd.Timestamp('2026-11-02')]
            self.assertEqual(row['open'],1.16);self.assertEqual(row['close'],1.15)
            self.assertEqual(row['high'],1.2);self.assertEqual(row['volume'],12100)
            frame.iloc[:-1].to_csv(path,index=False)
            self.assertEqual(read_morning(path,1),{})

    def test_new_configuration_rejects_ambiguous_options(self):
        for kwargs in [{'price_position_basis':'random'},{'volume_numerator_window':0},
                       {'volume_numerator_window':21},{'volume_numerator_window':True}]:
            with self.assertRaises(ValueError):IndicatorConfig(**kwargs)


if __name__=='__main__':unittest.main()
