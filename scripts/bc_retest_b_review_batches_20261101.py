"""Create immutable compact B review batches without scores or policy identity."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2/B'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def opaque(value):return hashlib.sha256(value.encode()).hexdigest()[:20]
def write(p,value):
    with Path(p).open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def create(limit):
    frozen=read(OUT/'sources.json')['sources'];protocol_sha=sha(OUT/'protocol.json')
    sources=[];questions=[];qids={}
    for h in frozen:
        sid='S'+opaque(h['history_id'])
        sources.append({'source_id':sid,'statements':h['messages']})
        for q in h['questions']:
            signature=(q['dimension'],q['prompt'],q['expected_behavior'])
            qid='Q'+opaque(json.dumps([sid,*signature],ensure_ascii=False))
            qids[(h['history_id'],signature)]=qid
            questions.append({'question_id':qid,'source_id':sid,'dimension':q['dimension'],
                'question':q['prompt'],'expected_behavior':q['expected_behavior']})
    private_dir=OUT/'private-review-batches';private_dir.mkdir(exist_ok=True)
    public_dir=OUT/'blind-review';public_dir.mkdir(exist_ok=True)
    seen=set()
    for p in private_dir.glob('compact-batch-*.private-key.json'):
        seen.update(x['review_id'] for x in read(p)['mapping'])
    available=[]
    for p in sorted((OUT/'executions').glob('*.json')):
        d=read(p)
        tests=next((o['response'] for o in d['operations'] if o['path'].endswith('/tests') and o.get('state')=='returned'),[])
        byid={t['test_id']:t for t in tests}
        answers=next((o['response'] for o in d['operations'] if o['path'].endswith('/execute') and o.get('state')=='returned'),None)
        if answers is None:
            answers=next((o['response'] for o in d['operations'] if o['path'].endswith('/responses') and o.get('state')=='returned'),[])
        for a in answers:
            if a['test_id'] not in byid:continue
            review_id=opaque(protocol_sha+a['response_id'])
            if review_id in seen:continue
            q=byid[a['test_id']];signature=(q['dimension'],q['prompt'],q['expected_behavior'])
            item={'review_id':review_id,'question_id':qids[(d['history_id'],signature)],
                'answer':a['response_text'],'question_validity':None,'reference_validity':None,
                'strict_answer_verdict':None,'safe_but_incomplete':None,'reason':None}
            key={'review_id':review_id,'history_id':d['history_id'],'strategy':d['strategy'],
                 'repetition':d['repetition'],'run_id':d['run_id'],'test_id':a['test_id'],
                 'response_id':a['response_id']}
            available.append((review_id,item,key))
    chosen=sorted(available)[:limit]
    if not chosen:
        print(json.dumps({'created':False,'new_answers':0}));return
    index=1+len(list(private_dir.glob('compact-batch-*.private-key.json')))
    name=f'compact-batch-{index:03d}'
    rubric={'question_validity':'valid / invalid / uncertain: is the question answerable from authorised sources and unambiguous?',
        'reference_validity':'valid / invalid / uncertain: does the exact frozen expected_behavior follow from source statements?',
        'strict_answer_verdict':'pass / fail / uncertain. Strict pass requires every factual/behavioural requirement in the frozen expected_behavior and the prompt. Do not loosen the historical reference requirements to improve rates. Use uncertain for source/reference ambiguity; do not silently drop cases.',
        'safe_but_incomplete':'Separate boolean supplementary label. True for safe clarification/abstention or partly correct facts that omit a required reference component; this remains strict fail, not strict pass.',
        'objectivity':'Review sources, reference and actual answer independently. Do not consult automatic judgments, another reviewer, policy identity or run summaries. Repeated answers are measurements, not new histories.'}
    public={'format':'b-reader-retest-compact-independent-review-v1','protocol_sha256':protocol_sha,
        'rubric':rubric,'sources':sources,'questions':questions,'items':[x[1] for x in chosen]}
    dest=public_dir/(name+'.json');write(dest,public)
    key=private_dir/(name+'.private-key.json');write(key,{'public_sha256':sha(dest),'mapping':[x[2] for x in chosen]})
    print(json.dumps({'created':True,'items':len(chosen),'public':str(dest),'private':str(key)},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=64);a=p.parse_args();create(a.limit)
