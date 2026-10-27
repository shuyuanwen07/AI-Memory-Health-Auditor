"""Synthetic Phase 1/2 live PostgreSQL/API verification; no human research claims.

prepare creates a new history and frozen Weak/Strong suite, without model calls.
execute reuses the saved plan, calls each target once and exports receipts.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','execute']);p.add_argument('--output',type=Path,default=ROOT/'artifacts/local/phase12-20261027');args=p.parse_args()
args.output.mkdir(parents=True,exist_ok=True);state_path=args.output/'live-verification.json'
state=json.loads(state_path.read_text()) if state_path.exists() else {'scope':'synthetic_engineering_phase12','independent_human_review':False,'requests':[],'runs':[]}
def save():state_path.write_text(json.dumps(state,indent=2,ensure_ascii=False))
def request(method,path,body=None):
    req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
    try:
        with urllib.request.urlopen(req,timeout=300) as response:
            raw=response.read();code=response.status;content_type=response.headers.get('Content-Type','')
    except urllib.error.HTTPError as e:
        raw=e.read();state['requests'].append({'method':method,'path':path,'status':e.code,'error':raw.decode()});save();raise
    data=(json.loads(raw) if 'json' in content_type else raw.decode()) if raw else None
    state['requests'].append({'method':method,'path':path,'status':code,'body':data});save()
    print(method,path,code,flush=True);return data
if args.stage=='prepare':
    if state.get('conversation_id'):raise SystemExit('Prepared state already exists; refusing duplicate creation.')
    source_path=ROOT/'datasets/smoke/qwen-four-dimension-source-v1.json';source=json.loads(source_path.read_text());approval=json.loads((ROOT/'datasets/smoke/qwen-four-dimension-approval-v1.json').read_text())
    assert hashlib.sha256(source_path.read_bytes()).hexdigest()==approval['source_sha256']
    state['source_sha256']=approval['source_sha256'];state['started_at']=datetime.now(timezone.utc).isoformat()
    (args.output/'input.json').write_bytes(source_path.read_bytes())
    c=request('POST','/conversations',{k:source[k] for k in ['authorised','source_origin','messages']});cid=c['conversation_id'];state['conversation_id']=cid;save()
    state['extracted_candidates']=request('POST',f'/conversations/{cid}/extract',{'provider':'rule_based'})
    # Exact prior synthetic approval is reused through supported review APIs.
    # Retain original extracted candidates in the evidence before correcting them.
    for candidate in state['extracted_candidates']:request('DELETE','/memories/'+candidate['memory_id'])
    ids={}
    for m in source['messages']:
        fact=request('POST','/memories',{'conversation_id':cid,'canonical_value':m['content'],'source_message_ids':[m['message_id']],'timestamp':m['timestamp']});ids[m['message_id']]=fact['memory_id']
    for edge in approval['relationships']:
        request('PATCH','/memories/'+ids[edge['source_message_id']],{'relationships':[{'type':edge['type'],'target_memory_id':ids[edge['target_message_id']],'evidence_message_ids':[edge['source_message_id'],edge['target_message_id']]}]})
    state['reviewed_memories']=request('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':list(ids.values())})
    roles={'pipeline_provider':'rule_based','pipeline_model':'rule-based-v2','evaluator_provider':'rule_based','evaluator_model':'rule-based-v63','semantic_review_provider':'rule_based','semantic_review_model':'rule-based-v2'}
    e=request('POST','/experiments',{'conversation_id':cid,'label':'Phase12 current-version synthetic workflow verification','test_suite_configuration':{**roles,'test_budget':4,'random_seed':42}});eid=e['experiment_id'];state['experiment_id']=eid;save()
    for target,strategy in [('weak','weak_first_hit'),('strong','strong_rule_based')]:
        audit=request('POST','/audits',{'conversation_id':cid,'experiment_id':eid,'target_configuration':target,'provider':'openrouter','model':'openai/gpt-6-luna',**roles,'test_budget':4,'memory_strategy':strategy,'memory_maintenance_policy':'append_only','target_memory_writer':'rule_based','target_memory_profile':{'label':'Phase12 '+target,'max_retrieved_records':50,'context_character_budget':16000,'output_token_limit':2048}})
        state['runs'].append({'run_id':audit['run_id'],'strategy':strategy,'configuration':audit});save()
    for run in state['runs']:
        suite=request('POST','/audits/'+run['run_id']+'/generate-tests');run['tests']=suite;save()
        assert len(suite)==4 and {t['dimension'] for t in suite}=={'accuracy','freshness','conflict_resolution','appropriate_use'},'Missing dimension'
        assert all(t['quality_status']=='accepted' for t in suite),'Quality rejection; inspect before target execution'
    state['status']='prepared_for_review';save()
else:
    assert state.get('status')=='prepared_for_review','Only an explicitly prepared frozen suite may execute'
    for run in state['runs']:
        rid=run['run_id']
        run['responses']=request('POST',f'/audits/{rid}/execute')
        run['evaluations']=request('POST',f'/audits/{rid}/evaluate')
        run['result']=request('GET',f'/audits/{rid}/results')
        run['trace']=request('GET',f'/audits/{rid}/target-memory-trace')
        run['diagnosis']=request('GET',f'/audits/{rid}/diagnosis');save()
    eid=state['experiment_id'];bundle=request('GET',f'/experiments/{eid}/reproducibility-bundle.json');csv_text=request('GET',f'/experiments/{eid}/export.csv')
    (args.output/'bundle.json').write_text(json.dumps(bundle,indent=2));(args.output/'results.csv').write_text(csv_text)
    exported=request('GET','/conversations/'+state['conversation_id']+'/export');(args.output/'conversation-export.json').write_text(json.dumps(exported,indent=2))
    actual={e['evaluation_id'] for run in state['runs'] for e in run['evaluations']}
    csv_ids={row['evaluation_id'] for row in csv.DictReader(io.StringIO(csv_text)) if row['record_type']=='answer'}
    bundle_ids={answer['evaluation_id'] for run in bundle['runs'] for answer in run['answers']}
    assert actual==csv_ids==bundle_ids
    for run in state['runs']:
        result=run['result'];es=run['evaluations'];assert result['tests_passed']==sum(e['passed'] is True for e in es)
        assert len(run['responses'])==4 and len(es)==4
        assert all(d['expected_tests']==1 for d in result['dimensions'])
        assert all(receipt['memory_input'] for receipt in run['trace']['retrievals'])
    state['status']='completed';state['finished_at']=datetime.now(timezone.utc).isoformat();state['exports_verified']=True;save()
