"""Source-bind a post-outcome B retrieval contrast; no new target calls."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/b-freshness-trace-diagnostic-20261029-v1'
KEY=ROOT/'output/proposal-delivery/experiment-b-four-strategy-20261029-v1/private-review-key.json'
REVIEW=ROOT/'output/proposal-delivery/ac1-ac2-b-return-20261029-v1/normalized-user-confirmed'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
 mapping=load(KEY)['mapping'];reviewers=[load(REVIEW/f'b-reviewer-{i}.json') for i in (1,2)]
 row={};all_cases={}
 for slug,strategy in [('strong','strong_rule_based'),('scope','scope_aware')]:
  matches=[(k,v) for k,v in mapping.items() if v['history_id']=='P4-H1' and v['dimension']=='freshness' and v['repetition']==1 and v['strategy']==strategy]
  assert len(matches)==1
  bid,m=matches[0];trace=load(OUT/f'b-{slug}-trace.json');result=load(OUT/f'b-{slug}-result.json')
  assert trace['run_id']==result['run_id']==m['run_id'] and trace['memory_strategy']==strategy
  retrieval=next(x for x in trace['retrievals'] if x['test_id']==m['test_id'])
  answer=next(x for x in result['answers'] if x['test']['test_id']==m['test_id'])
  assert hashlib.sha256(answer['response']['response_text'].encode()).hexdigest()==m['answer_sha256']
  assert retrieval['question']==answer['test']['prompt']
  verdicts=[next(x['verdict'] for x in rev['answer_reviews'] if x['blind_id']==bid) for rev in reviewers]
  assert verdicts==(['fail','fail'] if slug=='strong' else ['pass','pass'])
  assert answer['evaluation']['passed'] is True
  records={x['memory_id']:x for x in trace['records']}
  selected=[records[x] for x in retrieval['selected_memory_ids']]
  old=any('mysql' in x['canonical_value'].lower() for x in selected)
  new=any('postgresql' in x['canonical_value'].lower() for x in selected)
  assert new and old==(slug=='scope')
  row[strategy]={'run_id':m['run_id'],'test_id':m['test_id'],'selected_count':len(selected),'old_database_retrieved':old,'new_database_retrieved':new,
                 'human_review_verdicts':verdicts,'saved_automatic_verdict':'pass','answer_sha256':m['answer_sha256']}
  all_cases[strategy]=answer
 assert all_cases['strong_rule_based']['test']['prompt']==all_cases['scope_aware']['test']['prompt']
 assert all_cases['strong_rule_based']['test']['expected_behavior']==all_cases['scope_aware']['test']['expected_behavior']
 out={'history':'P4-H1','repetition':1,'dimension':'freshness','strategies':row,
      'sources':{str(p.relative_to(ROOT)):sha(p) for p in [KEY,REVIEW/'b-reviewer-1.json',REVIEW/'b-reviewer-2.json',OUT/'b-strong-trace.json',OUT/'b-scope-trace.json',OUT/'b-strong-result.json',OUT/'b-scope-result.json']},
      'scope':'Post-outcome analysis of one selected synthetic example. Reviewers used AI assistance and their independence was user-reported. Retrieval shows what was supplied, not general model causality; the saved automatic evaluator incorrectly passed this human-failed answer in this example.'}
 (OUT/'analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
