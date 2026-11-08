"""CLI: reproducible 11:30 snapshots and next-day observation comparisons."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd
from .pipeline import run_snapshot,save_snapshot,TOLERANCES,clean


def compare(snapshot_path,observed_path,output_path):
    snapshot=json.loads(Path(snapshot_path).read_text())
    observed=pd.read_csv(observed_path)
    if 'metric' not in observed:raise ValueError('Observation CSV requires metric column')
    valcol='observed_value' if 'observed_value' in observed else 'value'
    if valcol not in observed:raise ValueError('Observation CSV requires observed_value or value column')
    rows=[]
    for row in observed.to_dict('records'):
        key=row['metric'];target=row[valcol]
        if pd.isna(target):continue
        result=snapshot['metrics'].get(key,{})
        actual=result.get('value');tol=TOLERANCES.get(key)
        error=None;passed=None
        if actual is not None:
            try:
                error=abs(float(actual)-float(target));passed=error<=tol+1e-10 if tol is not None else None
            except (ValueError,TypeError):
                # Fetch time is pipeline-specific; it is not an author-value accuracy target.
                passed=None if key=='data_capture_time' else str(actual)==str(target)
        rows.append({'metric':key,'observed_value':target,'predicted_value':actual,'absolute_error':error,
                     'tolerance':tol,'within_tolerance':passed,'model_status':result.get('status','unavailable'),
                     'asof':snapshot['asof']})
    if not rows:raise ValueError('No observed values entered; fill the template first')
    output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(output,index=False,encoding='utf-8-sig')
    return clean({'compared':len(rows),'within_tolerance':sum(r['within_tolerance'] is True for r in rows),
                  'failed':sum(r['within_tolerance'] is False for r in rows),
                  'unavailable_or_no_threshold':sum(r['within_tolerance'] is None for r in rows),'output':str(output)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    snap=commands.add_parser('snapshot',help='Fetch actual AkShare data and calculate a report')
    snap.add_argument('--asof',required=True,help='Asia/Shanghai market cutoff, e.g. 2026-11-09 11:30:00')
    snap.add_argument('--cache-only',action='store_true',help='Read exact cached requests; never fetch')
    snap.add_argument('--cache-dir',default='data/raw/dividend_low_vol/cache')
    snap.add_argument('--timeout',type=float,default=45)
    snap.add_argument('--no-statistics',action='store_true')
    snap.add_argument('--output')
    comp=commands.add_parser('compare',help='Compare saved predictions with tomorrow author observations')
    comp.add_argument('--snapshot',required=True);comp.add_argument('--observed',required=True)
    comp.add_argument('--output',default='outputs/fuli_time_reproduction/next_day_comparison.csv')
    args=parser.parse_args()
    try:
        if args.command=='snapshot':
            result,features=run_snapshot(args.asof,cache_dir=args.cache_dir,cache_only=args.cache_only,
                timeout_seconds=args.timeout,include_statistics=not args.no_statistics)
            stamp=pd.Timestamp(args.asof).strftime('%Y%m%d_%H%M%S')
            out=save_snapshot(result,features,args.output or f'outputs/fuli_time_reproduction/{stamp}')
            print(json.dumps({'asof':result['asof'],'report':str((out/'report.html').resolve()),
                              'snapshot':str((out/'snapshot.json').resolve()),'original_reproduction_complete':False,
                              'unavailable':[k for k,v in result['metrics'].items() if v['value'] is None]},ensure_ascii=False,indent=2))
        else:print(json.dumps(compare(args.snapshot,args.observed,args.output),ensure_ascii=False,indent=2))
    except (ValueError,RuntimeError) as exc:
        print(f'Cannot produce requested evidence: {exc}',file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
