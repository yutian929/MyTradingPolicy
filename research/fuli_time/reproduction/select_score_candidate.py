import pandas as pd,numpy as np,json
from statistics import NormalDist
from pathlib import Path
x=pd.read_csv('outputs/fuli_time_archive/daily_indicators.csv');x=x[x.date<'2026-11-01'].reset_index(drop=True);y=x.score_precise.to_numpy()
fssets=[['rsi14','bias_250_pct'],['rsi14','bias_250_pct','kdj_j'],['rsi14','bias_250_pct','bollinger_percent_b_pct'],['rsi14','bias_250_pct','annualized_volatility_20d_pct'],['rsi14','bias_250_pct','volume_ratio'],['rsi14','bias_250_pct','kdj_j','bollinger_percent_b_pct']]
normal=NormalDist()
def trans(y,t):
 if t=='linear':return y
 if t=='logit':return np.log(y/(100-y))
 return np.array([normal.inv_cdf(v/100) for v in y])
def inv(y,t):
 if t=='linear':return np.clip(y,0,100)
 if t=='logit':return 100/(1+np.exp(-y))
 return np.array([100*normal.cdf(v) for v in y])
def predict(f,ids,vs,t,lam,degree):
 a=x[f].to_numpy();m=a[ids].mean(0);s=a[ids].std(0);a=(a-m)/s
 if degree==2:a=np.column_stack([a]+[a[:,i]*a[:,j] for i in range(a.shape[1]) for j in range(i,a.shape[1])])
 a=np.c_[np.ones(len(a)),a];pen=np.eye(a.shape[1])*lam;pen[0,0]=0
 c=np.linalg.solve(a[ids].T@a[ids]+pen,a[ids].T@trans(y[ids],t))
 return inv(a[vs]@c,t)
r=[]
for f in fssets:
 for t in ['linear','logit','probit']:
  for degree in [1,2]:
   for lam in [.01,.1,1,10]:
    err=[]
    for end in [18,22,26,30]:
     vs=np.arange(end,min(end+4,len(x)));p=predict(f,np.arange(end),vs,t,lam,degree);err.extend((p-y[vs]).tolist())
    r.append(dict(features=f,transform=t,degree=degree,ridge=lam,cv_mae=float(np.abs(err).mean()),cv_max=float(np.abs(err).max())))
r.sort(key=lambda a:a['cv_mae']);print(json.dumps(r[:12],indent=2));Path('research/fuli_time/reproduction/score_candidate_selection.json').write_text(json.dumps({'validation':'expanding folds 18,22,26,30 initial rows,4 day eval; only <=2026-10-30','candidates':r},indent=2))
