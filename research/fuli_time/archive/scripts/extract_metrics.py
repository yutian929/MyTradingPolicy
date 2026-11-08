#!/usr/bin/env python3
"""Extract source-bound observations from cached OCR; missing/ambiguous values stay explicit.

This is a transcription layer, not an implementation of the author's strategy.
Full OCR and every line containing a digit remain available beside typed metrics.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from ocr_images import ARCHIVE, ROOT, dump

# Rectangles use original-page coordinates normalized to image width/height.
# Match a whole numeric token to avoid treating explanatory thresholds as observations.
SPECS = {
 'cover': [
  ('price',(.04,.15,.49,.58),'source_price_unit_unknown'),('daily_return_pct',(.16,.29,.51,.59),'%'),
  ('score_rounded',(.49,.57,.49,.58),'score'),('bias_250_pct',(.08,.30,.68,.75),'%'),
  ('rsi14',(.40,.58,.68,.75),'index'),('dividend_yield_pct',(.69,.87,.68,.75),'%')],
 'overview':[
  ('price',(.04,.20,.23,.30),'source_price_unit_unknown'),('daily_return_pct',(.35,.50,.23,.28),'%'),
  ('score_rounded',(.49,.59,.23,.30),'score'),('pe_ttm',(.04,.25,.35,.41),'multiple'),
  ('dividend_yield_pct',(.49,.75,.35,.41),'%'),('equity_bond_spread_pp',(.63,.86,.47,.54),'pp'),
  ('rsi14',(.04,.25,.60,.665),'index'),('bias_250_pct',(.49,.74,.60,.68),'%'),
  ('crowding',(.10,.31,.72,.78),'index'),('bollinger_percent_b_pct',(.40,.60,.72,.78),'%'),
  ('position_52w_pct',(.70,.91,.72,.78),'%')],
 'strength':[
  ('rsi14',(.04,.17,.16,.21),'index'),('bias_250_pct',(.49,.64,.16,.21),'%'),
  ('kdj_j',(.12,.29,.65,.69),'index'),('kdj_k',(.40,.58,.65,.69),'index'),('kdj_d',(.69,.87,.65,.69),'index')],
 'price':[
  ('return_5d_pct',(.10,.34,.66,.73),'%'),('return_10d_pct',(.40,.62,.66,.73),'%'),('return_20d_pct',(.69,.91,.66,.73),'%')],
 'value':[
  ('dividend_yield_pct',(.10,.35,.23,.28),'%'),('bond_yield_10y_pct',(.39,.62,.23,.28),'%'),
  ('equity_bond_spread_pp',(.68,.90,.23,.28),'pp'),('pe_ttm',(.04,.26,.47,.50),'multiple'),
  ('pb',(.33,.56,.47,.50),'multiple'),('dividend_yield_pct',(.62,.89,.47,.50),'%')],
 'score':[
  ('score_precise',(.04,.18,.28,.37),'score'),('price',(.14,.35,.37,.40),'source_price_unit_unknown'),
  ('daily_return_pct',(.14,.35,.40,.44),'%'),('same_score_samples',(.49,.75,.37,.42),'days')],
 'position':[
  ('volume_ratio',(.14,.34,.53,.60),'multiple'),('streak',(.43,.60,.53,.60),'days'),
  ('annualized_volatility_20d_pct',(.69,.87,.53,.60),'%')],
}
NUM = r'([+\-−]?\d+(?:\.\d+)?)'
FULL_NUM = re.compile(r'^'+NUM+r'\s*(%|％|天)?$')


def normalized(line,width,height):
    return line['x']/width,line['y']/height


def in_rect(line,rect,width,height):
    x,y=normalized(line,width,height)
    return rect[0]<=x<=rect[1] and rect[2]<=y<=rect[3]


def number(text):
    clean=text.strip().replace(' ','').replace('＋','+')
    clean=re.sub(r'^[▲△▼▽]', '', clean)
    clean=re.sub(r'^(?:A|1)(?=[+-]\d+(?:\.\d+)?[%％]$)', '', clean)
    if re.match(r'^[+-]?0\d',clean): return None
    match=FULL_NUM.fullmatch(clean)
    if not match: return None
    return float(match[1].replace('−','-'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=Path,default=ARCHIVE/'ocr_index.json')
    args=parser.parse_args()
    observations=[]; missing=[]; histograms=[]; texts=defaultdict(list); inventory=[]; image_bases=[]
    for record in json.loads(args.index.read_text())['images']:
        raw=json.loads((ROOT/record['ocr_file']).read_text());w,h=raw['width'],raw['height']
        base={key:record.get(key) for key in ['note_id','date','title','page_kind','image_file','sha256','ocr_file','source_url']}
        printed_date=re.search(r'20\d{2}-\d{2}-\d{2}',raw['text'][:450])
        base['chart_date']=printed_date[0] if printed_date else None
        # Keep exact visible instrument labels, without inferring an ETF ticker from a price.
        banner=[l for l in raw['lines'] if .11<l['y']/h<.19 and l['x']/w<.35]
        banner_names=[l for l in banner if re.fullmatch(r'(?:红利低波(?:100)?|低波100|南方50|南方红利50|中证红利|红利50|红利低波50)',l['text'].strip())]
        scope=re.search(r'本(?:页|图)全部(?:指标)?针对\s*([^·\n]+)',raw['text'])
        if banner_names:
            base['instrument_name']=banner_names[0]['text'].strip()
            base['instrument_evidence']=banner_names[0]['text']
        elif scope:
            base['instrument_name']=scope[1].strip()
            base['instrument_evidence']=scope[0]
        elif record['page_kind']=='cover' and '今日红利低波' in raw['text']:
            base['instrument_name']='红利低波'
            base['instrument_evidence']='今日红利低波'
        else:
            base['instrument_name']=None
            base['instrument_evidence']=None
        image_bases.append(base)
        lines=[dict(line,ocr_pass='full_page') for line in raw['lines']]
        detailfile=ARCHIVE/'ocr_details'/(record['sha256']+'.json')
        if detailfile.exists():
            details=json.loads(detailfile.read_text())
            lines += [dict(line,ocr_pass='enlarged_region') for line in details['lines']]
        # Every source line is retained even if a typed parser does not recognize its layout.
        for line in lines:
            if re.search(r'\d',line['text']): inventory.append({**base,**line,'status':'machine_ocr_unverified'})
        texts[record['note_id']].append({'page_kind':record['page_kind'],'image_file':record['image_file'],
                                       'text':raw['text'],'supplemental_lines':[x['text'] for x in lines if x['ocr_pass']=='enlarged_region']})
        used=set()
        def add(key,value,unit,line,method='layout_and_literal'):
            observations.append({**base,'metric':key,'value':value,'unit':unit,'raw_text':line['text'],
                                 'line_id':line['line_id'],'ocr_pass':line['ocr_pass'],'confidence':line['confidence'],
                                 'box':line['box'],'extraction_method':method,'status':'machine_ocr_unverified'})
            used.add((key,str(line['line_id']),line['ocr_pass']))
        for key,rect,unit in SPECS.get(record['page_kind'],[]):
            if record['page_kind']=='value':
                if rect[2]>.4:
                    anchors=[l['y']/h for l in lines if l['ocr_pass']=='full_page' and l['text'].startswith('滚动PE') and l['y']/h<.6]
                    if anchors: rect=(rect[0],rect[1],min(anchors)+.012,min(anchors)+.055)
                else: rect=(rect[0],rect[1],.23,.32)
            candidates=[line for line in lines if line['ocr_pass']=='full_page' and in_rect(line,rect,w,h) and number(line['text']) is not None]
            if not candidates and record['page_kind']=='position':
                candidates=[line for line in lines if line['ocr_pass']=='enlarged_region' and not line.get('recognition_mode') and in_rect(line,rect,w,h) and number(line['text']) is not None]
            if not candidates:
                candidates=[line for line in lines if line.get('recognition_mode')=='single_numeric_region' and line.get('region')==key and number(line['text']) is not None]
            # Deduplicate repeated passes of a matching value; differing readings remain separate observations.
            groups=defaultdict(list)
            for line in candidates:groups[number(line['text'])].append(line)
            for val,group in groups.items():add(key,val,unit,max(group,key=lambda l:l['confidence']))
            if not candidates:missing.append({**base,'metric':key,'reason':'no_numeric_token_in_expected_region'})
            elif len(groups)>1:missing.append({**base,'metric':key,'reason':'ambiguous_ocr_candidates','values':list(groups)})
        # Named values and dates need literal context, not explanatory constants from elsewhere.
        for line in lines:
            t=line['text'];x,y=normalized(line,w,h);kind=record['page_kind']
            def regex_metric(key,pattern,unit,group=1):
                match=re.search(pattern,t)
                if match:add(key,float(match[group].replace('−','-')),unit,line,'contextual_literal')
            if kind=='value':
                if .26<y<.35:regex_metric('spread_percentile',r'历史百分位\s*'+NUM,'%')
                if .38<y<.48:
                    if x<.35:regex_metric('pe_percentile_10y',r'近10年P\s*(\d+)','percentile')
                    elif x<.65:regex_metric('pb_percentile_10y',r'近10年P\s*(\d+)','percentile')
                    regex_metric('roe_pct',r'ROE\s*'+NUM,'%')
                if .34<y<.45 and '均值' in t:
                    regex_metric('spread_historical_mean_pp',r'均值\s*'+NUM,'pp')
                    regex_metric('spread_historical_min_pp',r'范围\s*'+NUM,'pp')
                    regex_metric('spread_historical_max_pp',r'范围\s*'+NUM+r'\s*[~～至]\s*'+NUM,'pp',2)
                if .44<y<.53 and '@' in t:
                    match=re.search(r'@(\d{4}-\d{2}-\d{2})',t)
                    if match:add('valuation_date_'+('pe' if x<.30 else 'pb' if x<.60 else 'dy'),match[1],'date',line,'contextual_literal')
            if kind=='overview' and .49<y<.57:
                regex_metric('bond_yield_10y_pct',r'10Y\s*'+NUM,'%')
                regex_metric('spread_percentile',r'(?:百分位|P)\s*'+NUM,'percentile')
            if kind=='strength' and .68<y<.72 and x<.45 and not re.search(r'\d',t):
                add('kdj_state_text',t,'text',line)
            if kind=='overview' and .77<y<.80 and not re.search(r'\d',t):
                add('crowding_state_text' if x<.35 else 'bollinger_state_text' if x<.66 else 'position_52w_state_text',t,'text',line)
            if kind=='position' and .59<y<.63 and not re.search(r'\d',t):
                add('volume_ratio_state_text' if x<.40 else 'streak_state_text' if x<.65 else 'volatility_state_text',t,'text',line)
            if kind=='position' and .30<y<.42:
                regex_metric('position_52w_pct',r'^'+NUM+r'%','%')
            if kind=='score':
                if .76<y<.82:
                    for key,label in [('forward_60d_mean_pct','均值'),('forward_60d_median_pct','中位'),('forward_60d_min_pct','最低'),('forward_60d_max_pct','最高')]:
                        regex_metric(key,label+r'\s*'+NUM,'%')
                if .28<y<.35 and x>.14 and x<.85 and not re.search(r'\d',t):
                    add('score_action_text',t,'text',line)
                if .35<y<.40 and x<.18 and re.fullmatch('[A-E]',t):add('score_grade',t,'grade',line)
            if kind in ('cover','overview') and '取数' in t:
                add('data_capture_time',t,'text',line,'contextual_literal')
            if kind=='cover' and y<.35:
                match=re.search(r'([A-E])\s*[·.]?\s*综合评分',t)
                if match:add('score_grade',match[1],'grade',line,'contextual_literal')
            if kind=='cover' and .50<y<.59 and .55<x<.65 and re.fullmatch('[A-E]',t):add('score_grade',t,'grade',line)
            if kind=='overview' and .23<y<.30 and .58<x<.65 and re.fullmatch('[A-E]',t):add('score_grade',t,'grade',line)
            if kind=='strength' and .16<y<.22 and not re.search(r'\d',t):
                add(('rsi_' if x<.50 else 'bias_')+('sentiment_text' if '情绪' in t else 'action_text'),t,'text',line)
        if record['page_kind']=='score':
            crop=[line for line in lines if line.get('region')=='histogram']
            counts=[line for line in crop if re.fullmatch(r'\d{1,4}',line['text']) and .67<line['y']/h<.76 and .08<line['x']/w<.90]
            counts.sort(key=lambda line:line['x'])
            labels=[line for line in lines if line.get('region')=='histogram_range']
            if not labels: labels=[line for line in crop if .75<line['y']/h<.78 and '%' in line['text']]
            labels.sort(key=lambda line:line['x'])
            histogram={**base,'bins':[],'status':'machine_ocr_unverified','count_sum':sum(int(line['text']) for line in counts),'count_count':len(counts)}
            for i,line in enumerate(counts):
                center=line['x']+line['width']/2
                label=min(labels,key=lambda l:abs(l['x']+l['width']/2-center),default=None)
                bounds=re.fullmatch(r'\s*'+NUM+r'\s*[-~～]\s*'+NUM+r'[%％]\s*',label['text']) if label else None
                histogram['bins'].append({'ordinal':i+1,'count':int(line['text']),'count_line':line,
                                          'range_raw':label['text'] if label else None,'range_line':label,
                                          'lower_pct':float(bounds[1]) if bounds else None,
                                          'upper_pct':float(bounds[2]) if bounds else None})
            histograms.append(histogram)
    # Remove duplicate regex observations from full/cropped passes by source + metric + value.
    unique={}
    for obs in observations:
        key=(obs['sha256'],obs['metric'],str(obs['value']))
        if key not in unique or obs['confidence']>unique[key]['confidence']:unique[key]=obs
    observations=list(unique.values())
    override_path=ARCHIVE/'manual_overrides.json'
    if override_path.exists():
        override_data=json.loads(override_path.read_text())
        overrides=override_data.get('overrides',[])+[dict(item,value=None) for item in override_data.get('confirmed_missing',[])]
        for override in overrides:
            def matches(item):
                return item.get('page_kind')==override['page_kind'] and (item.get('note_id')==override['note_id'] if override.get('note_id') else item.get('date')==override['date']) and (not override.get('image_file') or item.get('image_file')==override['image_file'])
            bases=[b for b in image_bases if matches(b)]
            if len(bases)!=1: raise ValueError(f'Manual override must select one image: {override}')
            previous=[o for o in observations if matches(o) and o['metric']==override['metric']]
            observations=[o for o in observations if not (matches(o) and o['metric']==override['metric'])]
            observations.append({**bases[0],'metric':override['metric'],'value':override['value'],
                                 'unit':override.get('unit',previous[0]['unit'] if previous else None),
                                 'raw_text':override.get('raw_text',str(override['value'])),'line_id':None,
                                 'ocr_pass':'manual_visual','confidence':None,'box':override.get('box'),
                                 'extraction_method':'visual_transcription','status':override.get('status','visually_verified'),
                                 'verification_note':override.get('reason'),'previous_ocr_values':previous})
            missing=[m for m in missing if not (matches(m) and m['metric']==override['metric'])]
    histogram_checks=ARCHIVE/'histogram_visual_checks.json'
    if histogram_checks.exists():
        visual={x['sha256']:x for x in json.loads(histogram_checks.read_text())['histograms']}
        for histogram in histograms:
            if histogram['sha256'] in visual:
                checked=visual[histogram['sha256']]
                histogram['previous_ocr_bins']=histogram['bins']
                histogram['bins']=[dict(b,count_line=None,range_line=None,range_raw=b['range_text_verified'],range_raw_provenance='manual_visual_transcription',status='visually_verified') for b in checked['bins']]
                histogram['count_sum']=sum(b['count'] for b in histogram['bins'])
                histogram['count_count']=len(histogram['bins'])
                histogram['status']='visually_verified'
                histogram['verification_method']=checked['method']
                histogram['checked_on']=checked['checked_on']
    dump(ARCHIVE/'metrics_long.json',{'version':'layout-extraction-v1','observations':observations,'missing_or_ambiguous':missing})
    dump(ARCHIVE/'histograms.json',{'histograms':histograms,'note':'range_text_verified与lower/upper_pct是逐图目视核验值；previous_ocr_bins保留原始机器识别。后续新图片没有视觉记录时仍标machine_ocr_unverified。'})
    dump(ARCHIVE/'numeric_line_inventory.json',{'lines':inventory})
    dump(ARCHIVE/'note_texts.json',{'notes':[{'note_id':note,'pages':pages} for note,pages in texts.items()]})
    out=ARCHIVE/'texts';out.mkdir(exist_ok=True)
    for note,pages in texts.items():
        text='\n\n'.join(f"=== {p['page_kind']} | {p['image_file']} ===\n{p['text']}\n[局部放大OCR]\n"+'\n'.join(p['supplemental_lines']) for p in pages)
        (out/(note+'.txt')).write_text(text+'\n',encoding='utf-8')
    print(json.dumps({'notes':len(texts),'observations':len(observations),'histograms':len(histograms),'unresolved':len(missing),'numeric_lines':len(inventory)},ensure_ascii=False))

if __name__=='__main__':main()
