"""Experiment A: freeze real user-declared reviews, generate, then await new-suite review."""
import argparse,hashlib,html,json,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-20261027';P=D/'researcher-preexecution';PATH=D/'A-live.json'
def save():PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2))
def api(method,path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=300) as r:data=json.load(r)
 except urllib.error.HTTPError as e:
  state['http_events'].append({'method':method,'path':path,'status':e.code,'error':e.read().decode()});save();raise
 state['http_events'].append({'method':method,'path':path,'response':data});save();return data
p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','execute']);args=p.parse_args()
plan=json.loads((D/'protocol.json').read_text());assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in plan['app_source'].items()),'Frozen production source changed'
state=json.loads(PATH.read_text()) if PATH.exists() else {'status':'preparing','http_events':[],'scenarios':[],'review_provenance':{'researcher':'Yichao Wang','inventory_reviewers':['Yichao Wang','Shuyuan Wen'],'user_confirmation':'User explicitly confirmed both independently reviewed all nine inventory items and passed without modifications.','authenticity':'Actual chat declaration; software does not authenticate reviewer identity or independence.','new_generated_suite_human_review':'Pending; previous approval covers fixed draft and inventory only.'},'estimated_A_target_calls':36,'estimated_A_target_cost_usd':0.02,'budget':'Within original user-authorised US$5; no model execution in prepare stage.'}
if args.stage=='execute':
 state['review_provenance']['new_generated_suite_human_review']={'reviewer':'Yichao Wang','statement':'新增24题审核通过','decision':'accepted_without_modification','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'material_sha256':hashlib.sha256((D/'A-generated-suites-review.html').read_bytes()).hexdigest()};save()
 for item in state['scenarios']:
  for run in item['runs']:
   rid=run['run_id']
   if not run.get('new_suite_review_recorded'):
    tests=api('GET','/audits/'+rid+'/tests')
    for index,t in enumerate(tests):
     if t.get('human_validity_status')!='accepted':
      tests[index]=api('PATCH','/audits/'+rid+'/tests/'+t['test_id']+'/human-validity-review',{'decision':'accepted','reviewer_pseudonym':'Yichao Wang','note':'User explicitly confirmed all24 newly generated direct/contextual-indirect questions in the linked review material before target execution: 新增24题审核通过.'})
    assert all(t.get('human_validity_status')=='accepted' for t in tests)
    run['tests']=tests;run['new_suite_review_recorded']=True;save()
 state['status']='collecting';save()
 for item in state['scenarios']:
  for run in item['runs']:
   rid=run['run_id'];run['configuration']=api('GET','/audits/'+rid);save()
   if run['configuration']['status']=='FAILED':
    state['status']='failed_run_retained';save();raise SystemExit('A terminal failed run exists; do not silently repeat it.')
   if 'responses' not in run:
    run['responses']=api('POST','/audits/'+rid+'/execute');save()
   if 'evaluations' not in run:
    run['evaluations']=api('POST','/audits/'+rid+'/evaluate');save()
   run['result']=api('GET','/audits/'+rid+'/results');run['trace']=api('GET','/audits/'+rid+'/target-memory-trace');run['configuration']=api('GET','/audits/'+rid);save()
   usage=[r['execution_metadata'] for h in state['scenarios'] for condition in h['runs'] for r in condition.get('responses',[])]
   state['estimated_completed_target_cost_usd']=sum((m.get('input_tokens') or 0)*1e-7+(m.get('output_tokens') or 0)*5e-7 for m in usage);save();assert state['estimated_completed_target_cost_usd']<0.5,'A stage cost ceiling reached'
   print('Completed',item['scenario_id'],run['label'],len(run['responses']),flush=True)
  item['comparison_results']=api('GET','/audits/'+item['source_run_id']+'/method-comparison-results?comparison_id='+item['comparison_id']);save()
 state['status']='complete_target_collection_independent_response_review_pending';save();print('36 target answers complete; independent response labels/mapping remain pending.');raise SystemExit(0)
for f in sorted(P.glob('P4-H*.json')):
 source=json.loads(f.read_text());sid=source['scenario_id'];item=next((x for x in state['scenarios'] if x['scenario_id']==sid),None)
 if item is None:
  item={'scenario_id':sid,'source_run_id':source['source_run_id'],'comparison_id':source['comparison']['comparison_id'],'runs':source['comparison']['runs']};state['scenarios'].append(item);save()
 if 'frozen_inventory' not in item:
  body={**source['proposed_inventory'],'release_id':'phase4-a-'+sid+'-human-confirmed-v1','reviewers':['Yichao Wang','Shuyuan Wen'],'fixed_template_release_id':'phase4-a-'+sid+'-fixed-v1','fixed_template_reviewers':['Yichao Wang'],'fixed_template_review_confirmed':True}
  item['submitted_inventory']=body;save();item['frozen_inventory']=api('POST','/audits/'+source['source_run_id']+'/method-comparison-inventory',body);save()
 for run in item['runs']:
  rid=run['run_id']
  if 'configuration' not in run:run['configuration']=api('GET','/audits/'+rid);save()
  if 'tests' not in run:run['tests']=api('POST','/audits/'+rid+'/generate-tests');save()
  assert len(run['tests'])==4 and len({t['dimension'] for t in run['tests']})==4,'Unequal budget or missing dimension'
  assert all(t['quality_status']=='accepted' for t in run['tests']),'Automated quality gate pending'
  if run['label']=='Fixed templates' and not run.get('prior_fixed_review_recorded'):
   frozen=item['submitted_inventory']['fixed_template_questions']
   signature=lambda t:(t['dimension'],t['prompt'],t['expected_behavior'],tuple(sorted(t['supporting_memory_ids'])))
   assert sorted(map(signature,run['tests']))==sorted(map(signature,frozen)),'Fixed questions differ from human-reviewed release'
   for index,t in enumerate(run['tests']):
    run['tests'][index]=api('PATCH','/audits/'+rid+'/tests/'+t['test_id']+'/human-validity-review',{'decision':'accepted','reviewer_pseudonym':'Yichao Wang','note':'User explicitly reviewed and confirmed this exact fixed-template release in chat before execution; no modifications.'});save()
   run['prior_fixed_review_recorded']=True;save()
state['status']='awaiting_human_validity_review_of_generated_suites';save()
parts=['<!doctype html><meta charset="utf-8"><title>Experiment A generated suites review</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto;line-height:1.5}article{border:1px solid #ccc;padding:18px;margin:18px 0}small{color:#444}</style><h1>Experiment A: generated suites, before target execution</h1><p>36 questions across three histories and three methods. The 12 fixed-template questions and nine inventory entries were previously confirmed; 24 direct/contextual-indirect questions are newly generated. Target calls: zero. Review grounding, clarity, expected behaviour and answer leakage for every new question. Actual human validity declarations remain pending.</p>']
for item in state['scenarios']:
 source=json.loads((P/(item['scenario_id']+'.json')).read_text());mem={m['memory_id']:m for m in source['confirmed_memories']}
 parts.append('<h2>'+item['scenario_id']+'</h2><h3>Original source</h3>'+''.join('<p>'+html.escape(m['message_id']+': '+m['content'])+'</p>' for m in source['source_messages']))
 for run in item['runs']:
  parts.append('<h3>'+html.escape(run['label'])+'</h3>')
  for t in run['tests']:
   parts.append('<article><b>'+html.escape(t['dimension']+' / '+t['test_type'])+'</b><p>'+html.escape(t['prompt'])+'</p><p><b>Expected:</b> '+html.escape(t['expected_behavior'])+'</p><small>'+html.escape(' | '.join(mem[mid]['canonical_value'] for mid in t['supporting_memory_ids']))+'</small></article>')
(D/'A-generated-suites-review.html').write_text(''.join(parts));print('Frozen three inventories; generated nine suites / 36 questions; zero target calls. New-suite human review pending.')
