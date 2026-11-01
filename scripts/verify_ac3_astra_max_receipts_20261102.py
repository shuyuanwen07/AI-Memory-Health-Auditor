"""Check completed AC3 model receipts and bound judge inputs without API calls."""
import ast
from collections import Counter
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ac3_frozen_collector',ROOT/'scripts/ac3_astra_max_retest_20261101.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
c.check()
source=ast.parse((ROOT/'backend/app/evaluator/taxonomy_evaluator.py').read_text())
rubric=next(ast.literal_eval(n.value) for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RUBRIC' for t in n.targets))
private=c.read(c.OUT/'private-scorer-inputs.json')['items']
actual={x['test']['test_id']:x for x in c.collect_inputs()}
assert len(private)==120 and len(actual)==120
assert all(c.digest(x)==c.digest(actual[x['test']['test_id']]) for x in private)
scores=[c.read(p) for p in (c.OUT/'candidate-scores').glob('*.json')]
assert len(scores)==120 and len({x['test_id'] for x in scores})==120
inputs={x['test']['test_id']:x for x in private}
for score in scores:
    assert score['state']=='returned'
    assert score['provider']=='openai' and score['model']==score['reported_model']=='gpt-6-astra'
    assert score['reasoning_effort']=='max' and score['request_attempts']==1
    assert score['output_token_limit']==8192 and score['completion_status']=='completed' and score['http_status']==200
    item=inputs[score['test_id']]
    memories=[{'memory_id':m['memory_id'],'canonical_value':m['canonical_value'],'timestamp':m.get('timestamp')} for m in item['memories']]
    prompt='Question: '+item['test']['prompt']+'\nTarget answer: '+item['response']['response_text']+'\nConfirmed memory records: '+json.dumps(memories,ensure_ascii=False)
    payload={'model':'gpt-6-astra','reasoning':{'effort':'max'},'max_output_tokens':8192,'instructions':rubric,'input':prompt,
        'text':{'format':{'type':'json_schema','name':'ac3_taxonomy_judgment','strict':True,'schema':c.SCHEMA}}}
    assert c.digest(payload)==score['request_payload_sha256']
baseline=c.read(c.OUT/'baseline-scores.json')
assert len(baseline['items'])==120 and {x['test_id'] for x in baseline['items']}==set(inputs)
assert all(x['response_id']==inputs[x['test_id']]['response']['response_id'] for x in baseline['items'])
report={'provider':'openai','model':'gpt-6-astra','reasoning_effort':'max','protocol_sha256':c.sha(c.OUT/'protocol.json'),
    'target_answers_verified':120,'candidate_judgments_verified':120,'offline_baseline_verified':120,
    'same_saved_answers_for_both_scorers':True,'all_candidate_request_payload_fingerprints_verified':True,
    'candidate_inputs':'Only exact question, saved target answer and confirmed memory values/timestamps. No expected behavior, intended category or human label in model requests.',
    'candidate_actual_models':dict(Counter(x['reported_model'] for x in scores)),
    'candidate_request_attempts':dict(Counter(x['request_attempts'] for x in scores)),
    'candidate_usage':{key:sum((x.get('usage') or {}).get(key) or 0 for x in scores) for key in ['input_tokens','output_tokens','total_tokens']},
    'candidate_reasoning_tokens':sum(((x.get('usage') or {}).get('output_tokens_details') or {}).get('reasoning_tokens') or 0 for x in scores),
    'raw_reference_labels':'Independent AI reviews and subsequent human confirmation are separate; no automatic score is treated as gold.',
    'new_answer_human_confirmation':'pending',
    'implementation_sha256':{str(path.relative_to(ROOT)):c.sha(path) for path in [ROOT/'scripts/ac3_astra_max_retest_20261101.py',ROOT/'scripts/ac3_astra_max_review_packets_20261102.py',ROOT/'scripts/ac3_astra_max_offline_baseline_20261102.py',Path(__file__)]}}
c.write(c.OUT/'scorer-receipt-verification.json',report)
print(json.dumps(report,indent=2))
