"""Prepare independent, score-blind AI review materials for new paired answers."""
import json,hashlib,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/experiment-a-expanded-20261030'
run=json.loads((D/'retrieval-retest-execution.json').read_text());source=json.loads((D/'four-scenario-frozen-input.json').read_text());histories={h['history_id']:h for h in source['histories']};cases=[];key={}
for oldid,row in run['conditions'].items():
 if row.get('status')!='completed_review_pending':raise SystemExit('Retest condition incomplete')
 newtests={t['test_id']:t for t in row['operations']['candidate-tests']['response']}; replies=row['operations']['execute']['response'];h=histories[row['history_id']]
 if len(replies)!=4 or set(newtests)!={r['test_id'] for r in replies}:raise SystemExit('Question/answer mismatch')
 for r in replies:
  t=newtests[r['test_id']];id='PAIR-'+hashlib.sha256(r['response_id'].encode()).hexdigest()[:16]
  if id in key:raise SystemExit('Repeated response')
  cases.append({'case_id':id,'source_messages':h['messages'],'question':t['prompt'],'expected_behavior':t['expected_behavior'],'answer':r['response_text'],'dimension':t['dimension'],'candidate_failure_patterns':h['candidate_failure_patterns']})
  key[id]={'history_id':row['history_id'],'method':row['method'],'source_run_id':oldid,'candidate_run_id':row['candidate_run_id'],'test_id':r['test_id'],'response_id':r['response_id']}
if len(cases)!=48:raise SystemExit('Expected 48 new answers')
(D/'retrieval-retest-blind-key-private.json').write_text(json.dumps(key,ensure_ascii=False,indent=2)+'\n')
for idx in (1,2):
 rows=cases.copy();random.Random(1833+idx).shuffle(rows)
 packet={'review_type':'independent AI review; no human claim','instructions':'Review against provided source and actual question. The packet intentionally omits method, condition and automated scores. For each answer classify pass/fail/uncertain, cite source message IDs and reason. Matching current value need not repeat old value unless specifically asked. A specific-scope answer need not repeat general preference unless specifically asked. Do not assume missing evidence was supplied to the model.','items':rows}
 (D/f'retrieval-retest-blind-input-{idx}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
print('Prepared 48 new answers for two condition- and score-blind independent AI reviewers.')
