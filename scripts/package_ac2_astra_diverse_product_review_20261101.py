"""Prepare blinded-to-automatic-score reviews, including missing-run accounting."""
import hashlib
import json
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/ac2-astra-diverse-product-20261101-v1'
summary=json.loads((OUT/'summary.json').read_text())
source=json.loads((ROOT/'output/proposal-delivery/ac2-prospective-new-histories-20261029/histories.json').read_text())
byid={x['conversation_id']:x for x in source['conversations']}
items=[]
for run in summary['runs']:
    path=OUT/(run['history_id']+'.json');raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=run['record_sha256']:raise SystemExit('Run record changed')
    entry=json.loads(raw);messages=byid[run['history_id']]['messages']
    review=next((r['response'] for r in entry['requests'] if r['path'].endswith('/test-review') and r['status']=='returned'),None)
    if not review: continue
    for test in review.get('tests',[]):
        items.append({'history_id':run['history_id'],'test_id':test['test_id'],'source_messages':messages,
            'dimension':test['dimension'],'question':test['prompt'],'expected_behavior':test['expected_behavior'],
            'source_grounding':'','question_executability':'','reference_answer_validity':'','review_note':''})
if not items: raise SystemExit('No generated questions to review')
if len({(x['history_id'],x['test_id']) for x in items})!=len(items):raise SystemExit('Duplicate test identity')
random.Random(20261104).shuffle(items)
for n in (1,2):
    dest=OUT/f'question-ai-reviewer-{n}-blank.json'
    if dest.exists():raise SystemExit('Existing packet retained')
    dest.write_text(json.dumps({'reviewer':f'ai-reviewer-{n}',
        'instructions':'Source-only AI question review; no automatic quality results. Each field must be valid, invalid or uncertain. Missing questions remain missing.',
        'items':items},ensure_ascii=False,indent=2)+'\n')
print('Prepared',len(items),'questions from',len({x['history_id'] for x in items}),'histories; planned slots',summary['requested_max_questions'])
