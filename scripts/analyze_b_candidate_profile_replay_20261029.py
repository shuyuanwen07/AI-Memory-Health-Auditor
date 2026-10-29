"""Development replay of saved candidate ranks through the actual selector/profile."""
import hashlib,json,os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import MemoryStrategy
from app.schemas.target_profile import TargetMemoryProfile
from scripts.b_update_history_candidate_20261029 import include_update_history
ROOT=Path(__file__).resolve().parents[1];DIR=ROOT/'output/proposal-delivery/b-freshness-all-traces-20261029-v1'
PROTOCOL=ROOT/'output/proposal-delivery/experiment-b-four-strategy-20261029-v1/protocol.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 analysis=json.loads((DIR/'analysis.json').read_text());p=json.loads(PROTOCOL.read_text());profile=TargetMemoryProfile.model_validate(p['target']['profile']);store=SqlTargetMemoryStore(None,profile=profile)
 rows=[]
 for row in analysis['rows']:
  if row['strategy']!='strong_rule_based':continue
  path=DIR/f"{row['run_id']}.json";assert sha(path)==row['trace_sha256'];trace=json.loads(path.read_text());rt=next(x for x in trace['retrievals'] if x['test_id']==row['test_id']);ranks={x['memory_id']:x for x in rt['ranking_evidence']};candidates=[];relations=[]
  for rec in trace['records']:
   rank=ranks[rec['memory_id']];obj=SimpleNamespace(id=rec['memory_id'],lifecycle_state=rec['lifecycle_state'],canonical_value=rec['canonical_value'],scope=rec['scope'],write_order=rec['write_order'],observed_at=datetime.fromisoformat(rec['observed_at']) if rec['observed_at'] else None,source_message_ids=rec['source_message_ids'])
   candidates.append({'record':obj,'eligible':rank['eligible'],'category_match':'topic_category_match' in rank['reason'],'relevance':rank['relevance'],'reason':rank['reason'],'policy_score':rank['policy_score'],'conflict_targets':[e['target_memory_id'] for e in rec['relationships'] if e['type']=='CONFLICT'],'test_prompt':rt['question']})
   relations.extend(SimpleNamespace(memory_id=rec['memory_id'],target_memory_id=e['target_memory_id'],relationship_type=e['type']) for e in rec['relationships'])
  include_update_history(candidates,relations,rt['question'],MemoryStrategy.STRONG_RULE_BASED)
  test=SimpleNamespace(prompt=rt['question']);eligible=[c for c in candidates if c['eligible'] and c['relevance']>0]
  eligible=store._filter_profile_candidates(eligible,test);selected=store._apply_profile(store._select(eligible,MemoryStrategy.STRONG_RULE_BASED),test,MemoryStrategy.STRONG_RULE_BASED);ids={x['record'].id for x in selected}
  pairs=[(x.memory_id,x.target_memory_id) for x in relations if x.relationship_type=='UPDATE']
  rows.append({'history':row['history'],'repeat':row['repeat'],'run_id':row['run_id'],'test_id':row['test_id'],
   'question':rt['question'],'selected_context':[store._render_context(item) for item in selected],
   'both_update_endpoints_selected':any(a in ids and b in ids for a,b in pairs),'selected_count':len(ids),'trace_sha256':sha(path)})
 assert len(rows)==9
 out={'source_analysis_sha256':sha(DIR/'analysis.json'),'candidate_sha256':sha(ROOT/'scripts/b_update_history_candidate_20261029.py'),'profile':p['target']['profile'],'cases':len(rows),'both_endpoints_selected':sum(x['both_update_endpoints_selected'] for x in rows),'rows':rows,'scope':'Post-outcome reconstruction from saved candidate fields and actual selection/profile code, not a full live retrieval, target response, human validity or generalisation test.'}
 Path(os.environ.get('B_CANDIDATE_OUTPUT',str(DIR/'candidate-profile-replay.json'))).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('profile','rows')},indent=2))
if __name__=='__main__':main()
