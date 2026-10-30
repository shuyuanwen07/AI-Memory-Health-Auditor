"""Build condition-blind review packets; do not include automated verdicts."""
import json,hashlib,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/experiment-a-expanded-20261030'
runpath=D/'four-scenario-v7-execution-ledger.json';suitepath=D/'four-scenario-v7-question-ledger.json';sourcepath=D/'four-scenario-frozen-input.json'
run=json.loads(runpath.read_text());suites=json.loads(suitepath.read_text());source=json.loads(sourcepath.read_text())
byhist={h['history_id']:h for h in source['histories']};records=[];key={}
for hid,h in suites['histories'].items():
 for suite in h['suites']:
  rid=suite['run_id'];condition=run['conditions'][rid]
  if condition.get('status')!='completed_answer_review_pending':raise SystemExit(f'{rid}: execution incomplete')
  replies=condition['operations']['execute']['response'];tests={t['test_id']:t for t in suite['tests']}
  if len(replies)!=4 or {r['test_id'] for r in replies}!=set(tests):raise SystemExit(f'{rid}: incomplete answers')
  for r in replies:
   t=tests[r['test_id']];ident='CASE-'+hashlib.sha256(r['response_id'].encode()).hexdigest()[:16]
   if ident in key:raise SystemExit('Duplicate response')
   records.append({'case_id':ident,'source_messages':byhist[hid]['messages'],'question':t['prompt'],'expected_behavior':t['expected_behavior'],'answer':r['response_text'],'dimension':t['dimension'],'candidate_failure_patterns':byhist[hid]['candidate_failure_patterns']})
   key[ident]={'history_id':hid,'method':suite['method'],'run_id':rid,'test_id':r['test_id'],'response_id':r['response_id']}
if len(records)!=48:raise SystemExit(f'Expected 48 answers, received {len(records)}')
(D/'v7-blind-answer-key-private.json').write_text(json.dumps(key,ensure_ascii=False,indent=2)+'\n')
for idx in (1,2):
 rows=records.copy();random.Random(624+idx).shuffle(rows)
 packet={'format':'a-v7-blind-answer-review-v1','review_type':'AI-only independent review','instruction':'Review each answer against the source and question. Do not see automatic verdicts or the other reviewer. Mark pass/fail/uncertain, cite evidence; record candidate IDs only if the answer actually fails that pattern, and note any failures outside the candidate list. Correct current value need not repeat the old value unless explicitly required. Do not infer missing facts.','items':rows}
 (D/f'v7-blind-answer-review-input-{idx}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
print('Prepared two condition-blind packets, each with 48 target answers; no automatic verdicts included.')
