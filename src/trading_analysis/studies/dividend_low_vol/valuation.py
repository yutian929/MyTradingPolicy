"""Source-explicit valuation snapshots; unsupported source equivalences stay missing."""
from __future__ import annotations
from datetime import timedelta
import math
import numpy as np
import pandas as pd
from trading_analysis.data.akshare_provider import DataBundle

VALUATION_KEYS = ['dividend_yield_pct','bond_yield_10y_pct','equity_bond_spread_pp','pe_ttm','pb','roe_pct',
                  'pe_percentile_10y','pb_percentile_10y','spread_percentile','spread_historical_mean_pp',
                  'spread_historical_min_pp','spread_historical_max_pp','valuation_date_pe','valuation_date_pb','valuation_date_dy','crowding']


def _unpack(value):
    if value is None:return pd.DataFrame(),{}
    if isinstance(value,DataBundle):return value.frame.copy(),value.metadata
    return value.copy(),value.attrs.get('provenance',{})


def _prior(frame,asof):
    if frame.empty or 'date' not in frame:return None
    frame['date']=pd.to_datetime(frame['date']).dt.tz_localize(None)
    eligible=frame[frame.date < pd.Timestamp(asof).tz_localize(None).normalize()].sort_values('date')
    return None if eligible.empty else eligible.iloc[-1]


def roe_from_pe_pb(pe_ttm:float,pb:float)->float:
    """Derived identity for consistent PE/PB inputs, not a substitute source ROE."""
    if not math.isfinite(pe_ttm) or pe_ttm<=0 or not math.isfinite(pb) or pb<0:
        raise ValueError('PE must be finite positive; PB must be finite nonnegative')
    return 100*pb/pe_ttm


def history_percentile(series:pd.Series,value:float)->float:
    """Explicit weak empirical CDF; source author's tie rule remains unconfirmed."""
    clean=pd.to_numeric(series,errors='coerce').dropna()
    if clean.empty or not np.isfinite(clean).all() or not math.isfinite(value):
        raise ValueError('Finite historical values are required')
    return float((clean<=value).mean()*100)


def valuation_snapshot(valuation=None,treasury=None,asof=None,*,valuation_error=None,treasury_error=None):
    """Return values/statuses/sources/missing_reasons/diagnostics with archive keys.

    Source observations are selected strictly before the requested calendar date,
    matching midday publication of prior-session valuation and treasury values.
    CSI DY(total shares) is a separately labelled candidate source: recent five
    holdout dates match, but October historical discrepancies reach 0.51 pp.
    CSI PE alternatives are exposed in diagnostics, never renamed Xueqiu PE TTM.
    """
    if asof is None:raise ValueError('asof is required')
    values=dict.fromkeys(VALUATION_KEYS)
    statuses={k:'unavailable' for k in VALUATION_KEYS};sources={};reasons={}
    vf,vm=_unpack(valuation);tf,tm=_unpack(treasury)
    vr=_prior(vf,asof);tr=_prior(tf,asof)
    diagnostics={'asof':str(asof),'valuation_source_metadata':vm,'treasury_source_metadata':tm,
                 'availability_policy':'strictly prior date; actual historical publication timestamp is not available',
                 'source_equivalence':'CSI valuation is not assumed identical to Danjuan/Xueqiu',
                 'csi_valuation':None}
    if vr is not None:
        source_date=vr.date.strftime('%Y-%m-%d')
        dy=vr.get('dividend_yield_total_shares_pct',np.nan)
        diagnostics['csi_valuation']={key:float(vr[key]) if pd.notna(vr.get(key)) else None for key in
                                    ['pe_total_shares','pe_calculation_shares','dividend_yield_total_shares_pct','dividend_yield_calculation_shares_pct']}
        diagnostics['csi_valuation']['date']=source_date
        if pd.notna(dy) and np.isfinite(dy):
            values['dividend_yield_pct']=float(dy);values['valuation_date_dy']=source_date
            for key in ['dividend_yield_pct','valuation_date_dy']:
                statuses[key]='candidate_source_recently_validated'
                sources[key]={'api':'stock_zh_index_value_csindex','symbol':'H30269','field':'股息率1','date':source_date,
                              'limitation':'Matches five November holdout dates; October differences up to 0.51 percentage points'}
    else:
        reasons['dividend_yield_pct']=valuation_error or 'No prior-date CSI dividend yield observation'
        reasons['valuation_date_dy']=reasons['dividend_yield_pct']
    if tr is not None and pd.notna(tr.get('bond_yield_10y_pct')):
        values['bond_yield_10y_pct']=float(tr['bond_yield_10y_pct']);statuses['bond_yield_10y_pct']='observed_prior_session'
        sources['bond_yield_10y_pct']={'api':'bond_zh_us_rate','field':'中国国债收益率10年','date':tr.date.strftime('%Y-%m-%d')}
    else:reasons['bond_yield_10y_pct']=treasury_error or 'No prior-date treasury yield observation'
    if values['dividend_yield_pct'] is not None and values['bond_yield_10y_pct'] is not None:
        values['equity_bond_spread_pp']=values['dividend_yield_pct']-values['bond_yield_10y_pct']
        statuses['equity_bond_spread_pp']='derived_from_candidate_dy_source'
        sources['equity_bond_spread_pp']={'formula':'dividend_yield_pct - bond_yield_10y_pct',
                                       'dy':sources['dividend_yield_pct'],'treasury':sources['bond_yield_10y_pct']}
    else:reasons['equity_bond_spread_pp']='Missing one or both independent inputs'
    reasons.update({
        'pe_ttm':'AkShare CSI PE1/PE2/rolling PE are different from the cited Danjuan/Xueqiu TTM values; candidates retained in diagnostics',
        'pb':'No H30269 PB history in the available supported AkShare valuation endpoint',
        'roe_pct':'Consistent PE/PB inputs unavailable; PB/PE*100 identity is implemented but not fabricated',
        'pe_percentile_10y':'No ten-year source-consistent PE history',
        'pb_percentile_10y':'No ten-year source-consistent PB history',
        'spread_percentile':'No ten-year source-consistent dividend-yield history; recent20 observations cannot represent ten years',
        'spread_historical_mean_pp':'No ten-year source-consistent dividend-yield history',
        'spread_historical_min_pp':'No ten-year source-consistent dividend-yield history',
        'spread_historical_max_pp':'No ten-year source-consistent dividend-yield history',
        'valuation_date_pe':'Source-equivalent PE observation unavailable',
        'valuation_date_pb':'Source-equivalent PB observation unavailable',
        'crowding':'Author only labels A-share funding concentration; exact universe, calculation and time sampling are unpublished. Market fund flows are not concentration.'})
    cutoff=pd.Timestamp(asof).tz_localize(None).normalize()
    diagnostics['source_age_calendar_days']={
        'valuation':None if vr is None else int((cutoff-vr.date).days),
        'treasury':None if tr is None else int((cutoff-tr.date).days)}
    return {'values':values,'statuses':statuses,'sources':sources,'missing_reasons':reasons,'diagnostics':diagnostics}
