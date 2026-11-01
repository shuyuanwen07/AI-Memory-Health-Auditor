"""Collect four-policy paired answers with durable no-redispatch journals."""
import concurrent.futures,hashlib,json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/proposal-delivery/b-astra-four-strategy-20261101-v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((OUT/'protocol.json').read_text());reg=[json.loads(x) for x in (OUT/'registrations.jsonl').read_text().splitlines()]
seal=json.loads((OUT/'execution-seal.json').read_text());API='http://127.0.0.1:8000/api/v1'
if len(reg)!=16 or sha(OUT/'protocol.json')!=seal['protocol_sha256'] or sha(OUT/'registrations.jsonl')!=seal['registrations_sha256']:raise SystemExit('Frozen registrations changed')
byhistory={h['history_id']:h for h in p['histories']}
def check():
    if any(sha(ROOT/path)!=value for path,value in p['app_sha256'].items()):raise RuntimeError('Application changed after protocol freeze')
    if any(sha(ROOT/path)!=value for path,value in p['scripts_sha256'].items()):raise RuntimeError('Study script changed after protocol freeze')
    if sha(OUT/'protocol.json')!=seal['protocol_sha256'] or sha(OUT/'registrations.jsonl')!=seal['registrations_sha256']:raise RuntimeError('Protocol or registrations changed')
def one(history):
    dest=OUT/(history+'-execution.json')
    if dest.exists():return {'history_id':history,'status':'existing_attempt_not_repeated'}
    state={'history_id':history,'status':'started','conditions':[]}
    def save():
        tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');tmp.replace(dest)
    save()
    try:
        rows=[x for x in reg if x['history_id']==history]
        if [x['strategy'] for x in rows]!=p['strategies']:raise ValueError('Strategy order differs from freeze')
        configurations=[]
        for row in rows:
            condition={'strategy':row['strategy'],'run_id':row['run_id'],'status':'started','operations':[]};state['conditions'].append(condition);save()
            def call(method,path,body=None):
                check();op={'method':method,'path':path,'state':'dispatched'};condition['operations'].append(op);save()
                try:
                    with urlopen(Request(API+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=1200) as r:op.update(state='returned',status=r.status,response=json.load(r))
                except HTTPError as e:op.update(state='http_error',status=e.code,error=e.read().decode(errors='replace')[:1500]);save();raise
                except Exception as e:op.update(state='ambiguous',error_type=type(e).__name__);save();raise
                save();return op['response']
            rid=row['run_id'];audit=call('GET',f'/audits/{rid}')
            if audit.get('provider')!='openai' or audit.get('model')!='gpt-6-astra' or audit.get('memory_strategy')!=row['strategy'] or audit.get('target_memory_writer')!='rule_based':raise ValueError('Target configuration mismatch')
            fields=('provider','model','target_configuration','retrieval_mode','test_budget','temperature','random_seed','target_memory_capacity','memory_maintenance_policy','target_memory_writer','target_system_adapter','evaluator_provider','evaluator_model','pipeline_provider','pipeline_model')
            profile=dict(audit.get('reproducibility',{}).get('target_memory_profile') or {});profile.pop('label',None)
            configs=tuple(json.dumps(audit.get(k),sort_keys=True) for k in fields)+(json.dumps(profile,sort_keys=True),)
            if configurations and configs!=configurations[0]:raise ValueError('Non-strategy settings differ')
            configurations.append(configs)
            tests=call('GET',f'/audits/{rid}/tests')
            signature=lambda x:(x['dimension'],x['prompt'],x['expected_behavior'],tuple(sorted(x['supporting_memory_ids'])))
            if len(tests)!=4 or sorted(map(signature,tests))!=sorted(map(signature,byhistory[history]['questions'])):raise ValueError('Frozen questions differ')
            answers=call('POST',f'/audits/{rid}/execute',{})
            if len(answers)!=4 or any(x.get('execution_metadata',{}).get('reported_model')!='gpt-6-astra' or x.get('execution_metadata',{}).get('requested_reasoning_effort')!='max' for x in answers):raise ValueError('Target receipt mismatch')
            evaluations=call('POST',f'/audits/{rid}/evaluate',{})
            if len(evaluations)!=4:raise ValueError('Incomplete evaluation')
            call('GET',f'/audits/{rid}/target-memory-trace');call('GET',f'/audits/{rid}/agent-executions')
            condition['status']='completed_review_pending';save();print(history,row['strategy'],'completed',flush=True)
        state['status']='completed_review_pending'
    except Exception as exc:state.update(status='stopped',error_type=type(exc).__name__,error=str(exc)[:350])
    save();print(history,state['status'],flush=True);return {'history_id':history,'status':state['status']}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,byhistory))
(OUT/'collection-summary.json').write_text(json.dumps({'histories':results,'human_review':'pending','scope':p['limits']},indent=2)+'\n')
print(json.dumps(results),flush=True)
