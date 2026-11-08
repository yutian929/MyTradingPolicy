"""Report source differences without replacing the author's published values."""
from pathlib import Path
import json,collections,csv,math
ROOT=Path(__file__).resolve().parents[4];A=ROOT/'research/fuli_time/archive'
im=json.loads((A/'metrics_long.json').read_text())['observations']
body=json.loads((A/'body_facts.json').read_text())
lookup=collections.defaultdict(list)
for m in im:lookup[m['note_id'],m['metric']].append(m)
diff=[];matched=0
for b in body:
    if not b.get('subject','').startswith('中证红利低波'):continue
    metric=b['metric'];v=b['value']
    if metric=='score_body':
        metric='score_rounded' if isinstance(v,(int,float)) and float(v).is_integer() else 'score_precise'
    if metric=='annualized_volatility_pct':metric='annualized_volatility_20d_pct'
    sources=lookup.get((b['note_id'],metric),[])
    if not sources:continue
    if metric.endswith('_text') or isinstance(v,bool):continue
    if isinstance(v,(float,int)):
        sources=[s for s in sources if isinstance(s['value'],(float,int))]
        # Accommodate rounding to the precision displayed in body text.
        tol=0.00001 if metric in ['price','same_score_samples'] else .051 if metric in ['score_precise','rsi14','kdj_j','kdj_k','kdj_d'] else .0051
        same=any(abs(s['value']-v)<=tol for s in sources)
    elif metric=='score_grade':same=any(s['value']==v for s in sources)
    else:continue
    if same:matched+=1;continue
    confirmed=b['date']=='2026-10-26' and metric=='spread_percentile' and v==37 and any(s['value']==38 for s in sources)
    diff.append({'date':b['date'],'note_id':b['note_id'],'metric':metric,'body_value':v,
                 'image_values':list(dict.fromkeys(str(s['value']) for s in sources)),
                 'images':list(dict.fromkeys(s['image_file'] for s in sources)),
                 'source_url':b['source_url'],'status':'confirmed_source_disagreement' if confirmed else 'requires_source_review',
                 'meaning':'已目视确认正文37、图中38，两个来源分别保留' if confirmed else '图文数值不一致候选；可能为作者差异或OCR误读，未自动改值'})
result={'matched_body_image_facts':matched,'differences':diff,'note':'正文和图片是独立来源；匹配只提供交叉佐证，不代表所有OCR字词已人工核验。'}
(A/'body_image_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
with (A/'body_image_differences.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=['date','note_id','metric','body_value','image_values','images','source_url','status','meaning']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for d in diff:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in d.items()})
print(json.dumps({'matched':matched,'differences':len(diff)},ensure_ascii=False))
