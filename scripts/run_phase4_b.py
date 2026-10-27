"""Collect frozen B candidate through the real API; human labels stay pending."""
import argparse,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','execute']);a=p.parse_args();out=ROOT/'artifacts/local/phase4-20261027';plan=json.loads((out/'protocol.json').read_text());sp=out/'B-live.json'
state=json.loads(sp.read_text()) if sp.exists() else {'scope':'B_frozen_automated_collection_human_validation_pending','scenarios':[],'requests':[],'status':'preparing','protocol_sha256':hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest()}
def save():sp.write_text(json.dumps(state,indent=2))
def api(method,path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=300) as response:raw=response.read();code=response.status;kind=response.headers.get('Content-Type','')
 except urllib.error.HTTPError as e:
  state['requests'].append({'method':method,'path':path,'status':e.code,'error':e.read().decode()});save();raise
 data=(json.loads(raw) if 'json' in kind else raw.decode()) if raw else None
 state['requests'].append({'method':method,'path':path,'status':code,'body':data});save();print(method,path,code,flush=True);return data
assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==sha for f,sha in plan['app_source'].items()),'Frozen app source drift'
if a.stage=='prepare':
 if state['scenarios']:raise SystemExit('Preparation already exists; refusing duplicate histories.')
 histories=json.loads((ROOT/'datasets/phase4-candidate-v1/source-histories.json').read_text())
 for h in histories:
  source=api('POST','/conversations',{k:h[k] for k in ['authorised','source_origin','messages']});cid=source['conversation_id'];scenario={'scenario_id':h['scenario_id'],'conversation_id':cid,'runs':[]};state['scenarios'].append(scenario);save()
  extracted=api('POST',f'/conversations/{cid}/extract',{'provider':'rule_based'});scenario['extracted_candidates']=extracted;save()
  for m in extracted:api('DELETE','/memories/'+m['memory_id'])
  mids=[]
  for m in h['messages']:
   record=api('POST','/memories',{'conversation_id':cid,'canonical_value':m['content'],'source_message_ids':[m['message_id']],'timestamp':m['timestamp']});mids.append(record['memory_id'])
  for source_index,typ,target_index in [(2,'UPDATE',1),(4,'CONTEXTUAL_OVERRIDE',3),(5,'CONFLICT',6)]:
   api('PATCH','/memories/'+mids[source_index],{'relationships':[{'type':typ,'target_memory_id':mids[target_index],'evidence_message_ids':[h['messages'][source_index]['message_id'],h['messages'][target_index]['message_id']]}]})
  scenario['memories']=api('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':mids});scenario['confirmation_provenance']='AI-assisted synthetic engineering source review; not independent human gold';save()
  roles={'pipeline_provider':'rule_based','pipeline_model':'rule-based-v2','evaluator_provider':'rule_based','evaluator_model':'rule-based-v64','semantic_review_provider':'rule_based','semantic_review_model':'rule-based-v2'}
  exp=api('POST','/experiments',{'conversation_id':cid,'label':'Phase4 B candidate '+h['scenario_id']+' - human review pending','test_suite_configuration':{**roles,'test_budget':4,'random_seed':42}});scenario['experiment_id']=exp['experiment_id'];save()
  for rep in range(1,4):
   for strategy in plan['target']['memory_strategies']:
    run=api('POST','/audits',{'conversation_id':cid,'experiment_id':exp['experiment_id'],'target_configuration':'strong','provider':'openrouter','model':plan['target']['model'],**roles,'test_budget':4,'random_seed':42,'temperature':0,'memory_strategy':strategy,'memory_maintenance_policy':plan['target']['memory_maintenance_policy'],'target_memory_capacity':50,'target_memory_writer':'rule_based','target_memory_profile':plan['target']['profile']})
    scenario['runs'].append({'run_id':run['run_id'],'configuration':run,'strategy':strategy,'repetition':rep});save()
  for run in scenario['runs']:
   suite=api('POST','/audits/'+run['run_id']+'/generate-tests');run['tests']=suite;save()
   assert len(suite)==4 and len({t['dimension'] for t in suite})==4 and all(t['quality_status']=='accepted' for t in suite)
  signatures=lambda run:[(t['dimension'],t['prompt'],t['expected_behavior'],t['supporting_memory_ids']) for t in run['tests']]
  assert all(signatures(run)==signatures(scenario['runs'][0]) for run in scenario['runs'])
 state['status']='prepared_for_preexecution_review';save()
else:
 assert state['status'] in ['prepared_for_preexecution_review','collecting','complete_automatic_collection'],'Prepare first'
 state['status']='collecting';save()
 for scenario in state['scenarios']:
  for run in scenario['runs']:
   rid=run['run_id']
   failed=any(x['path']==f'/audits/{rid}/execute' and x['status']==503 for x in state['requests'])
   if failed and 'responses' not in run:
    run.setdefault('interrupted_runs',[]).append({'run_id':rid,'reason':'provider 503; original terminal FAILED retained; replacement keeps frozen settings and suite'})
    keys=['conversation_id','experiment_id','target_configuration','provider','model','pipeline_provider','pipeline_model','evaluator_provider','evaluator_model','semantic_review_provider','semantic_review_model','test_budget','random_seed','temperature','memory_strategy','memory_maintenance_policy','target_memory_capacity','target_memory_writer','target_memory_profile']
    exp=api('POST','/experiments',{'conversation_id':scenario['conversation_id'],'label':'Phase4 B 503 recovery; original group retained','test_suite_configuration':{k:run['configuration'][k] for k in ['pipeline_provider','pipeline_model','evaluator_provider','evaluator_model','semantic_review_provider','semantic_review_model','test_budget','random_seed']}})
    body={k:run['configuration'][k] for k in keys if k in run['configuration']};body['experiment_id']=exp['experiment_id']
    config=api('POST','/audits',body)
    run['configuration']=config;run['run_id']=config['run_id'];rid=run['run_id'];run['tests']=api('POST',f'/audits/{rid}/generate-tests');save()
   if 'responses' not in run:run['responses']=api('POST',f'/audits/{rid}/execute');save()
   if 'evaluations' not in run:run['evaluations']=api('POST',f'/audits/{rid}/evaluate');save()
   run['result']=api('GET',f'/audits/{rid}/results');run['trace']=api('GET',f'/audits/{rid}/target-memory-trace');save()
   usage=[r['execution_metadata'] for h in state['scenarios'] for rrun in h['runs'] for r in rrun.get('responses',[])]
   cost=sum((m.get('input_tokens') or 0)*1e-7+(m.get('output_tokens') or 0)*5e-7 for m in usage);state['estimated_target_cost_usd']=cost;save();assert cost<0.5,'B reserved budget exceeded'
  eid=scenario['experiment_id'];scenario['analytics']=api('GET',f'/experiments/{eid}/results');scenario['bundle']=api('GET',f'/experiments/{eid}/reproducibility-bundle.json');scenario['csv']=api('GET',f'/experiments/{eid}/export.csv');scenario['conversation_export']=api('GET',f'/conversations/{scenario["conversation_id"]}/export');save()
 state['status']='complete_automatic_collection';state['independent_human_results_received']=False;save()
