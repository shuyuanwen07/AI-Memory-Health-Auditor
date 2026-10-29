"""Prepare scoped synthetic-source corrections without changing reviewed files.

This is an AI author's self-check, not an independent review. The revision still
requires both reviewers' judgments for every modified history and cannot freeze
or execute any study.
"""
import argparse, copy, hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_ac3_diverse_candidate_expansion import review_packet
PARENT=ROOT/'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v5'
SOURCE_HASH='31aaf7880282c14c9ee1640e803639071af0a62450623cf077f01daf465a89dd'
PLAN_HASH='97b431272a30ce24e76417bd12e00478bd3b614a6ee0a42acd074a37299c08d1'
CHANGED=['AC3-H09','AC3-H10','AC3-H13','AC3-H15','AC3-H16','AC3-H18','AC3-H19','AC3-H20','AC3-H21','AC3-H23']

def sha(data): return hashlib.sha256(data).hexdigest()
def dump(x,pretty=True): return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode() if pretty else json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def build(old_source,old_plan):
 if sha(old_source)!=SOURCE_HASH or sha(old_plan)!=PLAN_HASH: raise ValueError('The parent source and fact plan differ from v5')
 src=json.loads(old_source); plan=json.loads(old_plan); old_src=copy.deepcopy(src); old_plan_obj=copy.deepcopy(plan)
 byid={c['history_id']:c for c in src['cases']}
 def fact(hid,fid): return next(f for f in plan['histories'][hid]['facts'] if f['memory_id']==hid+'-'+fid)
 def replace_fact_source(hid,fid,previous,new):
  f=fact(hid,fid)
  if f['source_span']!=previous: raise ValueError('Unexpected original fact source span')
  source=next(m for m in byid[hid]['source_messages'] if m['message_id']==f['source_message_id'])
  if source['text'].count(previous)!=1 or f['canonical_value'].count(previous)!=1: raise ValueError('Source/canonical anchor not unique')
  source['text']=source['text'].replace(previous,new); f['source_span']=new; f['canonical_value']=f['canonical_value'].replace(previous,new)
 def replace_canonical(hid,fid,previous,new):
  f=fact(hid,fid)
  if f['canonical_value'].count(previous)!=1: raise ValueError('Canonical anchor not unique')
  f['canonical_value']=f['canonical_value'].replace(previous,new)
 def replace_expected(hid,old,new):
  q=next(q for q in byid[hid]['tests'] if q['dimension']=='conflict_resolution')
  if q['expected_behavior']!=old: raise ValueError('Expected-answer anchor mismatch')
  q['expected_behavior']=new
 replace_canonical('AC3-H09','F5','its sole approved supply voltage','the train model’s sole approved supply voltage')
 replace_fact_source('AC3-H10','F1','The seed packets for the balcony trial are labelled basil.','The seed packets for the balcony trial contain basil seeds and are labelled basil.')
 replace_fact_source('AC3-H13','F1','The shared kitchen uses a purple key fob.','The shared kitchen is opened using a purple key fob.')
 replace_canonical('AC3-H15','F5','its sole final departure','the trial shuttle’s sole final departure')
 replace_fact_source('AC3-H16','F5','An active signed delivery note instead names the hall as the sole final pickup point.','An active signed delivery note instead names the hall, a physical place distinct from the depot, as the sole final pickup point.')
 replace_fact_source('AC3-H18','F4','The active robot test configuration says the sole approved battery type is rechargeable.','The active robot test configuration says the sole approved battery must be rechargeable.')
 replace_fact_source('AC3-H18','F5','The active signed technician configuration says the sole approved battery type is alkaline.','The active signed technician configuration says the sole approved battery must not be rechargeable.')
 replace_expected('AC3-H18','Rechargeable and alkaline are conflicting sole-approved types; confirm with the lab.','The rechargeable and non-rechargeable requirements conflict; confirm with the lab.')
 replace_fact_source('AC3-H19','F5','The active signed library notice says the only final registration contact is Noor.','The active signed library notice says the only final registration contact is Noor, a different person from Maya.')
 replace_fact_source('AC3-H20','F5','The signed active setup sheet says the only final timestamp basis is local time.','The signed active setup sheet says the only final timestamp basis is local time at UTC+10.')
 replace_expected('AC3-H20','UTC and local time are conflicting sole-basis claims; confirm the setting.','UTC and UTC+10 local time are conflicting sole-basis claims; confirm the setting.')
 replace_fact_source('AC3-H21','F5','The active signed pickup order names the loading bay as the sole final pickup point.','The active signed pickup order names the loading bay, physically distinct from the garden entrance, as the sole final pickup point.')
 replace_fact_source('AC3-H23','F5','The active signed outing notice says the single final destination is Lakeside.','The active signed outing notice says the single final destination is Lakeside, a location distinct from Hilltop.')
 before={c['history_id']:c for c in old_src['cases']}; after={c['history_id']:c for c in src['cases']}
 actual=sorted(h for h in before if before[h]!=after[h] or old_plan_obj['histories'][h]!=plan['histories'][h])
 if actual!=CHANGED: raise ValueError('Unexpected changed histories')
 for hid,c in after.items():
  messages={m['message_id']:m['text'] for m in c['source_messages']}
  facts=plan['histories'][hid]['facts']; mapping={f['memory_id']:f['source_message_id'] for f in facts}
  for f in facts:
   if f['source_message_id'] not in messages or f['source_span'] not in messages[f['source_message_id']]: raise ValueError('Fact span not in cited source')
  for rel in plan['histories'][hid]['relationships']:
   if hid not in {f'AC3-H{i:02d}' for i in range(1,9)} and not {mapping[rel['memory_id']],mapping[rel['target_memory_id']]}.issubset(rel['evidence_message_ids']): raise ValueError('Relation evidence misses endpoint')
   if not set(rel['evidence_message_ids']).issubset(messages): raise ValueError('Relation evidence not in history')
  for q in c['tests']:
   if not set(q['supporting_source_message_ids']).issubset(messages):raise ValueError('Question evidence not in history')
 return src,plan

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 old_source=(PARENT/'candidate-inputs.json').read_bytes();old_plan=(PARENT/'proposed-fact-plan.json').read_bytes();src,plan=build(old_source,old_plan)
 source_bytes=dump(src);plan_bytes=dump(plan,False); hs=sha(source_bytes);hp=sha(plan_bytes)
 manifest={'format':'ac3-expanded-repair-manifest-v1','parent_source_sha256':sha(old_source),'parent_fact_plan_sha256':sha(old_plan),
   'revised_source_sha256':hs,'revised_fact_plan_sha256':hp,'changed_history_ids':CHANGED,
   'unchanged_added_history_ids':[f'AC3-H{i:02d}' for i in range(9,31) if f'AC3-H{i:02d}' not in CHANGED],
   'unchanged_original_histories':8,'review_required_for_changed_histories':True,'frozen':False,'model_called':False,
   'review_provenance':'Corrections are an AI author self-check, not independent or human review.',
   'limitation':'Candidate sample is controlled synthetic data, not randomly sampled histories.'}
 manifest_bytes=dump(manifest); hm=sha(manifest_bytes)
 a.output_dir.mkdir(parents=True,exist_ok=False)
 (a.output_dir/'candidate-inputs.json').write_bytes(source_bytes);(a.output_dir/'proposed-fact-plan.json').write_bytes(plan_bytes);(a.output_dir/'manifest.json').write_bytes(manifest_bytes)
 changed=[c for c in src['cases'] if c['history_id'] in CHANGED]
 for slot in (1,2):
  review=review_packet(changed,plan,hs,hp,slot); review['parent_source_sha256']=sha(old_source);review['revision_manifest_sha256']=hm
  review['status']='AI author revision; independent human review required';review['说明']='仅复核本次修改的 10 段。每段4题分别审来源与预期（valid/invalid/uncertain）；8条拟议事实整段判 accept/revise/uncertain；3条关系各判 valid/invalid/uncertain；遗漏事实没有则填 []。有问题在 comment 注明编号。其他未变段继承 v5 两份原始审核，前 8 段保留既有审核。'
  (a.output_dir/f'reviewer-{slot}.json').write_bytes(dump(review))
 print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
