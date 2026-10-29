"""Verify v39 and pair only exact source-evidence, question and reference matches with v37."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'output/proposal-delivery/ac2-v37-same-source-development-20261029-v1'
NEW=ROOT/'output/proposal-delivery/ac2-v39-same-source-development-20261029-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
new=read(NEW/'ledger.json'); old=read(OLD/'ledger.json'); protocol=read(NEW/'protocol.json'); previous=read(OLD/'protocol.json')
assert new['protocol_sha256']==sha(NEW/'protocol.json') and old['protocol_sha256']==sha(OLD/'protocol.json')
assert protocol['prior_protocol_sha256']==sha(OLD/'protocol.json') and protocol['source_sha256']==previous['source_sha256']
assert [x['history_id'] for x in new['histories']]==[x['history_id'] for x in old['histories']]==protocol['history_ids']
assert len(new['histories'])==30 and 'finished_at_utc' in new
assert protocol['settings']['model_calls'] is False and protocol['settings']['target_execution'] is False and protocol['settings']['scope_review_execution'] is True

def stable_memory(mem,byid):
 links=[]
 for r in mem.get('relationships',[]):
  target=byid.get(r['target_memory_id'])
  if not target: raise ValueError('Unresolved relationship endpoint; cannot assert exact pairing.')
  links.append((r['type'],target['canonical_value'],tuple(sorted(target['source_message_ids'])),tuple(sorted(r.get('evidence_message_ids') or []))))
 return (mem['canonical_value'],tuple(sorted(mem['source_message_ids'])),tuple(sorted(links)))

def extract(ledger,require_scope):
 entries=[];history_states=Counter();rejected_reasons=Counter();dims=Counter();before=Counter();after=Counter();sizes=Counter()
 for entry in ledger['histories']:
  history_states[entry['status']]+=1
  assert all(not r['path'].endswith(('/execute','/evaluate')) for r in entry['requests'])
  audits=[r for r in entry['requests'] if r['method']=='POST' and r['path']=='/audits']
  if audits:
   settings=audits[0]['request']; assert settings['pipeline_provider']=='rule_based' and settings['provider']=='rule_based' and settings['test_budget']==4
  obs=entry.get('generation_observations',[])
  assert obs and len(obs[-1]['rejected_candidates'])==obs[-1]['rejected_candidate_count']
  rejected_reasons.update(r['reason'] for r in obs[-1]['rejected_candidates'])
  if entry['status']=='generation_failed':
   assert entry['generation_error']['http_status']==422 and obs[-1]['generated_test_count']==0
   continue
  if entry['status']!='completed': raise ValueError('Incomplete/failed non-generation step: '+entry['status'])
  memories={m['memory_id']:m for m in entry['simulated_confirmed_memories']}; sizes[len(entry['tests'])]+=1
  pre={t['test_id']:t for t in entry['review']['tests']}
  post={t['test_id']:t for t in entry['scope_review']['tests']} if require_scope else {}
  assert set(pre)=={t['test_id'] for t in entry['tests']}
  if require_scope: assert set(post)==set(pre)
  for test in entry['tests']:
   base=pre[test['test_id']]; later=post.get(test['test_id'])
   if later:
    for field in ('dimension','prompt','expected_behavior','supporting_memory_ids','test_type'):
     assert base[field]==later[field]
   support=tuple(sorted(stable_memory(memories[mid],memories) for mid in test['supporting_memory_ids']))
   key=(entry['history_id'],test['dimension'],test['test_type'],test['prompt'],test['expected_behavior'],support)
   data={'history_id':entry['history_id'],'run_id':entry['run_id'],'test_id':test['test_id'],'pre_status':base['quality_status'],
         'post_scope_status':later['quality_status'] if later else None}
   entries.append((key,data));dims[test['dimension']]+=1;before[base['quality_status']]+=1
   if later:after[later['quality_status']]+=1
 return entries,{'history_status':dict(history_states),'saved_questions':sum(dims.values()),'dimensions':dict(dims),
                 'questions_per_successful_history':dict(sorted(sizes.items())),
                 'pre_scope_status':dict(before),'post_scope_status':dict(after),
                 'rejected_candidates':sum(rejected_reasons.values()),'rejection_reasons':dict(rejected_reasons)}
old_entries,old_counts=extract(old,False);new_entries,new_counts=extract(new,True)
old_by=defaultdict(list);new_by=defaultdict(list)
for k,v in old_entries:old_by[k].append(v)
for k,v in new_entries:new_by[k].append(v)
pairs=[];ambiguous=0
for key in old_by.keys() & new_by.keys():
 if len(old_by[key])!=1 or len(new_by[key])!=1:
  ambiguous+=max(len(old_by[key]),len(new_by[key])); continue
 pairs.append({'old':old_by[key][0],'new':new_by[key][0]})
pairs.sort(key=lambda x:(x['old']['history_id'],x['old']['test_id']))
assert len(pairs)<=min(len(old_entries),len(new_entries))
comparison={'format':'ac2-v37-v39-strict-pairs-v1','old_ledger_sha256':sha(OLD/'ledger.json'),'new_ledger_sha256':sha(NEW/'ledger.json'),
 'pairing_rule':'Identical history, ability, test type, exact question and reference text, cited facts, source message IDs and relationship endpoints; duplicate/ambiguous keys excluded.',
 'matched_questions':len(pairs),'unmatched_old':len(old_entries)-len(pairs),'unmatched_new':len(new_entries)-len(pairs),'ambiguous_items_excluded':ambiguous,
 'paired_pre_status_transitions':dict(Counter(x['old']['pre_status']+' -> '+x['new']['pre_status'] for x in pairs)),
 'paired_new_scope_status':dict(Counter(x['new']['post_scope_status'] for x in pairs)),
 'pairs':pairs}
with (NEW/'strict-pairs.json').open('x',encoding='utf8') as f:json.dump(comparison,f,indent=2,ensure_ascii=False);f.write('\n')
summary={'format':'ac2-v39-same-source-development-verified-summary-v1','protocol_sha256':sha(NEW/'protocol.json'),
 'ledger_sha256':sha(NEW/'ledger.json'),'prior_ledger_sha256':sha(OLD/'ledger.json'),'strict_pairs_sha256':sha(NEW/'strict-pairs.json'),
 'planned_histories':30,'maximum_questions_per_history':4,'v37':old_counts,'v39':new_counts,
 'strict_pair_count':len(pairs),'unmatched_v37':comparison['unmatched_old'],'unmatched_v39':comparison['unmatched_new'],
 'paid_model_calls':0,'provider_reported_cost_usd':None,
 'notes':['The collector summary merges rejected candidate counts into history status; this verified summary separates them.',
 'Same 30 AI-authored related histories previously observed during development; this is not independent validation.',
 'Questions and simulated source confirmations are not human validated; no target answers were generated.',
 'Matching requires exact question/reference/evidence identity and excludes ambiguous duplicate keys.',
 'The v39 scope check is optional; pending items require review and are not confirmed failures.',
 'No paid provider was called, so no provider invoice or reported cost exists.']}
with (NEW/'summary-verified.json').open('x',encoding='utf8') as f:json.dump(summary,f,indent=2,ensure_ascii=False);f.write('\n')
print(json.dumps(summary,ensure_ascii=False))
