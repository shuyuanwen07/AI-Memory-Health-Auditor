"""Verify saved browser/API exports and recover exact request bodies by receipt hash.

No provider request is sent. Payloads are recovered from recorded delivery IDs
and frozen templates, and accepted only when equal to the original wire hash.
"""
import csv,json,sys,hashlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.schemas import TestCase,TargetConfiguration
from app.target_ai.rule_based import private_context_instruction,target_question_input
from app.target_ai.openrouter import build_openrouter_target_payload
from app.target_ai.request_contracts import request_contract_sha256
p=ROOT/'artifacts/local/phase12-20261027/final';state=json.loads((p/'live-verification.json').read_text());requests=[]
for run in state['runs']:
    records={m['memory_id']:m['canonical_value'] for m in run['trace']['records']}
    for response in run['responses']:
        retrieval=next(r for r in run['trace']['retrievals'] if r['test_id']==response['test_id'])
        receipt=retrieval['memory_input'];assert receipt['sent_memory_ids'] is not None
        context=[records[mid] for mid in receipt['sent_memory_ids']]
        test=TestCase.model_validate(next(t for t in run['tests'] if t['test_id']==response['test_id'])).model_copy(update={'target_memory_context':context})
        configuration=TargetConfiguration(run['configuration']['target_configuration'])
        instructions=private_context_instruction(test,configuration)
        assert hashlib.sha256(instructions.encode()).hexdigest()==receipt['instruction_sha256']
        c=response['execution_metadata']['request_contract']
        payload=build_openrouter_target_payload(model=c['model'],instructions=instructions,prompt=target_question_input(test.prompt),temperature=run['configuration']['temperature'],max_output_tokens=c['max_tokens']['value'],provider_options=c['provider']['value'])
        assert request_contract_sha256(payload)==c['payload_sha256']
        assert test.expected_behavior not in instructions
        requests.append({'run_id':run['run_id'],'test_id':test.test_id,'payload':payload,'payload_sha256':c['payload_sha256'],'verified_against_original_wire_receipt':True})
(p/'verified-request-bodies.json').write_text(json.dumps({'provenance':'Recovered from delivery receipts and frozen templates, verified byte-semantics against original wire hash; not a second model execution. Authorization headers excluded.','requests':requests},indent=2))
api=state['runs'][1]['result'];browser=json.loads((p/'browser-report.json').read_text())['result']
# Browser intentionally moves the sanitized profile to run_configuration.
api=json.loads(json.dumps(api));api['reproducibility'].pop('target_memory_profile',None)
assert browser==api
rows=list(csv.DictReader((p/'browser-report.csv').open()));answer_rows=[r for r in rows if r['Record type']=='Answer detail']
assert {r['Evaluation ID'] for r in answer_rows}=={e['evaluation_id'] for e in state['runs'][1]['evaluations']}
assert all(r['Outcome']=='Passed' for r in answer_rows)
assert next(r for r in rows if r['Record type']=='Audit summary')['Overall score (%)']=='100'
usage={key:sum(r['execution_metadata'].get(key) or 0 for run in state['runs'] for r in run['responses']) for key in ['input_tokens','output_tokens','total_tokens']}
manifest={'status':'verified','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'working_tree_modified':True,'requests_verified':len(requests),'browser_json_matches_api_except_documented_profile_sanitization':True,'browser_csv_matches_evaluations':True,'usage':usage,'estimated_standard_rate_usd':usage['input_tokens']*0.10/1000000+usage['output_tokens']*0.50/1000000,'pricing_basis':'https://openrouter.ai/openai/gpt-6-luna; estimate, not billing receipt','files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file() and f.name!='verification.json'}}
(p/'verification.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({k:v for k,v in manifest.items() if k!='files'}))
