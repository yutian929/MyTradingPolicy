"""Real-data snapshots, explicit source gaps and reproducible research reports."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import html
import json
import math

import numpy as np
import pandas as pd

from trading_analysis.data.akshare_provider import AkShareProvider, DataBundle, DataUnavailable, build_asof_ohlcv, normalize_ohlcv
from .analysis import calibrated_config, compute_indicators, compute_weekly_indicators, indicator_band
from .catalog import LABELS, EXTRA_LABELS
from .valuation import valuation_snapshot
from .scoring import predict_proxy_score, historical_conditional_returns

TZ = ZoneInfo('Asia/Shanghai')
TECHNICAL_MAP = {
    'price':'close', 'daily_return_pct':'daily_return_pct', 'bias_250_pct':'ma250_bias_pct',
    'rsi14':'rsi14', 'kdj_k':'kdj_k', 'kdj_d':'kdj_d', 'kdj_j':'kdj_j',
    'return_5d_pct':'momentum_5d_pct', 'return_10d_pct':'momentum_10d_pct', 'return_20d_pct':'momentum_20d_pct',
    'annualized_volatility_20d_pct':'volatility_20d_ann_pct', 'volume_ratio':'volume_ratio_20d',
    'position_52w_pct':'price_52w_position_pct', 'bollinger_percent_b_pct':'bollinger_20d_position_pct',
    'streak':'close_change_streak',
}
# Research acceptance targets, declared separately from any rounded source values.
TOLERANCES = {'price':.001, 'daily_return_pct':.01, 'bias_250_pct':.01, 'rsi14':.1,
    'kdj_k':.1,'kdj_d':.1,'kdj_j':.1,'return_5d_pct':.01,'return_10d_pct':.01,'return_20d_pct':.01,
    'annualized_volatility_20d_pct':.06,'volume_ratio':.01,'position_52w_pct':.55,
    'bollinger_percent_b_pct':.55,'streak':0.,'dividend_yield_pct':.02,'bond_yield_10y_pct':.015,
    'equity_bond_spread_pp':.02,'score_precise':3.}


def _stamp(value):
    t=pd.Timestamp(value)
    return t.tz_localize(TZ) if t.tzinfo is None else t.tz_convert(TZ)


def clean(value):
    """Strict JSON: missing numerics become null, never NaN or zero."""
    if isinstance(value, dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean(v) for v in value]
    if isinstance(value,(pd.Timestamp,datetime)):return value.isoformat()
    if isinstance(value,(np.bool_,bool)):return bool(value)
    if isinstance(value,(np.integer,int)):return int(value)
    if isinstance(value,(float,np.floating)):return float(value) if math.isfinite(value) else None
    if value is pd.NaT:return None
    return value


def metric_unit(key):
    if key in EXTRA_LABELS:return '元'
    if key.endswith('_pct'):return '%'
    if key.endswith('_pp'):return '百分点'
    if 'percentile' in key:return '百分位'
    return {'price':'元','rsi14':'点','kdj_k':'点','kdj_d':'点','kdj_j':'点',
            'score_precise':'分','score_rounded':'分','same_score_samples':'个',
            'streak':'天','volume_ratio':'倍','pe_ttm':'倍','pb':'倍'}.get(key,'')


def snapshot_from_data(prices:DataBundle, *, asof, valuation=None, treasury=None,
                       adjusted_returns=None, input_errors=None, include_statistics=True):
    """Compute from provided, provenance-carrying OHLCV; never reads the author archive."""
    cutoff=_stamp(asof);day=cutoff.tz_localize(None).normalize()
    frame=normalize_ohlcv(prices.frame)
    if frame.empty or frame.date.max()!=day:raise DataUnavailable('Price series must end on the requested trading day')
    if (frame.date>day).any():raise DataUnavailable('Future daily prices in snapshot')
    if cutoff.hour<15 and prices.metadata.get('bar_kind')!='partial_day':
        raise DataUnavailable('Intraday snapshot requires actual cutoff-bounded minute OHLCV')
    if prices.metadata.get('bar_kind')=='partial_day' and _stamp(prices.metadata['asof'])!=cutoff:
        raise DataUnavailable('Minute data cutoff does not match report cutoff')
    config=calibrated_config();features=compute_indicators(frame,config);last=features.iloc[-1]
    records={k:{'metric':k,'label':label,'unit':metric_unit(k),'value':None,'status':'unavailable',
                'source':None,'reason':'No verified implementation or matching input source'} for k,label in LABELS.items()}
    def put(key,value,status,source,reason=None):
        records[key]={'metric':key,'label':LABELS.get(key,EXTRA_LABELS.get(key,key)),'unit':metric_unit(key),'value':clean(value),
                      'status':status,'source':source,'reason':reason,'tolerance':TOLERANCES.get(key)}
    for key,col in TECHNICAL_MAP.items():
        inferred=key in {'volume_ratio','position_52w_pct','annualized_volatility_20d_pct'}
        available=pd.notna(last[col])
        put(key,last[col],('empirically_calibrated_formula' if inferred else 'computed_public_formula') if available else 'insufficient_history',
            {'symbol':'512890','api':'fund_etf_hist_em + fund_etf_hist_min_em','asof':cutoff.isoformat(),'column':col},
            'Source wording differs from empirically matching calculation; see config/validation' if inferred else None)
    for key in EXTRA_LABELS:
        available=pd.notna(last[key])
        put(key,last[key],'computed_additional_indicator' if available else 'insufficient_history',
            {'symbol':'512890','column':key,'asof':cutoff.isoformat(),
             'fast':12,'slow':26,'signal':9,'adjust':False,'ema_seed':'first_close',
             'dea_seed':0,'histogram_multiplier':2,'minimum_observations':34},
            'Additional indicator, not an author-archive field' if available else 'MACD requires at least 34 observations')
    errors=input_errors or {}
    val=valuation_snapshot(valuation,treasury,cutoff,valuation_error=errors.get('valuation'),treasury_error=errors.get('treasury'))
    for key,value in val['values'].items():put(key,value,val['statuses'][key],val['sources'].get(key),val['missing_reasons'].get(key))
    proxy=predict_proxy_score(last,as_of=cutoff.isoformat()) if day>pd.Timestamp('2026-10-30') else {
        'status':'unavailable_model_not_yet_frozen','metrics':{},'reason':'Model trained through 2026-10-30; earlier predictions are not point-in-time.'}
    pm=proxy['metrics'];score=pm.get('score_proxy')
    # These fields correspond to the author's outputs but are explicitly labelled surrogate.
    for key,value in [('score_precise',score),('score_rounded',None if score is None else round(score)),
                      ('score_grade',pm.get('grade_proxy')),('score_action_text',pm.get('action_proxy'))]:
        put(key,value,proxy['status'],{'model':proxy.get('model_version'),'trained_through':proxy.get('trained_through')},
            'Approximation, not recovered original score; boundary-sensitive actions may be withheld')
    stats={'status':'unavailable','reason':'Adjusted return prices or eligible frozen score unavailable','metrics':{},'histogram':[]}
    if include_statistics and adjusted_returns is not None and score is not None:
        try:
            stats=historical_conditional_returns(frame,adjusted_returns.frame,as_of=cutoff.isoformat(),current_score=score,return_adjustment='qfq')
        except (ValueError,DataUnavailable) as exc:
            stats={'status':'unavailable','reason':str(exc),'metrics':{},'histogram':[]}
    for key in ['same_score_samples','forward_60d_mean_pct','forward_60d_median_pct','forward_60d_min_pct','forward_60d_max_pct']:
        put(key,stats['metrics'].get(key+'_proxy'),stats['status'],{'formula':'mature adjusted 60-session returns in frozen proxy score bin'},
            'Independent retrospective statistic; not the original author sample set or a walk-forward trading backtest')
    def state(key,value,source_metric):put(key,value,'rule_mapping',{'input':source_metric,'boundary_policy':'left-closed'},'Public band or documented convention; not an order')
    r=float(last.rsi14);b=float(last.ma250_bias_pct);j=float(last.kdj_j)
    state('kdj_state_text',indicator_band('kdj_j',j) if math.isfinite(j) else None,'kdj_j')
    state('rsi_action_text','中性偏卖区·常规定投' if 30<=r<50 else '强弱平衡·常规定投' if 50<=r<70 else None,'rsi14')
    state('rsi_sentiment_text','情绪：接近超卖' if 30<=r<50 else '情绪：中性' if 50<=r<70 else None,'rsi14')
    state('bias_action_text','可适当加仓·常规定投' if 0<=b<5 else '常规定投·标准持有' if 5<=b<10 else None,'bias_250_pct')
    state('bias_sentiment_text','情绪：估值偏低' if 0<=b<5 else '情绪：估值合理' if 5<=b<10 else None,'bias_250_pct')
    bb=float(last.bollinger_20d_position_pct);pos=float(last.price_52w_position_pct);ratio=float(last.volume_ratio_20d)
    state('bollinger_state_text',None if not math.isfinite(bb) else '接近下轨·超跌' if bb<20 else '接近上轨·偏高' if bb>=80 else '区间内','bollinger_percent_b_pct')
    state('position_52w_state_text',None if not math.isfinite(pos) else '年内高位' if pos>=80 else '偏高' if pos>=60 else '中位' if pos>=40 else '偏低','position_52w_pct')
    state('volume_ratio_state_text',None if not math.isfinite(ratio) else '缩量' if ratio<.7 else '明显放量' if ratio>1.5 else '正常','volume_ratio')
    state('streak_state_text','连阳' if last.close_change_streak>0 else '连阴' if last.close_change_streak<0 else '持平','streak')
    state('volatility_state_text','越低越稳健','annualized_volatility_20d_pct')
    put('crowding_state_text',None,'unavailable',None,'Funding concentration formula is unpublished')
    fetch_time=(prices.metadata.get('minute_provenance') or {}).get('fetched_at',prices.metadata.get('fetched_at'))
    put('data_capture_time',fetch_time,'recorded_fetch_time',prices.metadata,'Our actual fetch time, not the author generation time; market cutoff is asof')
    weekly=compute_weekly_indicators(frame,as_of=day,config=config).iloc[-1].to_dict()
    return clean({'schema_version':1,'asof':cutoff.isoformat(),'generated_at':datetime.now(TZ).isoformat(),
        'symbol':'512890','valuation_symbol':'H30269','config':asdict(config),'metrics':records,
        'price_provenance':prices.metadata,'valuation':val,'input_errors':errors,
        'score_model':proxy,'conditional_returns':stats,'weekly':weekly,
        'latest_technical_row':last.to_dict(),'price_rows':len(frame),
        'complete_original_reproduction':False}),features


def run_snapshot(asof, *, cache_dir='data/raw/dividend_low_vol/cache',cache_only=False,
                 timeout_seconds=45,include_statistics=True):
    """Fetch fresh AkShare inputs. Explicit offline mode requires exact cached requests."""
    cutoff=_stamp(asof)
    if cutoff>pd.Timestamp.now(TZ):raise DataUnavailable('Requested cutoff has not happened yet; run after it is published')
    naive=cutoff.tz_localize(None);day=naive.strftime('%Y-%m-%d')
    if naive.time() not in [datetime.strptime(x,'%H:%M').time() for x in ('11:30','15:00')]:
        raise ValueError('Supported reproducible snapshots: 11:30 or 15:00 Asia/Shanghai')
    provider=AkShareProvider(cache_dir,timeout_seconds=timeout_seconds,cache_only=cache_only)
    calls={'daily':lambda:provider.daily(end_date=day),
           'valuation':provider.csindex_valuation,'treasury':provider.treasury}
    if naive.hour<15:calls['minutes']=lambda:provider.minutes(start_date=day+' 09:30:00',end_date=naive.strftime('%Y-%m-%d %H:%M:%S'),period='1')
    if include_statistics:calls['adjusted_returns']=lambda:provider.daily(end_date=day,adjust='qfq')
    bundles={};errors={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks={key:pool.submit(call) for key,call in calls.items()}
        for key,task in tasks.items():
            try:bundles[key]=task.result()
            except Exception as exc:errors[key]=f'{type(exc).__name__}: {exc}'
    for essential in ['daily']+(['minutes'] if naive.hour<15 else []):
        if essential not in bundles:raise DataUnavailable(errors[essential])
    daily=bundles['daily']
    if naive.hour<15:prices=build_asof_ohlcv(daily.frame,bundles['minutes'].frame,cutoff,period_minutes=1)
    else:
        f=daily.frame[daily.frame.date<=naive.normalize()].copy()
        prices=DataBundle(f,{**daily.metadata,'asof':cutoff.isoformat(),'bar_kind':'daily_close'})
    return snapshot_from_data(prices,asof=cutoff,valuation=bundles.get('valuation'),treasury=bundles.get('treasury'),
            adjusted_returns=bundles.get('adjusted_returns'),input_errors=errors,include_statistics=include_statistics)


def save_snapshot(result,features,output_dir):
    """CSV/JSON and an offline interactive chart with every field and provenance status."""
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/'snapshot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    rows=list(result['metrics'].values())
    with (out/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['metric','label','unit','value','status','source','reason','tolerance']);w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else v for k,v in r.items()})
    features.to_csv(out/'indicator_history.csv',index=False)
    pd.DataFrame([{'metric':r['metric'],'label':r['label'],'observed_value':None,'tolerance':r.get('tolerance')} for r in rows]).to_csv(out/'observations_template.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(result['conditional_returns'].get('histogram',[])).to_csv(out/'conditional_histogram.csv',index=False)
    pd.DataFrame(result['conditional_returns'].get('samples',[])).to_csv(out/'conditional_samples.csv',index=False)
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        frame=features.tail(300)
        fig=make_subplots(rows=4,cols=1,shared_xaxes=True,vertical_spacing=.04,row_heights=[.46,.18,.18,.18],subplot_titles=['价格、年线与布林带','RSI(14)','KDJ','MACD(12,26,9) · 柱=2×(DIF−DEA)'])
        fig.add_trace(go.Candlestick(x=frame.date,open=frame.open,high=frame.high,low=frame.low,close=frame.close,name='512890'),row=1,col=1)
        for col,name in [('ma250','MA250'),('bollinger_20d_lower','布林下轨'),('bollinger_20d_upper','布林上轨')]:
            fig.add_trace(go.Scatter(x=frame.date,y=frame[col],name=name),row=1,col=1)
        fig.add_trace(go.Scatter(x=frame.date,y=frame.rsi14,name='RSI14'),row=2,col=1)
        for key in ['kdj_k','kdj_d','kdj_j']:fig.add_trace(go.Scatter(x=frame.date,y=frame[key],name=key),row=3,col=1)
        fig.add_trace(go.Bar(x=frame.date,y=frame.macd_histogram,name='MACD柱',
                            marker_color=np.where(frame.macd_histogram>=0,'#d64545','#21936b')),row=4,col=1)
        for key,name,color in [('macd_dif','DIF','#e49b19'),('macd_dea','DEA','#6456b7')]:
            fig.add_trace(go.Scatter(x=frame.date,y=frame[key],name=name,line_color=color),row=4,col=1)
        fig.add_hline(y=0,line_color='#8a99a6',line_width=1,row=4,col=1)
        fig.update_layout(height=1100,xaxis_rangeslider_visible=False,template='plotly_white',title=f"红利低波 · {result['asof']}")
        chart=fig.to_html(full_html=False,include_plotlyjs=True)
        hist=result['conditional_returns'].get('histogram',[])
        if hist:
            h=go.Figure(go.Bar(x=[f"{b['lower_pct']:.2f}~{b['upper_pct']:.2f}%" for b in hist],y=[b['count'] for b in hist]))
            h.update_layout(title='独立代理模型：成熟60交易日条件收益分布（非博主原样本）',height=360,template='plotly_white')
            chart+=h.to_html(full_html=False,include_plotlyjs=False)
    except ImportError:chart='<p>可安装 notebook 可选依赖启用交互图；数值结果已保存。</p>'
    status_labels={'computed_public_formula':'公开公式计算','computed_additional_indicator':'新增分析指标','empirically_calibrated_formula':'样本校准的推断',
        'unavailable':'缺少输入或定义','insufficient_history':'历史不足','rule_mapping':'区间规则映射',
        'observed_prior_session':'前一可用交易日数据','candidate_source_recently_validated':'候选数据源：近期验证吻合',
        'derived_from_candidate_dy_source':'基于候选股息率计算','experimental_surrogate':'近似代理模型',
        'experimental_extrapolation':'超出代理模型训练范围','independent_proxy_statistic':'独立条件统计，未匹配原样本',
        'independent_proxy_statistic_low_sample':'独立条件统计，样本较少','recorded_fetch_time':'实际抓取记录'}
    display_rows=[]
    for r in rows:
        value=r['value'];status=r['status'];reason=''
        if status=='unavailable':reason='对应源数据或原始定义仍有缺口，详见 snapshot.json'
        elif status.startswith('experimental'):reason='分数为近似值；操作边界附近保留不确定性'
        elif status.startswith('independent_proxy_statistic'):reason='用真实前复权行情独立计算，与博主统计未匹配'
        elif status=='empirically_calibrated_formula':reason='由历史数据支持的推断，部分定义与图中文字不同'
        elif status=='recorded_fetch_time':reason='本程序的抓取时间；行情截止时间见页首'
        elif status=='computed_additional_indicator':reason='MACD(12,26,9)，首价初始化EMA，柱值为2×(DIF−DEA)；不参与代理评分'
        elif status=='insufficient_history':reason=r.get('reason') or '历史不足'
        shown='—' if value is None else f'{value:.6g}' if isinstance(value,(int,float)) else str(value)
        display_rows.append({'指标':r['label'],'数值':shown,'单位':r['unit'],'状态':status_labels.get(status,status),'说明':reason})
    table=pd.DataFrame(display_rows).to_html(index=False,escape=True,na_rep='—')
    content=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>红利低波研究快照</title>
<style>body{{font:15px system-ui;margin:32px auto;max-width:1250px;color:#17324d}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#edf3f8}}td{{word-break:break-word}}.note{{background:#fff4d8;padding:15px}}</style>
<h1>红利低波研究快照</h1><p>行情截止：{html.escape(result['asof'])} · 行情 512890 · 估值 H30269</p>
<p class="note">技术指标按真实行情计算；综合评分为代理模型，条件收益为独立历史统计。PE/PB、十年估值分位和拥挤度仍有来源或公式缺口。空白表示缺失，不是零。逐项来源见 snapshot.json。</p>{chart}<h2>全部对应指标</h2>{table}</html>'''
    (out/'report.html').write_text(content)
    return out
