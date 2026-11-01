"""Prepare source-grounded extraction reviews; never supply results as human gold."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/astra-ac1-reference-pilot-20261101-v2'
histories=json.loads((OUT/'reference-and-sources.json').read_text())['histories']
pack=[]
for h in histories:
    path=OUT/(h['history_id']+'-extraction.json')
    raw=path.read_bytes();entry=json.loads(raw)
    if entry['status']!='completed_reference_review_pending': raise SystemExit(f'Incomplete: {path.name}')
    extracted=next(x['response'] for x in entry['operations'] if x['path'].endswith('/extract') and x['state']=='returned')
    pack.append({'history_id':h['history_id'],'source_messages':h['source_messages'],
        'reviewed_reference':h['reviewed_reference'],'extracted_candidates':extracted,
        'extraction_sha256':hashlib.sha256(raw).hexdigest(),
        'review':{'candidates':[], 'reference_facts':[], 'extracted_relationships':[], 'reference_relationships':[], 'note':''}})
for n in (1,2):
    path=OUT/f'extraction-reviewer-{n}-blank.json'
    if path.exists(): raise SystemExit('Existing review packet retained')
    path.write_text(json.dumps({'reviewer':f'ai-reviewer-{n}', 'scope':'Source-grounded AI review; not human review or a population estimate.', 'histories':pack},ensure_ascii=False,indent=2)+'\n')
print('Prepared two independent AI review packets')
