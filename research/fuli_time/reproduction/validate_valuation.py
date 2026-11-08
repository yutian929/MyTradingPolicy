"""Independent source comparisons; published values are used only as targets."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from trading_analysis.data.akshare_provider import AkShareProvider
from trading_analysis.studies.dividend_low_vol.valuation import valuation_snapshot,roe_from_pe_pb
ROOT=Path(__file__).resolve().parents[3]
archive=pd.read_csv(ROOT/'outputs/fuli_time_archive/daily_indicators.csv')
p=AkShareProvider(ROOT/'data/raw/dividend_low_vol/cache',cache_only=True)
v=p.csindex_valuation();t=p.treasury();rows=[]
for _,a in archive.iterrows():
 s=valuation_snapshot(v,t,a['date']+' 11:30:00')
 for metric in ['dividend_yield_pct','bond_yield_10y_pct','equity_bond_spread_pp']:
  predicted=s['values'][metric];target=a.get(metric)
  if predicted is None or pd.isna(target):continue
  rows.append(dict(date=a['date'],split='holdout' if a['date']>='2026-11-02' else 'development',metric=metric,predicted=predicted,target=float(target),abs_error=abs(predicted-target),source=s['sources'].get(metric)))
 for metric,field in [('pe_ttm','pe_total_shares'),('pe_ttm_csi2','pe_calculation_shares')]:
  c=s['diagnostics']['csi_valuation'];target=a.get('pe_ttm')
  if c and pd.notna(target):
   predicted=c[field]
   rows.append(dict(date=a['date'],split='holdout' if a['date']>='2026-11-02' else 'development',metric=metric,predicted=predicted,target=float(target),abs_error=abs(predicted-target),source='CSI different source diagnostic; not original PE output'))
out=ROOT/'outputs/fuli_time_reproduction';out.mkdir(exist_ok=True)
f=pd.DataFrame(rows);f.to_csv(out/'valuation_validation.csv',index=False,encoding='utf-8-sig')
summary=[]
for (metric,split),g in f.groupby(['metric','split']):
 summary.append(dict(metric=metric,split=split,n=len(g),mae=float(g.abs_error.mean()),max_abs_error=float(g.abs_error.max())))
roe=[]
for _,a in archive.iterrows():
 if all(pd.notna(a.get(k)) for k in ['pe_ttm','pb','roe_pct']):
  estimate=roe_from_pe_pb(a.pe_ttm,a.pb);roe.append(abs(estimate-a.roe_pct))
report={'source_comparisons':summary,'roe_formula_diagnostic':{'status':'uses_published_PE_PB_inputs_only_not_independent_prediction','n':len(roe),'max_abs_error_pp':max(roe),'mae_pp':float(np.mean(roe))},
 'limitations':['CSI data supports only recent20 dates; missing earlier observations are not invented','DY1 matches recent5 holdout dates but October source discrepancies remain','CSI PE1/PE2 are not accepted as Danjuan/Xueqiu PE TTM','No supported AkShare H30269 PB/ten-year valuation history found','Market fund flow columns do not establish author crowding definition'],
 'documentation':['https://akshare.akfamily.xyz/data/fund/fund_public.html','https://akshare.akfamily.xyz/data/index/index.html','https://github.com/akfamily/akshare/issues/5508']}
(ROOT/'research/fuli_time/reproduction/valuation_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
