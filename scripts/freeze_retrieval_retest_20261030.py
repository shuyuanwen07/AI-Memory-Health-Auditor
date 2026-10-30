"""Freeze the selected source evidence for an exploratory paired retest.

The source outcomes are already known, so this is not a held-out study.
No target calls, API writes, reviewer labels, or performance thresholds occur.
"""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'output/experiment-a-expanded-20261030'
ledger=D/'four-scenario-v7-question-ledger.json';execution=D/'four-scenario-v7-execution-ledger.json';confirmation=D/'v7-answer-user-confirmation.json';target=D/'retrieval-retest-protocol.json'
if target.exists():raise SystemExit('Existing frozen protocol retained; do not overwrite')
sources=json.loads(ledger.read_text());runs=json.loads(execution.read_text())['conditions']; rows=[]
for history_id,history in sources['histories'].items():
 if len(history['suites'])!=3:raise SystemExit('Incomplete source condition count')
 for suite in history['suites']:
  if len(suite['tests'])!=4:raise SystemExit('Incomplete source question suite')
  rid=suite['run_id']; assert runs[rid]['status']=='completed_answer_review_pending'
  for test in suite['tests']:
   rows.append({'history_id':history_id,'method':suite['method'],'source_run_id':rid,'source_test_id':test['test_id'],'question':test['prompt'],'dimension':test['dimension'],'expected_behavior':test['expected_behavior'],'supporting_memory_ids':test['supporting_memory_ids']})
assert len(rows)==48 and len({r['source_test_id'] for r in rows})==48
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol={'format':'retrieval-retest-exploratory-v1','frozen_utc':datetime.now(timezone.utc).isoformat(),'source_question_ledger_sha256':sha(ledger),'source_execution_ledger_sha256':sha(execution),'human_confirmation_sha256':sha(confirmation),'planned_pairs':48,'source_histories':4,'source_methods':3,'baseline_strategy':'weak_first_hit','candidate_strategy':'relationship_bundle','controls':['same frozen questions, expected behaviours, support IDs, source histories','same target provider/model, weak reader configuration, profile, temperature, output cap, memory capacity and maintenance','one fresh target answer per candidate question; retain baseline answers and tests'], 'metrics':'User-confirmed human reference pass/fail/uncertain per paired answer, differences in pass counts and paired transitions; retain automated scores separately.', 'limitations':['Exploratory after baseline responses were observed; no causal claim outside these selected cases.','Four related synthetic source histories; 48 answers are correlated across methods and same history.','The model provider controls sampling; fixed nominal settings do not guarantee identical random draws.','User-confirmed references following two AI reviews do not equal two independent human reviews.','The bundled memory intervention changes the context presented to the model and may increase token cost; inspect actual traces.'], 'questions':rows}
target.write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n');print('Frozen',len(rows),'source questions to',target)
