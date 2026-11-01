"""Create condition-blinded review packets from the frozen four-history study."""
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/astra-writer-four-prospective-20261101-v1'
SOURCE = ROOT / 'output/proposal-delivery/ac2-astra-product-four-source-20261101-v1/ledger.json'
source = {h['id']: h for h in json.loads(SOURCE.read_text())['histories']}
rows, mapping, hashes = [], {}, {}
for path in sorted(OUT.glob('FS*-execution.json')):
    raw = path.read_bytes()
    run = json.loads(raw)
    if run['status'] != 'completed_human_review_pending':
        raise SystemExit(f'Incomplete: {path.name}')
    hashes[path.name] = hashlib.sha256(raw).hexdigest()
    messages = next(r['body']['messages'] for r in source[run['history_id']]['requests'] if r['path'] == '/conversations' and r['method'] == 'POST')
    tests = [x['response'] for x in run['operations'] if x['method'] == 'GET' and x['path'].endswith('/tests') and x['state'] == 'returned']
    answers = [x['response'] for x in run['operations'] if x['method'] == 'POST' and x['path'].endswith('/execute') and x['state'] == 'returned']
    if len(tests) != 2 or len(answers) != 2:
        raise SystemExit(f'Incomplete conditions: {path.name}')
    signature = lambda t: (t['dimension'], t['prompt'], t['expected_behavior'], tuple(sorted(t['supporting_memory_ids'])))
    canonical = {signature(t): t for t in tests[0]}
    if len(canonical) != 4 or set(canonical) != {signature(t) for t in tests[1]}:
        raise SystemExit('Questions differ across conditions')
    for condition, ts, responses in zip(('baseline', 'candidate'), tests, answers):
        by_id = {t['test_id']: t for t in ts}
        if len(responses) != 4 or {a['test_id'] for a in responses} != set(by_id):
            raise SystemExit('Response mismatch')
        for a in responses:
            t = by_id[a['test_id']]
            rid = hashlib.sha256((run['history_id'] + ':' + condition + ':' + a['response_id']).encode()).hexdigest()[:16]
            rows.append({'review_id': rid, 'source_messages': messages, 'question': t['prompt'], 'expected_behavior': t['expected_behavior'], 'target_answer': a['response_text'], 'question_validity': '', 'answer_verdict': '', 'failure_category': '', 'note': ''})
            mapping[rid] = {'condition': condition, 'history_id': run['history_id'], 'source_test_id': canonical[signature(t)]['test_id'], 'dimension': t['dimension'], 'response_id': a['response_id']}
if len(rows) != 32 or len(mapping) != 32:
    raise SystemExit('Expected 32 unique answers')
random.Random(20261103).shuffle(rows)
for n in (1, 2):
    p = OUT / f'four-writer-ai-reviewer-{n}-blank.json'
    if p.exists():
        raise SystemExit(f'Preserving existing {p}')
    p.write_text(json.dumps({'reviewer': f'ai-reviewer-{n}', 'scope': 'AI review of answers without condition or automatic verdict', 'items': rows}, ensure_ascii=False, indent=2) + '\n')
(OUT / 'four-writer-private-key.json').write_text(json.dumps({'execution_sha256': hashes, 'mapping': mapping}, indent=2) + '\n')
print('Prepared 32 blinded answers for each reviewer')
