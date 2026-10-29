"""Recalculate same-source development counts; preserves original collector summary."""
from collections import Counter
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/ac2-v37-same-source-development-20261029-v1'
OLD=ROOT/'output/proposal-delivery/ac2-v4-prospective-product-20261029-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
ledger=read(OUT/'ledger.json'); protocol=read(OUT/'protocol.json'); original=read(OLD/'summary.json'); original_ledger=read(OLD/'ledger.json')
assert ledger['protocol_sha256']==sha(OUT/'protocol.json')
assert sha(ROOT/protocol['source_path'])==protocol['source_sha256']
assert sha(OLD/'protocol.json')==protocol['prior_protocol_sha256']
assert [e['history_id'] for e in ledger['histories']]==protocol['history_ids']
assert [e['history_id'] for e in original_ledger['histories']]==protocol['history_ids']
assert len(ledger['histories'])==30 and 'finished_at_utc' in ledger
assert protocol['settings']['model_calls'] is False and protocol['settings']['target_execution'] is False
statuses=Counter(); dims=Counter(); reasons=Counter(); sizes=Counter(); rejected=0; short=0
for entry in ledger['histories']:
 statuses[entry['status']]+=1
 assert all(not r['path'].endswith(('/execute','/evaluate')) for r in entry['requests'])
 observations=entry.get('generation_observations',[])
 assert observations and observations[-1]['agent_version']=='rule-based-v37'
 observation=observations[-1]; rejected+=observation['rejected_candidate_count']
 assert len(observation['rejected_candidates'])==observation['rejected_candidate_count']
 assert all(c['prompt'] and c['reason'] and c['supporting_memory_ids'] for c in observation['rejected_candidates'])
 reasons.update(c['reason'] for c in observation['rejected_candidates'])
 if entry['status']=='completed':
  tests=entry['tests']; assert len(tests)==entry['review']['generated_test_count']==observation['generated_test_count']
  assert all(t['generator_version']=='rule-based-v37' for t in tests)
  dims.update(t['dimension'] for t in tests);sizes[len(tests)]+=1
  short+=int(entry['review']['count_target_met'] is False)
 elif entry['status']=='generation_failed':
  assert entry['generation_error']['http_status']==422 and observation['generated_test_count']==0
 else: raise ValueError('Unexpected run state '+entry['status'])
result={'format':'ac2-v37-same-source-development-verified-summary-v1',
 'protocol_sha256':sha(OUT/'protocol.json'),'ledger_sha256':sha(OUT/'ledger.json'),
 'collector_summary_sha256':sha(OUT/'summary.json'),'prior_summary_sha256':sha(OLD/'summary.json'),
 'planned_histories':30,'history_status_counts':dict(statuses),'saved_questions':sum(dims.values()),
 'saved_questions_by_dimension':dict(dims),'question_counts_per_successful_history':dict(sorted(sizes.items())),
 'successful_histories_below_maximum':short,'zero_question_histories':statuses.get('generation_failed',0),
 'rejected_candidates':rejected,'rejection_reasons':dict(reasons),
 'prior_development_comparison':{'history_successes':original['histories_generated'],'history_failures':original['generation_failed'],'saved_questions':original['saved_questions']},
 'paid_model_calls':0,'provider_reported_cost_usd':None,
 'notes':['Corrects the collector summary display: rejected_candidates is a candidate count, not a history status.',
          'No paid provider was called, so no provider bill or cost receipt exists.',
          'Post-outcome development comparison on the same 30 AI-authored histories; not independent validation.',
          'Rule-extracted memories were provisionally confirmed by automation; question validity was not judged by humans.',
          'The 29 previous failed histories did not provide individual question labels.',
          'Four is a maximum per history, not a mandatory minimum.']}
with (OUT/'summary-verified.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
print(json.dumps(result,ensure_ascii=False))
