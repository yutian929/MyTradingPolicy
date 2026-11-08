"""Export portable factual tables and per-note audit texts from captured evidence."""
from pathlib import Path
import csv,json,collections,hashlib,zipfile
ROOT=Path(__file__).resolve().parents[4]
A=ROOT/'research/fuli_time/archive'
OUT=ROOT/'outputs/fuli_time_archive'
def read(name): return json.loads((A/name).read_text())
def dump(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def csvout(name,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
OUT.mkdir(parents=True,exist_ok=True)
notes=read('source_manifest.json'); index=read('ocr_index.json')
metrics=read('metrics_long.json')['observations']; bodies=read('body_facts.json')
if isinstance(bodies,dict):bodies=bodies.get('facts',bodies.get('observations',[]))
images=index['images']; assert not index['failures'],index['failures']
counts=collections.Counter(i['note_id'] for i in images)
for n in notes:assert counts[n['note_id']]==n['expected_images'],n['note_id']
assert len(notes)==42 and len(images)==274
for im in images:
    assert hashlib.sha256((ROOT/im['image_file']).read_bytes()).hexdigest()==im['sha256']
allrows=[]
for m in metrics:
    allrows.append({'date':m['date'],'note_id':m['note_id'],'subject':m.get('instrument_name','未核实'),
                    'metric':m['metric'],'value':m['value'],'unit':m['unit'],'source_channel':'image',
                    'page_kind':m['page_kind'],'source_url':m.get('source_url','https://www.xiaohongshu.com/explore/'+m['note_id']),
                    'image_file':m['image_file'],'ocr_file':m.get('ocr_file'),'line_id':m.get('line_id'),
                    'confidence':m.get('confidence'),'verification':m['status'],'source_text':m.get('raw_text'),
                    'extraction_method':m.get('extraction_method'),'previous_ocr_values':m.get('previous_ocr_values')})
for b in bodies:
    allrows.append({**b,'source_channel':b.get('source_channel','body')})
allrows.sort(key=lambda r:(str(r.get('date')),str(r.get('note_id')),str(r.get('source_channel')),str(r.get('metric'))))
dump(OUT/'all_observations.json',allrows);csvout('all_observations.csv',allrows)
dictionary=read('metric_dictionary.json');catalog=[]
for key in sorted(set(r['metric'] for r in allrows)):
    group=[r for r in allrows if r['metric']==key]
    catalog.append({'metric':key,'description':dictionary.get(key,next((r.get('summary') for r in group if r.get('summary')),key)),
                    'units':sorted(set(str(r.get('unit','')) for r in group)),
                    'channels':sorted(set(r['source_channel'] for r in group)),
                    'observation_count':len(group),'date_count':len(set(r['date'] for r in group))})
dump(OUT/'metric_catalog.json',catalog);csvout('metric_catalog.csv',catalog)
groups=collections.defaultdict(list)
for m in metrics:groups[(m['date'],m['note_id'],m.get('instrument_name'),m.get('chart_date'))].append(m)
wide=[]
for (day,nid,subject,chartday),group in sorted(groups.items(),key=lambda x:str(x[0])):
    row={'date':day,'note_id':nid,'subject':subject,'chart_date':chartday,'source_channel':'image',
         'source_url':'https://www.xiaohongshu.com/explore/'+nid}
    for key in sorted(set(m['metric'] for m in group)):
        priority=['value','strength','price','position','score','cover','overview']
        if key in ['price','daily_return_pct','score_rounded']:priority=['cover','overview','score']
        if key in ['score_grade','score_precise','score_action_text']:priority=['score','cover','overview']
        candidates=[m for m in group if m['metric']==key]
        chosen=min(candidates,key=lambda m:priority.index(m['page_kind']) if m['page_kind'] in priority else 99)
        row[key]=chosen['value']
    wide.append(row)
dump(OUT/'daily_indicators.json',wide);csvout('daily_indicators.csv',wide)
csvout('image_metrics.csv',metrics);csvout('body_facts.csv',bodies)
csvout('notes_index.csv',[{k:v for k,v in n.items() if k!='files'} for n in notes])
csvout('images_index.csv',images)
hist=read('histograms.json')['histograms']
histrows=[{**{k:v for k,v in h.items() if k!='bins'},**b} for h in hist for b in h['bins']]
csvout('histogram_bins.csv',histrows)
# Keep each source channel separate. No averaging, backfilling or re-computation of published values.
textdir=OUT/'notes_text';textdir.mkdir(exist_ok=True)
for n in notes:
    lines=[n['title'],f"日期：{n['date']} | 来源：{n['url']}",f"原帖图片数：{n['expected_images']}",
           '说明：正文以事实和摘要整理；图片为OCR转录，未逐字人工校验。数值矛盾保留。','', '[正文事实与摘要]']
    for b in bodies:
        if b['note_id']==n['note_id']:
            lines.append(f"{b.get('subject','')} | {b.get('metric','')} = {b.get('value','')} {b.get('unit','')} | {b.get('summary','')}")
    for im in images:
        if im['note_id']!=n['note_id']:continue
        o=json.loads((ROOT/im['ocr_file']).read_text())
        lines.extend(['',f"[图片 {im['page_kind']}] {im['image_file']}",f"SHA256: {im['sha256']}",'[结构化指标]'])
        for m in metrics:
            if m['image_file']==im['image_file']:
                lines.append(f"{m['metric']} = {m['value']} {m['unit']} | {m['status']}")
        for h in hist:
            if h['image_file']==im['image_file']:
                lines.append('[历史同分收益分布]')
                for b in h['bins']:
                    lines.append(f"{b.get('range_raw','')} | 样本数={b.get('count')} | {h.get('status')}")
        lines.extend(['[原始OCR文字；人工校正见上方结构化值，原OCR保留供审计]',o['text']])
    (textdir/f"{n['date']}_{n['note_id']}.txt").write_text('\n'.join(lines)+'\n')
summary={'notes':len(notes),'daily_notes':sum(n['note_type']=='daily' for n in notes),
         'images':len(images),'image_observations':len(metrics),'body_facts':len(bodies),
         'all_observations':len(allrows),'histograms':len(hist),'histogram_bins':len(histrows),
         'distinct_image_metric_names':len(set(m['metric'] for m in metrics)),
         'distinct_all_metric_names':len(catalog),
         'ocr_lines':sum(i['line_count'] for i in images),
         'status':'Published factual records captured; OCR status and unresolved issues remain explicit.'}
dump(OUT/'archive_summary.json',summary)
print(json.dumps(summary,ensure_ascii=False))
