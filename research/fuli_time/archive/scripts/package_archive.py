"""Package the explicit evidence corpus; excludes unrelated downloads and credentials."""
import json,zipfile,shutil,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
A=ROOT/'research/fuli_time/archive'; OUT=ROOT/'outputs/fuli_time_archive'
shutil.copyfile(A/'README.txt',OUT/'README.txt')
for name in ['coverage.json','metric_dictionary.json','extraction_quality.json','body_image_audit.json','body_image_differences.csv']:
    if (A/name).exists():shutil.copyfile(A/name,OUT/name)
images=json.loads((A/'ocr_index.json').read_text())['images']
files=set()
for p in A.rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts and p.name not in ['sample_manifest.json'] and p.suffix not in ['.log','.tmp']:
        files.add(p)
for im in images:files.add(ROOT/im['image_file'])
for p in OUT.rglob('*'):
    if p.is_file() and p.suffix in ['.xlsx','.csv','.json','.txt'] and not p.name.startswith('package_'):
        files.add(p)
target=OUT/'fuli_time_20260901_20261106.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(files):z.write(p,p.relative_to(ROOT))
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert len([n for n in z.namelist() if n.endswith('.webp')])==274
    assert any(n.endswith('.xlsx') for n in z.namelist())
meta={'file':target.name,'files':len(files),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(OUT/'package_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(meta,ensure_ascii=False))
