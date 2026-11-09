"""Bounded AkShare reads with explicit cache provenance and strict intraday cutoffs."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import contextlib
import hashlib
import io
import json
import subprocess
import sys
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

TZ = ZoneInfo('Asia/Shanghai')
ALLOWED_APIS = {'fund_etf_hist_em', 'fund_etf_hist_min_em', 'bond_zh_us_rate',
                'stock_zh_index_value_csindex', 'stock_market_fund_flow',
                'stock_zh_a_hist', 'index_zh_a_hist', 'fund_lof_hist_em',
                'fund_open_fund_info_em'}
RENAME = {'日期':'date', '时间':'datetime', '开盘':'open', '最高':'high', '最低':'low',
          '收盘':'close', '成交量':'volume', '成交额':'amount', '涨跌幅':'daily_return_pct'}

class DataUnavailable(RuntimeError):
    """Requested data cannot be substantiated; caller must retain the gap."""

@dataclass
class DataBundle:
    frame: pd.DataFrame
    metadata: dict


def _worker():
    request = json.load(sys.stdin)
    if request['api'] not in ALLOWED_APIS:
        raise ValueError('Unsupported API')
    import akshare as ak
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            frame = getattr(ak, request['api'])(**request['params'])
        print(json.dumps({'ok':True, 'akshare_version':ak.__version__,
                          'table':json.loads(frame.to_json(orient='table',date_format='iso'))},ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':f'{type(exc).__name__}: {exc}'},ensure_ascii=False))
        raise SystemExit(1)


def _stamp(value):
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize(TZ) if timestamp.tzinfo is None else timestamp.tz_convert(TZ)


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.rename(columns=RENAME).copy()
    key = 'datetime' if 'datetime' in result else 'date'
    if key not in result:
        raise DataUnavailable('Missing source time column')
    result[key] = pd.to_datetime(result[key],errors='raise')
    if result[key].dt.tz is not None:
        result[key]=result[key].dt.tz_convert(TZ).dt.tz_localize(None)
    for col in ['open','high','low','close','volume','amount']:
        if col in result:result[col]=pd.to_numeric(result[col],errors='raise')
    return result.sort_values(key).reset_index(drop=True)


class AkShareProvider:
    def __init__(self, cache_dir='data/raw/dividend_low_vol/cache', timeout_seconds=45, cache_only=False):
        self.cache_dir=Path(cache_dir)
        self.timeout_seconds=float(timeout_seconds)
        self.cache_only=bool(cache_only)
        if self.timeout_seconds <= 0:raise ValueError('timeout_seconds must be positive')

    def _read(self, api, params, *, normalize=False):
        if api not in ALLOWED_APIS:raise ValueError('Unsupported API')
        identity=json.dumps({'api':api,'params':params},sort_keys=True,separators=(',',':'))
        key=hashlib.sha256(identity.encode()).hexdigest()[:20]
        path=self.cache_dir/f'{api}_{key}.csv';meta_path=path.with_suffix('.json')
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        if self.cache_only:
            if not path.exists() or not meta_path.exists():
                raise DataUnavailable(f'Exact request cache missing: {api} {params}')
            meta=json.loads(meta_path.read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:
                raise DataUnavailable(f'Cache checksum mismatch: {path}')
            frame=pd.read_csv(path);meta={**meta,'cache_read':True,'mode':'cache_only'}
        else:
            started=datetime.now(TZ).isoformat()
            try:
                completed=subprocess.run([sys.executable,'-m',__name__,'--worker'],input=identity,
                                         capture_output=True,text=True,timeout=self.timeout_seconds,check=False)
                response=json.loads(completed.stdout)
                if not response.get('ok'):raise DataUnavailable(response.get('error','Unknown API failure'))
                frame=pd.read_json(io.StringIO(json.dumps(response['table'])),orient='table')
                if frame.empty:raise DataUnavailable(f'{api} returned no rows for {params}')
            except (subprocess.TimeoutExpired,ValueError,DataUnavailable) as exc:
                failure={'api':api,'params':params,'requested_at':started,'status':'failed','error':str(exc)}
                (self.cache_dir/f'{api}_{key}.failure.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2))
                raise DataUnavailable(f'{api}: {exc}; old cache was not substituted') from exc
            frame.to_csv(path,index=False)
            dates=frame['时间'] if '时间' in frame else frame['日期'] if '日期' in frame else None
            meta={'api':api,'params':params,'provider':'CSI via AkShare' if 'csindex' in api else 'Eastmoney via AkShare',
                  'akshare_version':response['akshare_version'],'fetched_at':datetime.now(TZ).isoformat(),
                  'source_date_min':str(pd.to_datetime(dates).min()) if dates is not None else None,
                  'source_date':str(pd.to_datetime(dates).max()) if dates is not None else None,
                  'rows':len(frame),'cache_path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'cache_read':False,'mode':'live','timezone':'Asia/Shanghai'}
            meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
        if normalize:frame=normalize_ohlcv(frame)
        frame.attrs['provenance']=meta
        return DataBundle(frame,meta)

    def daily(self, symbol='512890', end_date=None, adjust='', start_date='2019-01-01'):
        if adjust not in ('','qfq','hfq'):raise ValueError('Unknown adjustment')
        end_date=end_date or datetime.now(TZ).strftime('%Y-%m-%d')
        bundle=self._read('fund_etf_hist_em',{'symbol':symbol,'period':'daily','start_date':pd.Timestamp(start_date).strftime('%Y%m%d'),
                         'end_date':pd.Timestamp(end_date).strftime('%Y%m%d'),'adjust':adjust},normalize=True)
        bundle.metadata.update(price_adjustment=adjust or 'none',volume_unit='lots_100_shares',bar_kind='daily',requested_end_date=str(end_date))
        return bundle

    def minutes(self, symbol='512890', start_date=None, end_date=None, period='1', adjust=''):
        if period not in ('1','5','15','30','60'):raise ValueError('Unsupported minute period')
        if period=='1' and adjust:raise ValueError('AkShare 1-minute ETF series is unadjusted; adjustment cannot be requested')
        end_date=end_date or datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
        start_date=start_date or pd.Timestamp(end_date).strftime('%Y-%m-%d 09:30:00')
        start_date=_stamp(start_date).strftime('%Y-%m-%d %H:%M:%S')
        end_date=_stamp(end_date).strftime('%Y-%m-%d %H:%M:%S')
        bundle=self._read('fund_etf_hist_min_em',{'symbol':symbol,'start_date':start_date,'end_date':end_date,'period':period,'adjust':adjust},normalize=True)
        bundle.metadata.update(price_adjustment=adjust or 'none',volume_unit='lots_100_shares',bar_kind='minute',period_minutes=int(period),
                               asof=end_date,limitation='1m only last five trading days; longer intervals also have bounded server history')
        return bundle

    def treasury(self,start_date='2016-01-01'):
        bundle=self._read('bond_zh_us_rate',{'start_date':pd.Timestamp(start_date).strftime('%Y%m%d')})
        bundle.frame=bundle.frame.rename(columns={'日期':'date','中国国债收益率10年':'bond_yield_10y_pct'})
        bundle.frame['date']=pd.to_datetime(bundle.frame['date'])
        bundle.frame=bundle.frame.sort_values('date').reset_index(drop=True)
        return bundle

    def csindex_valuation(self,symbol='H30269'):
        bundle=self._read('stock_zh_index_value_csindex',{'symbol':symbol})
        bundle.frame=bundle.frame.rename(columns={'日期':'date','市盈率1':'pe_total_shares','市盈率2':'pe_calculation_shares',
                                                  '股息率1':'dividend_yield_total_shares_pct','股息率2':'dividend_yield_calculation_shares_pct'})
        bundle.frame['date']=pd.to_datetime(bundle.frame['date'])
        bundle.frame=bundle.frame.sort_values('date').reset_index(drop=True)
        bundle.metadata['limitation']='CSI recent ~20 rows; PE share-weighting alternatives are not confirmed equivalent to Xueqiu TTM; no PB/10-year history'
        return bundle

    def market_fund_flow(self):
        return self._read('stock_market_fund_flow',{})


def build_asof_ohlcv(daily_frame: pd.DataFrame, minute_frame: pd.DataFrame, asof, *, period_minutes=1, require_complete=True) -> DataBundle:
    """Combine prior complete sessions with only observed bars through asof.

    Minute timestamps label interval ends. At 09:30 the one-minute feed uses
    open=0; its observed auction close supplies the opening transaction price.
    Missing bars or an unavailable requested cutoff fail rather than use EOD data.
    """
    cutoff=_stamp(asof).tz_localize(None)
    if period_minutes not in (1,5,15,30,60):raise ValueError('Unsupported period_minutes')
    daily=normalize_ohlcv(daily_frame);minutes=normalize_ohlcv(minute_frame)
    required=['open','high','low','close','volume']
    if any(c not in daily or c not in minutes for c in required):raise DataUnavailable('OHLCV columns missing')
    day=cutoff.normalize(); current=minutes[(minutes.datetime.dt.normalize()==day)&(minutes.datetime<=cutoff)].copy()
    if current.empty:raise DataUnavailable(f'No actual minute bars for {cutoff}')
    if current.datetime.duplicated().any():raise DataUnavailable('Duplicate minute bars')
    start=day+pd.Timedelta(hours=9,minutes=30)
    expected_first=start if period_minutes==1 else start+pd.Timedelta(minutes=period_minutes)
    if current.datetime.min()!=expected_first:raise DataUnavailable('Morning opening bars missing; cannot establish intraday OHLCV')
    if current.datetime.max()!=cutoff:raise DataUnavailable(f'Requested cutoff {cutoff} unavailable; latest bar is {current.datetime.max()}')
    if require_complete:
        morning=pd.date_range(expected_first,min(cutoff,day+pd.Timedelta(hours=11,minutes=30)),freq=f'{period_minutes}min')
        afternoon_start=day+pd.Timedelta(hours=13,minutes=period_minutes)
        afternoon=pd.date_range(afternoon_start,cutoff,freq=f'{period_minutes}min') if cutoff>=afternoon_start else pd.DatetimeIndex([])
        expected=morning.append(afternoon)
        if not set(expected).issubset(set(current.datetime)):
            raise DataUnavailable('Minute series has gaps before requested cutoff')
    values=current[required].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (current[['high','low','close']]<=0).any().any() or (current.volume<0).any():
        raise DataUnavailable('Invalid source intraday OHLCV')
    first=current.iloc[0];opening=float(first.open)
    if opening<=0:
        if period_minutes!=1 or first.datetime!=start:raise DataUnavailable('Opening price unavailable')
        opening=float(first.close)
    bar={'date':day,'open':opening,'high':float(current.high.max()),'low':float(current.low.min()),
         'close':float(current.iloc[-1].close),'volume':float(current.volume.sum())}
    if 'amount' in current:bar['amount']=float(current.amount.sum())
    previous=daily[daily.date<day].copy()
    if previous.empty:raise DataUnavailable('Prior completed daily history missing')
    result=pd.concat([previous,pd.DataFrame([bar])],ignore_index=True)
    meta={'asof':_stamp(asof).isoformat(),'source_date':str(cutoff),'bar_kind':'partial_day',
          'daily_history_last_date':str(previous.date.max().date()),'minute_rows_used':len(current),
          'period_minutes':period_minutes,'volume_unit':'lots_100_shares','future_bars_used':False,
          'opening_price_source':'09:30 auction close' if float(first.open)<=0 else 'first completed minute bar open',
          'daily_provenance':daily_frame.attrs.get('provenance'),'minute_provenance':minute_frame.attrs.get('provenance')}
    result.attrs['provenance']=meta
    return DataBundle(result,meta)

if __name__=='__main__' and '--worker' in sys.argv:_worker()
