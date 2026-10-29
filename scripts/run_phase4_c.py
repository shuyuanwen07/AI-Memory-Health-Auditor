"""Frozen official-Oracle subset with shared reader and pinned upstream grader.

Alternate OpenRouter transport and a 14/500 Oracle subset are explicit limits.
Not the complete official benchmark or independent human calibration.
"""
import argparse,hashlib,json,sys,os,time,re
from pathlib import Path
ROOT=Path(os.environ.get('MHA_PROJECT_ROOT','/app'))
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,'/app');sys.path.insert(0,'/scripts')
from app.schemas.benchmark import LiveBenchmarkRequest
from app.schemas import TargetResponse
from app.benchmarks.live import LiveBenchmarkRunner
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import private_context_instruction,target_question_input
from app.target_ai.openrouter import build_openrouter_target_payload
from app.target_ai.request_contracts import request_contract_sha256
from longmemeval_grading import build_openrouter_grader_payload, load_upstream_prompt
import httpx
p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--max-cost-usd',type=float,default=None);a=p.parse_args();d=a.directory;plan=json.loads((d/'protocol.json').read_text());subset=json.loads((d/'longmemeval-subset.json').read_text());binding=json.loads((d/'upstream/source-binding.json').read_text())
if a.max_cost_usd is not None and a.max_cost_usd <= 0:raise SystemExit('--max-cost-usd must be positive when supplied.')
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(d/'longmemeval-subset.json')==plan['source_files']['benchmark_subset_sha256'],'Frozen benchmark subset changed'
assert digest(ROOT/plan['source']['source_manifest'])==plan['source']['source_manifest_sha256'],'Dataset source manifest changed'
assert digest(ROOT/plan['source']['oracle_source'])==plan['source']['oracle_source_sha256'],'Pinned Oracle dataset changed'
assert digest(ROOT/plan['selection']['release_manifest'])==plan['selection']['release_manifest_sha256'],'Prepared release manifest changed'
assert digest(ROOT/plan['selection']['execution_manifest'])==plan['selection']['execution_manifest_sha256_at_freeze'],'Candidate execution manifest changed after freeze'
for source_path,expected_sha in plan['app_source'].items():
 assert digest(ROOT/source_path)==expected_sha,f'Frozen app or runner source changed: {source_path}'
path=d/'C-live.json'
prior=json.loads(path.read_text()) if path.exists() else None
if prior and prior['status'] not in ['failed','recovering']:raise SystemExit('Collection already complete or uncertain; do not repeat.')
report={'scope':'official_oracle_subset_compatibility_not_full_official_benchmark','protocol_sha256':digest(d/'protocol.json'),'upstream_binding':binding,'reader_runs':[],'target_receipts':[],'grades':[],'status':'running','estimated_cost_usd':0,'max_cost_usd':a.max_cost_usd,'compatibility_deviations':['14/500 frozen candidate-held-out Oracle subset, not full S/M','GPT-6 Luna model grader is not the official metric model and is the same model as the target','Controlled-memory reader and source adapter, not upstream execution stack','No independent human calibration; automated ranking only']}
if prior:
 amendment=plan.get('protocol_amendment') or {}
 prior_source=ROOT/amendment.get('prior_candidate_run','')
 new_protocol_sha256=digest(d/'protocol.json')
 prior_protocol_sha256=prior.get('protocol_sha256')
 if prior_protocol_sha256==amendment.get('prior_protocol_sha256'):
  assert prior_source.is_file() and digest(prior_source)==amendment.get('prior_candidate_run_sha256'),'Original partial run differs from the declared amendment source'
  interruption_rel=amendment.get('prior_interruption_receipt')
  if interruption_rel:
   interruption_path=ROOT/interruption_rel
   assert interruption_path.is_file() and digest(interruption_path)==amendment.get('prior_interruption_receipt_sha256'),'Prior interruption receipt differs from the declared amendment'
   interruption=json.loads(interruption_path.read_text())
  else: interruption=None
 elif prior_protocol_sha256==new_protocol_sha256:
  interruption=None
 else: raise ValueError('Partial run protocol does not match the declared amendment or its recovery protocol')
 report=prior
 if prior_protocol_sha256==amendment.get('prior_protocol_sha256'):
  if amendment.get('prior_grading_labels_regraded_as_a_separate_round'):
   report.setdefault('prior_grading_rounds',[]).append({'protocol_sha256':prior_protocol_sha256,'grades':report.get('grades',[]),'usable_grade_count':sum(bool(g.get('verdict_usable')) for g in report.get('grades',[])),'round_note':'Preserved intact; v5 regrades all target receipts using one unified scorer request configuration.'})
   report['grades']=[]
  if interruption and not any(r.get('sha256')==amendment.get('prior_interruption_receipt_sha256') for r in report.get('target_interruption_history',[])):
   report.setdefault('target_interruption_history',[]).append({'sha256':amendment['prior_interruption_receipt_sha256'],'receipt':interruption})
 report.setdefault('protocol_lineage',[]).append({'protocol_sha256':prior_protocol_sha256,'status':'failed_partial','reason':'Prior target 503 and incomplete grader outputs; successful targets are re-used only after exact request-payload equality checks.'})
 report['protocol_sha256']=new_protocol_sha256
 report['status']='recovering'
 report.setdefault('recovery_events',[]).append({'reason':'Resume from an explicitly amended exploratory protocol; preserved target responses are replayed locally after exact request equality checks.', 'max_recovery_invocations':3})
 report.pop('error_type',None)
