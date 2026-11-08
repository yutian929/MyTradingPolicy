#!/usr/bin/env python3
"""Supplement full-page OCR with enlarged source-bound chart regions (no network)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from ocr_images import ROOT, ARCHIVE, dump

REGIONS = {
    'score': {'histogram': (.06, .65, .94, .81)},
    'position': {'daily_values': (.15, .52, .88, .63)},
    'overview': {},
}
NUMERIC_REGIONS = {
    'score': {'score_precise': (.05,.29,.19,.36), 'daily_return_pct': (.14,.402,.35,.435)},
    'overview': {'score_rounded': (.505,.252,.584,.290), 'crowding': (.155,.745,.25,.78), 'position_52w_pct': (.765,.745,.85,.78)},
    'position': {'streak': (.44,.545,.60,.592)},
}
VERSION = 'rapidocr-crops-v1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ARCHIVE/'ocr_index.json')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    from rapidocr_onnxruntime import RapidOCR
    from PIL import Image
    import numpy as np
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, det_limit_side_len=2000)
    records = []
    for image in json.loads(args.index.read_text())['images']:
        regions = REGIONS.get(image['page_kind'], {})
        if not regions and image['page_kind'] not in NUMERIC_REGIONS:
            continue
        dest = ARCHIVE/'ocr_details'/(image['sha256']+'.json')
        if dest.exists() and not args.force:
            result = json.loads(dest.read_text())
        else:
            started = time.monotonic()
            with Image.open(ROOT/image['image_file']) as source:
                width, height = source.size
                lines = []
                for region, bounds in regions.items():
                    left, top, right, bottom = [int(v*(width if i%2==0 else height)) for i,v in enumerate(bounds)]
                    crop = source.crop((left, top, right, bottom)).convert('RGB')
                    crop = crop.resize((crop.width*3, crop.height*3))
                    extracted, _ = engine(np.asarray(crop))
                    for i, (box, text, confidence) in enumerate(extracted or []):
                        box = [[float(p[0])/3+left, float(p[1])/3+top] for p in box]
                        xs, ys = [p[0] for p in box], [p[1] for p in box]
                        lines.append({'line_id':f'{region}:{i}','region':region,'text':text,'confidence':float(confidence),
                                      'box':box,'x':min(xs),'y':min(ys),'width':max(xs)-min(xs),'height':max(ys)-min(ys)})
                result = {'version':VERSION,'sha256':image['sha256'],'width':width,'height':height,
                          'lines':lines,'status':'machine_ocr_unverified','seconds':round(time.monotonic()-started,3)}
                dump(dest,result)
        if not result.get('numeric_complete_v3'):
            result['lines']=[l for l in result['lines'] if l.get('recognition_mode')!='single_numeric_region']
            with Image.open(ROOT/image['image_file']) as source:
                width,height=source.size
                full=json.loads((ROOT/image['ocr_file']).read_text())
                for region,bounds in NUMERIC_REGIONS.get(image['page_kind'],{}).items():
                    bounds=list(bounds)
                    if region=='score_precise':
                        actions=[l['x']/width for l in full['lines'] if .275<l['y']/height<.295 and .14<l['x']/width<.30]
                        if actions: bounds[2]=min(actions)-.008
                    left,top,right,bottom=[int(v*(width if i%2==0 else height)) for i,v in enumerate(bounds)]
                    if region=='daily_return_pct':
                        candidates=[l for l in full['lines'] if .40<l['y']/height<.44 and .14<l['x']/width<.35 and any(c.isdigit() for c in l['text'])]
                        if len(candidates)==1:
                            l=candidates[0];left,top=int(l['x'])-4,int(l['y'])-3
                            right,bottom=int(l['x']+l['width'])+4,int(l['y']+l['height'])+3
                    crop=source.crop((left,top,right,bottom)).convert('RGB')
                    crop=crop.resize((crop.width*3,crop.height*3))
                    recognized,_=engine(np.asarray(crop),use_det=False,use_cls=False)
                    if recognized:
                        text,confidence=recognized[0]
                        result['lines'].append({'line_id':f'numeric:{region}','region':region,'recognition_mode':'single_numeric_region',
                            'text':text,'confidence':float(confidence),'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                            'x':left,'y':top,'width':right-left,'height':bottom-top})
            result['numeric_complete_v3']=True
            dump(dest,result)
        if image['page_kind']=='score' and not result.get('histogram_ranges_refined'):
            with Image.open(ROOT/image['image_file']) as source:
                width,height=source.size
                labels=[l for l in result['lines'] if l.get('region')=='histogram' and .75<l['y']/height<.78 and '%' in l['text']]
                for index,label in enumerate(labels):
                    left,top=int(label['x'])-3,int(label['y'])-2
                    right,bottom=int(label['x']+label['width'])+3,int(label['y']+label['height'])+2
                    crop=source.crop((left,top,right,bottom)).convert('RGB')
                    crop=crop.resize((crop.width*5,crop.height*5))
                    recognized,_=engine(np.asarray(crop),use_det=False,use_cls=False)
                    if recognized:
                        text,confidence=recognized[0]
                        result['lines'].append({'line_id':f'histogram_range:{index}','region':'histogram_range','recognition_mode':'single_range_text',
                            'text':text,'confidence':float(confidence),'box':[[left,top],[right,top],[right,bottom],[left,bottom]],
                            'x':left,'y':top,'width':right-left,'height':bottom-top,'source_line_id':label['line_id']})
            result['histogram_ranges_refined']=True
            dump(dest,result)
        records.append({'note_id':image['note_id'],'date':image['date'],'page_kind':image['page_kind'],
                        'image_file':image['image_file'],'ocr_details_file':str(dest.relative_to(ROOT)),
                        'line_count':len(result['lines'])})
        print(json.dumps(records[-1],ensure_ascii=False),flush=True)
    dump(ARCHIVE/'ocr_details_index.json', {'version':VERSION,'images':records})


if __name__ == '__main__':
    main()
