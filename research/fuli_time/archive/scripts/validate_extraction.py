#!/usr/bin/env python3
"""Check extracted transcription consistency without silently correcting source values."""
from collections import defaultdict,Counter
import json
from ocr_images import ARCHIVE,dump


def main():
    data=json.loads((ARCHIVE/'metrics_long.json').read_text());observations=data['observations']
    groups=defaultdict(list);anomalies=[{'type':'body_attachment_claim_not_observed','date':'2026-09-30','note':'正文称附南方50/低波100；浏览器确认原帖共7图，当前可见七图均为红利低波。不据正文伪造附图或数据。','status':'browser_and_image_observation'}]
    for obs in observations:groups[(obs['note_id'],obs.get('instrument_name'),obs['metric'])].append(obs)
    for (note,instrument,metric),values in groups.items():
        numeric=[v for v in values if isinstance(v['value'],(int,float))]
        unique=set(v['value'] for v in numeric)
        if len(unique)>1:
            anomalies.append({'type':'cross_page_numeric_disagreement','note_id':note,'instrument_name':instrument,
                              'metric':metric,'values':numeric})
    by_note=defaultdict(list)
    for obs in observations:by_note[(obs['note_id'],obs.get('instrument_name'))].append(obs)
    for (note,instrument),items in by_note.items():
        precise=[x for x in items if x['metric']=='score_precise']
        rounded=[x for x in items if x['metric']=='score_rounded']
        grades=[x for x in items if x['metric']=='score_grade']
        for score in precise:
            for rounded_score in rounded:
                if abs(score['value']-rounded_score['value'])>.6:
                    anomalies.append({'type':'score_precision_disagreement','note_id':note,'instrument_name':instrument,'values':[score,rounded_score]})
            expected='E' if score['value']<25 else 'D' if score['value']<40 else 'C' if score['value']<55 else 'B' if score['value']<70 else 'A'
            for grade in grades:
                if grade['value']!=expected:
                    anomalies.append({'type':'grade_differs_from_printed_common_thresholds','note_id':note,'instrument_name':instrument,
                                      'expected_by_thresholds':expected,'values':[score,grade],
                                      'note':'Flag only; source grade retained. Check this page’s visible threshold legend before correction.'})
    histograms=json.loads((ARCHIVE/'histograms.json').read_text())['histograms']
    for hist in histograms:
        samples=[x for x in observations if x['sha256']==hist['sha256'] and x['metric']=='same_score_samples']
        hist['sample_sum_matches'] = bool(len(samples)==1 and hist['count_sum']==samples[0]['value'])
        bounds=[(b.get('lower_pct'),b.get('upper_pct')) for b in hist['bins']]
        boundaries_ok=bool(bounds) and all(lo is not None and hi is not None and lo<hi for lo,hi in bounds)
        if boundaries_ok:
            boundaries_ok=all(abs(bounds[i][1]-bounds[i+1][0])<.011 for i in range(len(bounds)-1))
        if not boundaries_ok:
            anomalies.append({'type':'histogram_bin_boundaries_unresolved','note_id':hist['note_id'],'date':hist['date'],
                              'image_file':hist['image_file'],'bounds':bounds})
        if hist['count_count']!=7 or not hist['sample_sum_matches']:
            anomalies.append({'type':'histogram_count_incomplete_or_mismatch','note_id':hist['note_id'],'date':hist['date'],
                              'image_file':hist['image_file'],'count_count':hist['count_count'],'count_sum':hist['count_sum'],
                              'sample_values':[x['value'] for x in samples]})
    summary={'observation_count':len(observations),'note_count_with_metrics':len(set(x['note_id'] for x in observations)),
             'instruments':dict(Counter(x.get('instrument_name') for x in observations)),
             'missing_or_ambiguous_count':len(data['missing_or_ambiguous']),
             'source_not_reported_count':sum(o.get('status')=='source_not_reported' for o in observations),
             'histogram_count':len(histograms),'histograms_sum_verified':sum(x['sample_sum_matches'] for x in histograms),
             'anomaly_counts':dict(Counter(x['type'] for x in anomalies))}
    dump(ARCHIVE/'extraction_quality.json',{'summary':summary,'anomalies':anomalies,'missing_or_ambiguous':data['missing_or_ambiguous']})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
