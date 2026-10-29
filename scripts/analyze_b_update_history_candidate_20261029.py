"""Replay only candidate eligibility on saved traces, not full retrieval or target output."""
import hashlib,json,os
from pathlib import Path
from types import SimpleNamespace
from app.schemas import MemoryStrategy
from scripts.b_update_history_candidate_20261029 import include_update_history
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'output/proposal-delivery/b-freshness-all-traces-20261029-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 analysis=json.loads((DIR/'analysis.json').read_text());results=[]
 for row in analysis['rows']:
  if row['strategy']!='strong_rule_based':continue
  path=DIR/f"{row['run_id']}.json";assert sha(path)==row['trace_sha256'];trace=json.loads(path.read_text())
  retrieval=next(x for x in trace['retrievals'] if x['test_id']==row['test_id']); ranks={x['memory_id']:x for x in retrieval['ranking_evidence']}
  candidates=[];relations=[]
  for record in trace['records']:
   rank=ranks[record['memory_id']]
   candidates.append({'record':SimpleNamespace(id=record['memory_id'],lifecycle_state=record['lifecycle_state']),
    'eligible':rank['eligible'],'category_match':'topic_category_match' in rank['reason'],
    'relevance':rank['relevance'],'reason':rank['reason']})
   for rel in record['relationships']:
    relations.append(SimpleNamespace(memory_id=record['memory_id'],target_memory_id=rel['target_memory_id'],relationship_type=rel['type']))
  prior={c['record'].id for c in candidates if c['eligible']};include_update_history(candidates,relations,retrieval['question'],MemoryStrategy.STRONG_RULE_BASED)
  new={c['record'].id for c in candidates if c['eligible']}-prior
  results.append({'history':row['history'],'repeat':row['repeat'],'newly_eligible_count':len(new),'question':retrieval['question'],'trace_sha256':sha(path)})
 assert len(results)==9
 output={'source_analysis_sha256':sha(DIR/'analysis.json'),'candidate_sha256':sha(ROOT/'scripts/b_update_history_candidate_20261029.py'),
  'cases':len(results),'with_additional_eligible_records':sum(r['newly_eligible_count']>0 for r in results),'rows':results,
  'scope':'Post-outcome eligibility replay only: no ranking, profile budget, full API retrieval, target response, evaluation, human review, or independent generalisation claim.'}
 Path(os.environ.get('B_CANDIDATE_OUTPUT',str(DIR/'candidate-eligibility-replay.json'))).write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({k:v for k,v in output.items() if k!='rows'},indent=2))
if __name__=='__main__':main()
