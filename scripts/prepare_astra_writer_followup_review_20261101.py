"""Blind the retrieval-only and retrieval-plus-writer answers for review."""
import hashlib,json,random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/proposal-delivery/astra-product-end-to-end-20261101-v1'
base_raw=(OUT/'retrieval-followup-ledger.json').read_bytes();new_raw=(OUT/'writer-followup-ledger.json').read_bytes()
base=json.loads(base_raw);new=json.loads(new_raw);source=json.loads((OUT/'ledger.json').read_bytes())['histories'][0]
if base['status']!='completed_human_review_pending' or new['status']!='completed_human_review_pending':raise SystemExit('A comparison run is incomplete')
def get(d,s):return next(x['response'] for x in d['operations'] if x['path'].endswith(s) and x['state']=='returned')
bt=get(base,'/tests');nt=get(new,'/tests');ba=get(base,'/execute');na=get(new,'/execute')
signature=lambda x:(x['dimension'],x['prompt'],x['expected_behavior'],tuple(sorted(x['supporting_memory_ids'])))
canonical={signature(t):t for t in bt}
if len(canonical)!=4 or {signature(t) for t in nt}!=set(canonical):raise SystemExit('Question evidence differs')
source_messages=next(x['body']['messages'] for x in source['requests'] if x['path']=='/conversations' and x['method']=='POST')
items=[];mapping={}
for condition,tests,answers in [('baseline',bt,ba),('candidate',nt,na)]:
    byid={t['test_id']:t for t in tests}
    for a in answers:
        t=byid[a['test_id']];original=canonical[signature(t)];rid=hashlib.sha256((condition+':'+a['response_id']).encode()).hexdigest()[:16]
        items.append({'review_id':rid,'source_messages':source_messages,'question':t['prompt'],'expected_behavior':t['expected_behavior'],
                      'target_answer':a['response_text'],'question_validity':'','answer_verdict':'','failure_category':'','note':''})
        mapping[rid]={'condition':condition,'source_test_id':original['test_id'],'dimension':t['dimension'],'response_id':a['response_id']}
if len(items)!=8 or len(mapping)!=8:raise SystemExit('Expected eight unique answers')
random.Random(20261102).shuffle(items)
for n in (1,2):
    p=OUT/f'writer-followup-ai-reviewer-{n}-blank.json'
    if p.exists():raise SystemExit('Existing packet retained')
    p.write_text(json.dumps({'reviewer':f'ai-reviewer-{n}','scope':'Blind AI answer review; no condition or automatic verdict supplied.','items':items},ensure_ascii=False,indent=2)+'\n')
(OUT/'writer-followup-private-key.json').write_text(json.dumps({'baseline_ledger_sha256':hashlib.sha256(base_raw).hexdigest(),'candidate_ledger_sha256':hashlib.sha256(new_raw).hexdigest(),'mapping':mapping},indent=2)+'\n')
print('Prepared eight blinded answer rows')
