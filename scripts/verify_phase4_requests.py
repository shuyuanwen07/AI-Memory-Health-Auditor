"""Reconstruct B request bodies and bind every byte to saved HTTP-boundary SHA."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/app')
from app.schemas import AuditRun,TestCase
from app.target_ai.rule_based import private_context_instruction,target_question_input
from app.target_ai.openrouter import build_openrouter_target_payload
from app.target_ai.request_contracts import request_contract_sha256
p=Path(sys.argv[1]);b=json.loads(p.read_text());requests=[]
for h in b['scenarios']:
 for run in h['runs']:
  audit=AuditRun.model_validate(run['configuration']);tests={t['test_id']:t for t in run['tests']};records={r['memory_id']:r['canonical_value'] for r in run['trace']['records']}
  for response in run['responses']:
   meta=response['execution_metadata'];receipt=meta['memory_input'];c=meta['request_contract']
   test=TestCase.model_validate({**tests[response['test_id']],'expected_behavior':'','supporting_memory_ids':[],'target_memory_context':[records[k] for k in receipt['sent_memory_ids']]})
   instruction=private_context_instruction(test,audit.target_configuration);assert hashlib.sha256(instruction.encode()).hexdigest()==receipt['instruction_sha256']
   payload=build_openrouter_target_payload(model=audit.model,instructions=instruction,prompt=target_question_input(test.prompt),temperature=audit.temperature,max_output_tokens=audit.target_memory_profile.output_token_limit,provider_options=c['provider']['value'])
   assert request_contract_sha256(payload)==c['payload_sha256']
   requests.append({'run_id':run['run_id'],'response_id':response['response_id'],'payload':payload,'payload_sha256':c['payload_sha256'],'provenance':'Reconstructed exact body verified against original HTTP-boundary SHA256; no request resent','sampling_control':meta['sampling_control'],'sent_temperature':meta['sent_temperature']})
expected_count=int(sys.argv[2]) if len(sys.argv)>2 else 72
assert len(requests)==expected_count
filename=sys.argv[3] if len(sys.argv)>3 else ('A-verified-requests.json' if p.name.startswith('A-') else 'B-verified-requests.json')
assert Path(filename).name==filename
(p.parent/filename).write_text(json.dumps(requests,indent=2));print(str(expected_count)+'/'+str(expected_count)+' exact request-body hashes verified')
