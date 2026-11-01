"""Run pre-registered writer comparisons, one condition at a time per history."""
import concurrent.futures,hashlib,json,threading
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/proposal-delivery/astra-writer-four-prospective-20261101-v1'
PROTOCOL=OUT/'protocol.json';REG=OUT/'registrations.jsonl';AMEND=OUT/'execution-amendment.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol=json.loads(PROTOCOL.read_text());amend=json.loads(AMEND.read_text());regs=[json.loads(x) for x in REG.read_text().splitlines()]
if sha(PROTOCOL)!=amend['protocol_sha256'] or sha(REG)!=amend['registrations_sha256'] or len(regs)!=4:raise SystemExit('Frozen input mismatch')
if any(sha(ROOT/p)!=v for p,v in protocol['app_sha256'].items()):raise SystemExit('App changed since freeze')
by_history={h['history_id']:h for h in protocol['histories']};print_lock=threading.Lock()
def run(reg):
    path=OUT/f"{reg['history_id']}-execution.json"
    if path.exists():return {'history_id':reg['history_id'],'status':'existing_attempt_not_repeated'}
    state={'history_id':reg['history_id'],'experiment_id':reg['experiment_id'],'status':'starting','operations':[]}
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
    def check():
        if sha(PROTOCOL)!=amend['protocol_sha256'] or sha(REG)!=amend['registrations_sha256'] or any(sha(ROOT/p)!=v for p,v in protocol['app_sha256'].items()):raise RuntimeError('Frozen input or application changed')
    def call(method,route,body=None):
        check();row={'method':method,'path':route,'state':'dispatched'};state['operations'].append(row);save()
        try:
            with urlopen(Request('http://127.0.0.1:8000/api/v1'+route,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=1200) as response:row.update(state='returned',status=response.status,response=json.load(response))
        except HTTPError as e:row.update(state='http_error',status=e.code,error=e.read().decode(errors='replace')[:2000]);save();raise
        except Exception as e:row.update(state='ambiguous',error_type=type(e).__name__);save();raise
        save();return row['response']
    save()
    try:
        before=call('GET',f"/audits/{reg['baseline_run_id']}");after=call('GET',f"/audits/{reg['candidate_run_id']}")
        fields=('provider','model','target_configuration','memory_strategy','retrieval_mode','test_budget','temperature','random_seed','target_memory_capacity','memory_maintenance_policy','target_system_adapter','evaluator_provider','evaluator_model','pipeline_provider','pipeline_model')
        if any(before.get(k)!=after.get(k) for k in fields) or before.get('provider')!='openai' or before.get('model')!='gpt-6-astra' or before.get('memory_strategy')!='relationship_packet' or before.get('target_memory_writer')!='rule_based' or after.get('target_memory_writer')!='llm_structured':raise ValueError('Condition configuration mismatch')
        p1=dict(before.get('reproducibility',{}).get('target_memory_profile') or {});p2=dict(after.get('reproducibility',{}).get('target_memory_profile') or {});p1.pop('label',None);p2.pop('label',None)
        if p1!=p2:raise ValueError('Target profile mismatch beyond display label')
        expected=by_history[reg['history_id']]['questions'];sig=lambda x:(x['dimension'],x['prompt'],x['expected_behavior'],tuple(sorted(x['supporting_memory_ids'])))
        for label,key in [('baseline','baseline_run_id'),('candidate','candidate_run_id')]:
            rid=reg[key];tests=call('GET',f'/audits/{rid}/tests')
            if len(tests)!=4 or sorted(map(sig,tests))!=sorted(map(sig,expected)):raise ValueError('Frozen questions differ')
            responses=call('POST',f'/audits/{rid}/execute',{})
            if len(responses)!=4 or any(x.get('execution_metadata',{}).get('reported_model')!='gpt-6-astra' or x.get('execution_metadata',{}).get('requested_reasoning_effort')!='max' for x in responses):raise ValueError('Target model receipt mismatch')
            evaluations=call('POST',f'/audits/{rid}/evaluate',{})
            if len(evaluations)!=4:raise ValueError('Missing evaluation')
            call('GET',f'/audits/{rid}/target-memory-trace');call('GET',f'/audits/{rid}/agent-executions')
            with print_lock: print(reg['history_id'],label,'completed',flush=True)
        state['status']='completed_human_review_pending'
    except Exception as exc:state.update(status='stopped',error_type=type(exc).__name__,error=str(exc)[:300])
    save()
    with print_lock: print(reg['history_id'],state['status'],flush=True)
    return {'history_id':reg['history_id'],'status':state['status']}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:results=list(executor.map(run,regs))
(OUT/'collection-summary.json').write_text(json.dumps({'status_by_history':results,'human_review':'pending','scope':'Four related synthetic source histories; prospective target answers, not a representative population.'},indent=2)+'\n')
print('Collection status:',json.dumps(results),flush=True)
