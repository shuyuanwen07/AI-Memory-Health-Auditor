"""Blind both source and candidate answers for independent review."""
import hashlib,json,random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/astra-product-end-to-end-20261101-v1'
old_raw=(OUT/'ledger.json').read_bytes();new_raw=(OUT/'retrieval-followup-ledger.json').read_bytes()
old=json.loads(old_raw)['histories'][0];new=json.loads(new_raw)
if new['status']!='completed_human_review_pending':raise SystemExit('Retest incomplete')
def old_get(s):return next(x['response'] for x in old['requests'] if x['path'].endswith(s) and x['state']=='returned')
def new_get(s):return next(x['response'] for x in new['operations'] if x['path'].endswith(s) and x['state']=='returned')
old_tests=old_get('/test-review')['tests'];new_tests=new_get('/tests');old_answers=old_get('/execute');new_answers=new_get('/execute')
signature=lambda x:(x['dimension'],x['prompt'],x['expected_behavior'],tuple(sorted(x['supporting_memory_ids'])))
orig={t['test_id']:t for t in old_tests};copies={t['test_id']:t for t in new_tests};canonical={signature(t):t for t in old_tests}
if len(canonical)!=4 or {signature(t) for t in new_tests}!=set(canonical):raise SystemExit('Question evidence does not pair uniquely')
sources=next(x['body']['messages'] for x in old['requests'] if x['path']=='/conversations' and x['method']=='POST')
rows=[];key={}
for condition,tests,answers in [('baseline',orig,old_answers),('candidate',copies,new_answers)]:
    for a in answers:
        t=tests[a['test_id']];base=canonical[signature(t)];rid=hashlib.sha256((condition+':'+a['response_id']).encode()).hexdigest()[:16]
        rows.append({'review_id':rid,'source_messages':sources,'question':t['prompt'],'expected_behavior':t['expected_behavior'],
                     'target_answer':a['response_text'],'question_validity':'','answer_verdict':'','failure_category':'','note':''})
        key[rid]={'condition':condition,'source_test_id':base['test_id'],'dimension':t['dimension'],'response_id':a['response_id']}
if len(rows)!=8 or len(key)!=8:raise SystemExit('Expected eight unique answer rows')
random.Random(20261101).shuffle(rows)
info={'scope':'Blind independent review of 8 answers; no strategy, condition, dimension or automatic outcome is provided. AI assistance must be declared.','items':rows}
for n in (1,2):
    p=OUT/f'retrieval-followup-ai-reviewer-{n}-blank.json'
    if p.exists():raise SystemExit('Existing review packet preserved')
    p.write_text(json.dumps({**info,'reviewer':f'ai-reviewer-{n}'},ensure_ascii=False,indent=2)+'\n')
(OUT/'retrieval-followup-private-key.json').write_text(json.dumps({'prior_ledger_sha256':hashlib.sha256(old_raw).hexdigest(),'followup_ledger_sha256':hashlib.sha256(new_raw).hexdigest(),'mapping':key},indent=2)+'\n')
print('Prepared 8 blinded rows for two AI reviews')
