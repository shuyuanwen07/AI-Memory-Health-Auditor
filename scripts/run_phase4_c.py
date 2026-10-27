"""Frozen official-Oracle subset with shared reader and pinned upstream grader.

Alternate OpenRouter transport and a 14/500 Oracle subset are explicit limits.
Not the complete official benchmark or independent human calibration.
"""
import argparse,hashlib,json,sys,os,time,re
from pathlib import Path
sys.path.insert(0,'/app');sys.path.insert(0,'/scripts')
from app.schemas.benchmark import LiveBenchmarkRequest
from app.schemas import TargetResponse
from app.benchmarks.live import LiveBenchmarkRunner
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import private_context_instruction,target_question_input
from app.target_ai.openrouter import build_openrouter_target_payload
from app.target_ai.request_contracts import request_contract_sha256
from longmemeval_grading import load_upstream_prompt
import httpx
p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);a=p.parse_args();d=a.directory;plan=json.loads((d/'protocol.json').read_text());subset=json.loads((d/'longmemeval-subset.json').read_text());binding=json.loads((d/'upstream/source-binding.json').read_text())
assert hashlib.sha256((d/'longmemeval-subset.json').read_bytes()).hexdigest()==plan['source_files']['benchmark_subset_sha256']
path=d/'C-live.json'
prior=json.loads(path.read_text()) if path.exists() else None
if prior and prior['status'] not in ['failed','recovering']:raise SystemExit('Collection already complete or uncertain; do not repeat.')
report={'scope':'official_oracle_subset_compatibility_not_full_official_benchmark','protocol_sha256':hashlib.sha256((d/'protocol.json').read_bytes()).hexdigest(),'upstream_binding':binding,'reader_runs':[],'target_receipts':[],'grades':[],'status':'running','estimated_cost_usd':0,'compatibility_deviations':['14/500 stratified Oracle subset, not S/M','OpenRouter transport for pinned official GPT-4o judge','Controlled-memory reader and source adapter, not upstream execution stack','No independent human calibration; automated ranking only']}
if prior:
 report=prior
 report['status']='recovering'
 report.setdefault('recovery_events',[]).append({'reason':'503 service interruption; completed requests replayed locally after exact payload equality check', 'max_recovery_invocations':3})
 report.pop('error_type',None)
def save():path.write_text(json.dumps(report,indent=2))
prompt_function,_=load_upstream_prompt(d/'upstream');current={};original=HttpTargetAIConnector.execute

def capture(connector,test,audit):
 cached=[r for r in report['target_receipts'] if r['repetition']==current['repetition'] and r['strategy']==current['strategy']]
 index=current['case_index'];current['case_index']+=1
 if index<len(cached):
  item=cached[index];old=item['verified_request_payload']
  candidate=build_openrouter_target_payload(model=audit.model,instructions=private_context_instruction(test,audit.target_configuration),prompt=target_question_input(test.prompt),temperature=audit.temperature,max_output_tokens=audit.target_memory_profile.output_token_limit,provider_options=old['provider'])
  assert candidate==old,'Cached request differs; refuse recovery'
  return TargetResponse.model_validate(item['response']).model_copy(deep=True,update={'test_id':test.test_id,'run_id':audit.run_id})
 response=original(connector,test,audit);meta=response.execution_metadata.model_dump(mode='json');c=meta['request_contract']
 payload=build_openrouter_target_payload(model=audit.model,instructions=private_context_instruction(test,audit.target_configuration),prompt=target_question_input(test.prompt),temperature=audit.temperature,max_output_tokens=audit.target_memory_profile.output_token_limit,provider_options=c['provider']['value'])
 assert request_contract_sha256(payload)==c['payload_sha256']
 report['target_receipts'].append({**current,'response':response.model_dump(mode='json'),'verified_request_payload':payload,'expected_behavior_empty':test.expected_behavior=='','supporting_gold_ids_empty':test.supporting_memory_ids==[]})
 report['estimated_cost_usd']+=(meta.get('input_tokens') or 0)*1e-7+(meta.get('output_tokens') or 0)*5e-7;save();assert report['estimated_cost_usd']<1.5,'C cost ceiling reached'
 print('saved_target',len(report['target_receipts']),flush=True);return response