def save():path.write_text(json.dumps(report,indent=2))
def check_cost(reserve=0):
 if a.max_cost_usd is not None and report['estimated_cost_usd']+reserve>a.max_cost_usd:raise RuntimeError('User-specified C cost ceiling reached; partial evidence retained.')
prompt_function,_=load_upstream_prompt(d/'upstream');current={};original=HttpTargetAIConnector.execute

def capture(connector,test,audit):
 cached=[r for r in report['target_receipts'] if r['repetition']==current['repetition'] and r['strategy']==current['strategy']]
 index=current['case_index'];current['case_index']+=1
 if index<len(cached):
  item=cached[index];old=item['verified_request_payload']
  candidate=build_openrouter_target_payload(model=audit.model,instructions=private_context_instruction(test,audit.target_configuration),prompt=target_question_input(test.prompt),temperature=audit.temperature,max_output_tokens=audit.target_memory_profile.output_token_limit,provider_options=old['provider'])
  assert candidate==old,'Cached request differs; refuse recovery'
  return TargetResponse.model_validate(item['response']).model_copy(deep=True,update={'test_id':test.test_id,'run_id':audit.run_id})
 provider_options=(cached[0]['verified_request_payload']['provider'] if cached else
  (report['target_receipts'][-1]['verified_request_payload']['provider'] if report.get('target_receipts') else {'require_parameters':True,'allow_fallbacks':False}))
 candidate=build_openrouter_target_payload(model=audit.model,instructions=private_context_instruction(test,audit.target_configuration),prompt=target_question_input(test.prompt),temperature=audit.temperature,max_output_tokens=audit.target_memory_profile.output_token_limit,provider_options=provider_options)
 try:response=original(connector,test,audit)
 except Exception as exc:
  report.setdefault('target_failure_attempts',[]).append({**current,'case_index':index,'request_payload':candidate,'request_payload_sha256':request_contract_sha256(candidate),'error_type':type(exc).__name__,'status_code':getattr(exc,'status_code',None),'message':str(exc)[:500],'response_body_captured':False})
  report['billing_uncertain_due_to_failed_target_attempts']=True;save();raise
 meta=response.execution_metadata.model_dump(mode='json');c=meta['request_contract']
 payload=build_openrouter_target_payload(model=audit.model,instructions=private_context_instruction(test,audit.target_configuration),prompt=target_question_input(test.prompt),temperature=audit.temperature,max_output_tokens=audit.target_memory_profile.output_token_limit,provider_options=c['provider']['value'])
 assert request_contract_sha256(payload)==c['payload_sha256']
 report['target_receipts'].append({**current,'response':response.model_dump(mode='json'),'verified_request_payload':payload,'expected_behavior_empty':test.expected_behavior=='','supporting_gold_ids_empty':test.supporting_memory_ids==[]})
 report['estimated_cost_usd']+=(meta.get('input_tokens') or 0)*1e-7+(meta.get('output_tokens') or 0)*5e-7;save();check_cost()
 print('saved_target',len(report['target_receipts']),flush=True);return response
