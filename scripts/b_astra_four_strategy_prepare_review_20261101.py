"""Blind strategy identity and automatic scores for independent answer review."""
import hashlib,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/proposal-delivery/b-astra-four-strategy-20261101-v1'
SOURCE=ROOT/'output/proposal-delivery/ac2-astra-product-four-source-20261101-v1/ledger.json'
source={x['id']:x for x in json.loads(SOURCE.read_text())['histories']};items=[];mapping={};runs={}
protocol=json.loads((OUT/'protocol.json').read_text());histories={h['history_id']:h for h in protocol['histories']}
for f in sorted(OUT.glob('FS*-execution.json')):
    raw=f.read_bytes();state=json.loads(raw);runs[f.name]=hashlib.sha256(raw).hexdigest()
    messages=next(x['body']['messages'] for x in source[state['history_id']]['requests'] if x['path']=='/conversations' and x['method']=='POST')
    for c in state['conditions']:
        if c['status']!='completed_review_pending':continue
        tests=next(x['response'] for x in c['operations'] if x['path'].endswith('/tests') and x['state']=='returned')
        answers=next(x['response'] for x in c['operations'] if x['path'].endswith('/execute') and x['state']=='returned')
        byid={t['test_id']:t for t in tests}
        if len(tests)!=4 or len(answers)!=4 or {a['test_id'] for a in answers}!=set(byid):raise ValueError('Incomplete answer-test mapping')
        for answer in answers:
            test=byid[answer['test_id']];rid=hashlib.sha256((state['history_id']+':'+c['strategy']+':'+answer['response_id']).encode()).hexdigest()[:16]
            items.append({'review_id':rid,'source_messages':messages,'question':test['prompt'],'expected_behavior':test['expected_behavior'],
                'target_answer':answer['response_text'],'question_validity':'','answer_verdict':'','failure_category':'','note':''})
            original=[q for q in histories[state['history_id']]['questions'] if q['dimension']==test['dimension'] and q['prompt']==test['prompt'] and q['expected_behavior']==test['expected_behavior']]
            if len(original)!=1:raise ValueError('Could not map source question')
            mapping[rid]={'history_id':state['history_id'],'strategy':c['strategy'],'source_test_id':original[0]['test_id'],
                          'dimension':test['dimension'],'test_id':test['test_id'],'response_id':answer['response_id']}
if len(items)!=len(mapping) or not items:raise SystemExit('Missing or duplicated answer IDs')
random.Random(20261106).shuffle(items)
for n in (1,2):
    path=OUT/f'ai-reviewer-{n}-blank.json'
    if path.exists():raise SystemExit('Existing review retained')
    path.write_text(json.dumps({'reviewer':f'ai-reviewer-{n}','scope':'Blinded AI review; no strategy or automatic verdict shown.','items':items},ensure_ascii=False,indent=2)+'\n')
(OUT/'private-review-key.json').write_text(json.dumps({'runs_sha256':runs,'mapping':mapping},indent=2)+'\n')
print('Prepared',len(items),'answers for each reviewer. Planned: 64.')