HttpTargetAIConnector.execute=capture;save()
try:
 for repetition in range(1,4):
  for strategy in plan['target']['memory_strategies']:
   current.update(repetition=repetition,strategy=strategy,case_index=0)
   completed=next((r for r in report['reader_runs'] if r['repetition']==repetition and r['strategy']==strategy),None)
   request=LiveBenchmarkRequest(payload=subset,source_authorised=True,source_label='Official LongMemEval Oracle stratified subset',dataset_provenance={'dataset_version':binding['dataset_revision'],'license':'MIT; original LICENSE saved','citation':'Wu et al., LongMemEval, ICLR 2025; https://github.com/xiaowu0162/LongMemEval'},provider='openrouter',model=plan['target']['model'],strategies=[strategy],max_cases=14,target_memory_capacity=50,target_memory_profile=plan['target']['profile'],temperature=0,random_seed=42)
   if completed:
    from app.schemas.benchmark import LiveBenchmarkResponse
    result=LiveBenchmarkResponse.model_validate(completed['result'])
   else:
    result=LiveBenchmarkRunner().run(request);report['reader_runs'].append({'repetition':repetition,'strategy':strategy,'result':result.model_dump(mode='json')});save()
   for case in result.conditions[0].cases:
    if any(g['repetition']==repetition and g['strategy']==strategy and g['question_id']==case.case_id and g.get('verdict_usable') for g in report['grades']):continue
    prompt=prompt_function(case.category,case.question,case.expected_answer,case.response_text,abstention='_abs' in case.case_id)
    payload={'model':plan['C']['judge_model'],'messages':[{'role':'user','content':prompt}],'n':1,'temperature':0,'max_tokens':10,'provider':{'require_parameters':True,'allow_fallbacks':False}}
    grade=next((g for g in report['grades'] if g['repetition']==repetition and g['strategy']==strategy and g['question_id']==case.case_id),None)
    fresh=grade is None
    grade=grade or {'repetition':repetition,'strategy':strategy,'question_id':case.case_id,'question_type':case.category,'request_payload':payload,'upstream_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'attempts':[]}
    if fresh:report['grades'].append(grade)
    save()
    # Budget reserves a full upper-bound character-as-token estimate before
    # each grader attempt. Unknown billed usage is never silently zeroed.
    bound=len(prompt)*2.5e-6+10*1e-5
    for attempt in range(1,4):
     assert report['estimated_cost_usd']+bound<1.5,'C cost ceiling reached before grader'
     response=httpx.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']},json=payload,timeout=60)
     grade['attempts'].append({'attempt':attempt,'http_status':response.status_code});save()
     if response.status_code in {408,429,500,502,503,504} and attempt<3:
      report['estimated_cost_usd']+=bound;save();time.sleep(1);continue
     if response.status_code>=400:
      grade['error_response']=response.text[:1500];report['estimated_cost_usd']+=bound;save()
     response.raise_for_status();data=response.json();usage=data.get('usage',{});grade['reported_model']=data.get('model');grade['usage']=usage
     raw=data['choices'][0]['message']['content'].strip();grade['raw_verdict']=raw;grade['finish_reason']=data['choices'][0].get('finish_reason')
     grade['autoeval_label']=('yes' in raw.lower());grade['upstream_parse_rule']="'yes' in stripped_response.lower()"
     grade['verdict_usable']=bool(re.fullmatch(r'(?:yes|no)[.!]?',raw,re.I)) and grade['finish_reason']=='stop'
     report['estimated_cost_usd']+=(usage.get('prompt_tokens') or 0)*2.5e-6+(usage.get('completion_tokens') or 0)*1e-5 if usage else bound
     save();break
    print('saved_grade',len(report['grades']),grade.get('verdict_usable'),flush=True)
 report['status']='complete_automatic_collection' if len(report['grades'])==84 and all(g.get('verdict_usable') for g in report['grades']) else 'partial_grader_uncertainty';save()
except Exception as exc:
 report['status']='failed';report['error_type']=type(exc).__name__;save();raise
finally:HttpTargetAIConnector.execute=original