HttpTargetAIConnector.execute=capture;save()
try:
 for repetition in range(1,4):
  for strategy in plan['target']['memory_strategies']:
   current.update(repetition=repetition,strategy=strategy,case_index=0)
   completed=next((r for r in report['reader_runs'] if r['repetition']==repetition and r['strategy']==strategy),None)
   request=LiveBenchmarkRequest(payload=subset,source_authorised=True,source_label='Official LongMemEval candidate-held-out Oracle subset',dataset_provenance={'dataset_version':plan['source']['revision'],'license':plan['source']['license'],'citation':'Wu et al., LongMemEval, ICLR 2025; https://github.com/xiaowu0162/LongMemEval'},provider='openrouter',model=plan['target']['model'],strategies=[strategy],max_cases=14,target_memory_capacity=50,target_memory_profile=plan['target'].get('profile',plan['target'].get('target_memory_profile')),temperature=0,random_seed=42)
   if completed:
    from app.schemas.benchmark import LiveBenchmarkResponse
    result=LiveBenchmarkResponse.model_validate(completed['result'])
   else:
    result=LiveBenchmarkRunner().run(request);report['reader_runs'].append({'repetition':repetition,'strategy':strategy,'result':result.model_dump(mode='json')});save()
   if len(result.conditions)!=1 or len(result.conditions[0].cases)!=plan['selection']['case_count']:
    raise ValueError('Benchmark runner did not return the full frozen case set for this condition.')
   for case in result.conditions[0].cases:
    if any(g['repetition']==repetition and g['strategy']==strategy and g['question_id']==case.case_id and g.get('verdict_usable') for g in report['grades']):continue
    prompt=prompt_function(case.category,case.question,case.expected_answer,case.response_text,abstention='_abs' in case.case_id)
    payload=build_openrouter_grader_payload(plan['C']['judge_model'],prompt)
    grade=next((g for g in report['grades'] if g['repetition']==repetition and g['strategy']==strategy and g['question_id']==case.case_id),None)
    fresh=grade is None
    grade=grade or {'repetition':repetition,'strategy':strategy,'question_id':case.case_id,'question_type':case.category,'request_payload':payload,'upstream_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'attempts':[]}
    if fresh:report['grades'].append(grade)
    elif grade.get('request_payload') != payload:
     grade.setdefault('request_payload_history',[]).append({'payload':grade.get('request_payload'),'attempts':grade.get('attempts',[]),'provider_response_body':grade.get('provider_response_body'),'raw_verdict':grade.get('raw_verdict'),'finish_reason':grade.get('finish_reason'),'usage':grade.get('usage'),'unusable_reason':grade.get('unusable_reason'),'reason':'Preserved previous scorer response before the unified v5 scorer round.'})
     grade['request_payload']=payload
     grade['upstream_prompt_sha256']=hashlib.sha256(prompt.encode()).hexdigest()
    save()
    # Budget reserves a full upper-bound character-as-token estimate before
    # each grader attempt. Unknown billed usage is never silently zeroed.
    bound=len(prompt)*2.5e-6+128*1e-5
    next_attempt=(grade.get('attempts') or [{}])[-1].get('attempt',0)+1
    for attempt in range(next_attempt,4):
     check_cost(bound)
     response=httpx.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},json=payload,timeout=60)
     grade['attempts'].append({'attempt':attempt,'http_status':response.status_code});save()
     if response.status_code in {408,429,500,502,503,504} and attempt<3:
      report['estimated_cost_usd']+=bound;save();time.sleep(1);continue
     if response.status_code>=400:
      grade['error_response']=response.text[:1500];report['estimated_cost_usd']+=bound;save()
     response.raise_for_status();grade['provider_response_body']=response.text;save();data=response.json();usage=data.get('usage',{});grade['reported_model']=data.get('model');grade['usage']=usage
     choice=((data.get('choices') or [{}])[0]);message=choice.get('message') or {};content=message.get('content')
     if isinstance(content,str):raw=content.strip()
     elif isinstance(content,list):raw=''.join(str(part.get('text','')) for part in content if isinstance(part,dict)).strip()
     else:raw=''
     grade['raw_verdict']=raw;grade['finish_reason']=choice.get('finish_reason')
     grade['autoeval_label']=('yes' in raw.lower());grade['upstream_parse_rule']="'yes' in stripped_response.lower()"
     grade['verdict_usable']=bool(re.fullmatch(r'(?:yes|no)[.!]?',raw,re.I)) and grade['finish_reason']=='stop'
     if not grade['verdict_usable']:grade['unusable_reason']='No strict yes/no text with a stop finish reason; provider response is retained.'
     report['estimated_cost_usd']+=(usage.get('prompt_tokens') or 0)*2.5e-6+(usage.get('completion_tokens') or 0)*1e-5 if usage else bound
     save();check_cost();break
    print('saved_grade',len(report['grades']),grade.get('verdict_usable'),flush=True)
 expected=len(subset)*len(plan['target']['memory_strategies'])*plan['target']['repetitions_per_strategy']
 report['status']='complete_automatic_collection' if len(report['reader_runs'])==expected//len(subset) and len(report['target_receipts'])==expected and len(report['grades'])==expected and all(g.get('verdict_usable') for g in report['grades']) else 'partial_grader_uncertainty';save()
except Exception as exc:
 report['status']='failed';report['error_type']=type(exc).__name__;save();raise
finally:HttpTargetAIConnector.execute=original
