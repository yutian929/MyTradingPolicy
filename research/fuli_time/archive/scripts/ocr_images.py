#!/usr/bin/env python3
"""OCR only explicitly manifested chart images, retaining source and uncertainty.

Usage: .venv/bin/python research/fuli_time/archive/scripts/ocr_images.py \
  --manifest research/fuli_time/archive/source_manifest.json
No network access. Cached by image SHA-256 plus extraction version.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

VERSION = 'rapidocr-layout-v1'
ROOT = Path(__file__).resolve().parents[4]
ARCHIVE = ROOT / 'research/fuli_time/archive'
RAW = ROOT / 'data/raw/fuli_time_archive'


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def page_kind(text: str) -> str:
    for token, kind in [('HERO', 'cover'), ('OVERVIEW', 'overview'), ('STRENGTH', 'strength'),
                        ('PRICE', 'price'), ('VALUE', 'value'), ('SCORE', 'score'), ('POSITION', 'position')]:
        if token in text[:250].upper():
            return kind
    return 'other'


def normalize_notes(raw):
    if isinstance(raw, dict):
        raw = raw.get('notes', raw.get('sources', []))
    for note in raw:
        note = dict(note)
        note['note_id'] = note.get('note_id', note.get('id'))
        if not note['note_id']:
            raise ValueError('Every note requires note_id or id')
        if not note.get('date'):
            match = re.search(r'(2026)[.\-/](\d{1,2})[.\-/](\d{1,2})', note.get('title', ''))
            note['date'] = '-'.join([match[1], match[2].zfill(2), match[3].zfill(2)]) if match else None
        yield note


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ARCHIVE / 'source_manifest.json')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--note-id', action='append')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    notes = list(normalize_notes(json.loads(args.manifest.read_text(encoding='utf-8'))))
    if args.note_id:
        notes = [n for n in notes if n['note_id'] in args.note_id]
    if args.limit is not None:
        notes = notes[:args.limit]
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR(intra_op_num_threads=args.threads, inter_op_num_threads=1, det_limit_side_len=1200)
    ocr_dir = ARCHIVE / 'ocr'
    records, failures = [], []
    for note in notes:
        files = note.get('files', note.get('images', []))
        for index, entry in enumerate(files):
            path = Path(entry if isinstance(entry, str) else entry['path'])
            if not path.is_absolute():
                path = ROOT / path
            try:
                content = path.read_bytes()
                sha = hashlib.sha256(content).hexdigest()
                dest = RAW / note['note_id'] / (sha[:16] + path.suffix.lower())
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copyfile(path, dest)
                cache = ocr_dir / (sha + '.json')
                if cache.exists() and not args.force:
                    result = json.loads(cache.read_text(encoding='utf-8'))
                    if result.get('version') != VERSION:
                        raise ValueError(f'Cache version differs: {cache}; use --force')
                else:
                    started = time.monotonic()
                    extracted, timings = engine(str(dest))
                    with Image.open(dest) as img:
                        size = img.size
                    lines = []
                    for i, (box, text, confidence) in enumerate(extracted or []):
                        xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
                        lines.append({'line_id': i, 'text': text, 'confidence': float(confidence),
                                      'box': box, 'x': min(xs), 'y': min(ys),
                                      'width': max(xs)-min(xs), 'height': max(ys)-min(ys)})
                    text = '\n'.join(line['text'] for line in lines)
                    page = re.search(r'(?m)^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$', text)
                    result = {'version': VERSION, 'sha256': sha, 'width': size[0], 'height': size[1],
                              'page_kind': page_kind(text),
                              'printed_page_number': int(page[1]) if page else None,
                              'printed_page_total': int(page[2]) if page else None,
                              'text': text, 'lines': lines,
                              'low_confidence_line_count': sum(line['confidence'] < .90 for line in lines),
                              'elapsed_seconds': round(time.monotonic()-started, 3),
                              'status': 'machine_ocr_unverified'}
                    dump(cache, result)
                record = {'note_id': note['note_id'], 'date': note.get('date'), 'title': note.get('title'),
                          'source_url': note.get('url', 'https://www.xiaohongshu.com/explore/'+note['note_id']),
                          'download_index': index, 'sha256': sha, 'source_file': str(path),
                          'image_file': str(dest.relative_to(ROOT)), 'ocr_file': str(cache.relative_to(ROOT)),
                          'page_kind': result['page_kind'], 'printed_page_number': result['printed_page_number'],
                          'printed_page_total': result['printed_page_total'], 'line_count': len(result['lines']),
                          'low_confidence_line_count': result['low_confidence_line_count'],
                          'status': result['status']}
                records.append(record)
                print(json.dumps({'note_id':note['note_id'],'image':index+1,'kind':result['page_kind'],
                                  'lines':len(result['lines']), 'seconds':result['elapsed_seconds']},ensure_ascii=False),flush=True)
            except Exception as exc:
                failure = {'note_id':note['note_id'],'source_file':str(path),'error':f'{type(exc).__name__}: {exc}'}
                failures.append(failure)
                print(json.dumps(failure,ensure_ascii=False),flush=True)
        # Checkpoint after every note so interrupted long runs lose no OCR work.
        dump(ARCHIVE / 'ocr_index.json', {'version':VERSION,'manifest':str(args.manifest), 'images':records,'failures':failures})
    with (ARCHIVE / 'ocr_lines.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        fields = ['note_id','date','page_kind','page_number','image_file','line_id','text','confidence','x','y','width','height']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            result = json.loads((ROOT / record['ocr_file']).read_text())
            for line in result['lines']:
                writer.writerow({'note_id':record['note_id'],'date':record['date'],'page_kind':record['page_kind'],
                                 'page_number':record['printed_page_number'],'image_file':record['image_file'],
                                 **{k:line[k] for k in ['line_id','text','confidence','x','y','width','height']}})
    print(json.dumps({'notes':len(notes),'images':len(records),'failures':len(failures)},ensure_ascii=False),flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
