"""Evidence diagnostics for return adjustment, not selection of a trading model."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from trading_analysis.studies.dividend_low_vol.analysis import compute_indicators
from trading_analysis.studies.dividend_low_vol.scoring import _features, _raw_prediction

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'research/fuli_time/reproduction'
rename={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume'}
prices={mode:pd.read_csv(ROOT/f'data/raw/512890_daily_em_{mode}.csv').rename(columns=rename) for mode in ['none','qfq']}
archive=pd.read_csv(ROOT/'outputs/fuli_time_archive/daily_indicators.csv')
targets=sorted(set(archive.forward_60d_min_pct)|set(archive.forward_60d_max_pct))
identities=[]
for mode,frame in prices.items():
    returns=(frame.close.shift(-60)/frame.close-1)*100
    for target in targets:
        errors=(returns-target).abs();i=errors.idxmin()
        identities.append({'adjustment':mode,'published_extreme_pct':target,
            'closest_real_60d_return_pct':returns[i],'absolute_error_pp':errors[i],
            'start_date':frame.loc[i,'date'],'end_date':frame.loc[i+60,'date'],
            'matches_display_rounding':bool(errors[i]<=.0051)})
(OUT/'return_extreme_identity.json').write_text(json.dumps(identities,ensure_ascii=False,indent=2)+'\n')
rows=[]
for signal_mode,signal_frame in prices.items():
    features=compute_indicators(signal_frame)
    raw_score=pd.Series(_raw_prediction(np.array([_features(r)[0] for _,r in features.iterrows()])))
    for transform,score in [('frozen_proxy',raw_score),('retrospective_percentile_of_proxy',raw_score.rank(pct=True)*100)]:
        for return_mode,return_frame in prices.items():
            returns=(return_frame.close.shift(-60)/return_frame.close-1)*100
            for lower in range(0,100,10):
                vals=returns[(score>=lower)&(score<lower+10)].dropna()
                rows.append({'signal_adjustment':signal_mode,'return_adjustment':return_mode,
                    'score_transform':transform,'score_bin_lower':lower,'count':len(vals),
                    'mean_pct':float(vals.mean()),'min_pct':float(vals.min()),'max_pct':float(vals.max()),
                    'purpose':'diagnostic_only; raw returns may contain corporate-action discontinuities; ranking retrospective'})
(OUT/'return_definition_sensitivity.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(pd.DataFrame(identities).groupby('adjustment').agg(n=('matches_display_rounding','size'),matched=('matches_display_rounding','sum')))
