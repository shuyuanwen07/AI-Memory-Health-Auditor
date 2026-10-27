"""Execute the frozen synthetic target validation plan, preserving wire receipts."""
import argparse,json,hashlib,re,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'/app')
from app.schemas import AuditRun,TestCase,TargetMemoryProfile,TargetResponse
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import private_context_instruction,target_question_input
from app.target_ai.openrouter import build_openrouter_target_payload
from app.target_ai.request_contracts import request_contract_sha256
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args();plan=json.loads(a.plan.read_text());assert plan['expected_calls']==9
if a.output.exists() and not a.resume:raise SystemExit('Refusing to overwrite prior live evidence or repeat paid calls.')
report=json.loads(a.output.read_text()) if a.resume else {'plan_sha256':hashlib.sha256(a.plan.read_bytes()).hexdigest(),'scope':plan['scope'],'trials':[],'status':'running'}
assert report['plan_sha256']==hashlib.sha256(a.plan.read_bytes()).hexdigest()
report['status']='running'
a.output.parent.mkdir(parents=True,exist_ok=True)
def save():a.output.write_text(json.dumps(report,indent=2))
save()
for trial in plan['trials']:
 now=datetime.now(timezone.utc);configuration='weak' if trial['condition']=='weak_unchanged' else 'strong'
 audit=AuditRun(run_id='P3-'+trial['id'],conversation_id='P3-'+trial['case_id'],status='CREATED',target_configuration=configuration,provider='openrouter',model=plan['model'],temperature=0,random_seed=42,test_budget=1,prompt_template_version='phase3-frozen-validation-v1',created_at=now,target_memory_profile=TargetMemoryProfile(max_retrieved_records=2,context_character_budget=800,output_token_limit=2048))
 case=TestCase(test_id=trial['id'],run_id=audit.run_id,dimension='conflict_resolution',prompt=trial['prompt'],expected_behavior='',supporting_memory_ids=[],generator_version='phase3-frozen-validation-v1',target_memory_context=trial['context'])
 row=next((r for r in report['trials'] if r['id']==trial['id']),None)
 if row is None:
  row={'id':trial['id'],'condition':trial['condition'],'configuration':audit.model_dump(mode='json'),'context':trial['context']};report['trials'].append(row)
 if 'error_type' in row:row.setdefault('recovered_script_errors',[]).append(row.pop('error_type'))
 save()
 try:
  response=TargetResponse.model_validate(row['response']) if 'response' in row else HttpTargetAIConnector().execute(case,audit)
  row['response']=response.model_dump(mode='json');save()
  contract=response.execution_metadata.request_contract.model_dump(mode='json')
  payload=build_openrouter_target_payload(model=plan['model'],instructions=private_context_instruction(case,audit.target_configuration),prompt=target_question_input(case.prompt),temperature=0,max_output_tokens=2048,provider_options=contract['provider']['value'])
  assert request_contract_sha256(payload)==contract['payload_sha256'];row['verified_request_payload']=payload
  text=response.response_text.lower();row['task_criterion_passed']=all(re.search(r'\b'+re.escape(v)+r'\b',text) for v in trial['expected_options']) and bool(re.search(r'clarif|ask[^.!?]{0,60}(?:which|user)|which[^.!?]{0,60}(?:precedence|controls)',text))
 except Exception as exc:
  row['error_type']=type(exc).__name__;report['status']='failed';save();raise
 save();print(trial['id'],row['task_criterion_passed'],flush=True)
report['status']='completed';report['finished_at_utc']=datetime.now(timezone.utc).isoformat();save()
