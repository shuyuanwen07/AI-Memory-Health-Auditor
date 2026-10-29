"""Prepare two unlabelled blind review files for the saved development questions."""
import hashlib
import json
from pathlib import Path
import random
import zipfile

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'output/proposal-delivery/ac2-v40-same-source-development-20261029-v1'
OUT=STUDY/'blind-review-v2'
SOURCE=ROOT/'output/proposal-delivery/ac2-prospective-new-histories-20261029/histories.json'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def write(path,value):
 with path.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

protocol=json.loads((STUDY/'protocol.json').read_text()); ledger=json.loads((STUDY/'ledger.json').read_text()); summary=json.loads((STUDY/'summary-verified.json').read_text())
if sha(STUDY/'protocol.json')!=ledger['protocol_sha256'] or sha(STUDY/'ledger.json')!=summary['ledger_sha256'] or sha(SOURCE)!=protocol['source_sha256']:
 raise ValueError('Study source, protocol or ledger checksum changed.')
source={row['conversation_id']:row for row in json.loads(SOURCE.read_text())['conversations']}
if len(ledger['histories'])!=30 or [e['history_id'] for e in ledger['histories']]!=protocol['history_ids']:
 raise ValueError('History sequence differs from frozen protocol.')
items=[]; mapping={}; history_ids=set()
for entry in ledger['histories']:
 if entry['status']!='completed':continue
 hid=entry['history_id']; history_ids.add(hid)
 memories={m['memory_id']:m for m in entry['simulated_confirmed_memories']}
 for test in entry['tests']:
  item_id=hashlib.sha256((summary['ledger_sha256']+':'+test['test_id']).encode()).hexdigest()[:24]
  if item_id in mapping:raise ValueError('Duplicate blinded identifier.')
  supports=[]
  for memory_id in test['supporting_memory_ids']:
   if memory_id not in memories: raise ValueError('Referenced memory absent from saved source.')
   memory=memories[memory_id]
   supports.append({'memory_id':memory_id,'fact':memory['canonical_value'],
     'source_message_ids':memory['source_message_ids'],
     'proposed_relationships':[{'type':r['type'],'target_memory_id':r['target_memory_id'],
                                'evidence_message_ids':r.get('evidence_message_ids',[])} for r in memory.get('relationships',[])]})
  cited_ids={memory_id for memory_id in test['supporting_memory_ids']}
  related_ids={rel['target_memory_id'] for support in supports for rel in support['proposed_relationships']} - cited_ids
  if not related_ids.issubset(memories): raise ValueError('Relationship target missing from saved evidence.')
  related_context=[{'memory_id':mid,'fact':memories[mid]['canonical_value'],'source_message_ids':memories[mid]['source_message_ids']} for mid in sorted(related_ids)]
  items.append({'item_id':item_id,'history_id':hid,'ability':test['dimension'],
    'question':test['prompt'],'proposed_reference_answer':test['expected_behavior'],
    'cited_provisional_memories':supports, 'related_provisional_memory_context':related_context,
    'review':{'source_grounding':None,'question_executability':None,'reference_answer_validity':None,'notes':''}})
  mapping[item_id]={'history_id':hid,'run_id':entry['run_id'],'test_id':test['test_id'],
                    'supporting_memory_ids':test['supporting_memory_ids']}
if len(items)!=12 or len(history_ids)!=11:raise ValueError('Unexpected saved-question or history count.')
random.Random(42040).shuffle(items)
histories=[{'history_id':hid,'messages':source[hid]['messages']} for hid in sorted(history_ids)]
material={'histories':histories,'items':items}
material_sha=hashlib.sha256(canonical(material)).hexdigest()
OUT.mkdir(parents=True,exist_ok=False)
for number in (1,2):
 packet={'format':'ac2-development-question-blind-review-v1','reviewer_slot':number,'material_sha256':material_sha,
  'purpose':'Assess source grounding, question executability and proposed reference answer validity for saved development questions.',
  'instructions':'Work independently. Do not view the other reviewer’s decisions or the system quality assessments before judging. For each field enter valid, invalid or uncertain; use notes for evidence or uncertainty. Leave genuinely unresolved items uncertain. Record AI assistance and prior exposure truthfully. The source stories are synthetic and the extracted memories/relationships are provisional.',
  'allowed_values':['valid','invalid','uncertain'],
  'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'seen_other_review':None,'seen_system_quality_assessments':None,'used_ai_assistance':None},**material}
 write(OUT/f'reviewer-{number}.json',packet)
write(OUT/'private-mapping.json',{'format':'ac2-development-question-private-mapping-v1','material_sha256':material_sha,
 'ledger_sha256':summary['ledger_sha256'],'mapping':mapping,'unreviewable_generation_failures':19,
 'limitations':'Private mapping is not part of reviewer packets. The 19 histories with no saved question remain in the original ledger and are not assigned question-level labels.'})
instructions='''# 开发题双人盲审说明\n\n两个审核者分别填写自己的 JSON，不看对方内容或系统自动评判。每题的 `source_grounding`（来源依据）、`question_executability`（题目是否清楚可执行）和 `reference_answer_validity`（参考答案是否正确）填 `valid`、`invalid` 或 `uncertain`；有歧义就填 `uncertain`，在 `notes` 写明原因。\n\n填写开头的审核者声明，如实说明是否使用 AI 辅助。故事为 AI 编写的合成来源，记忆和关系是系统提取并由操作流程模拟确认的候选，不是已获人工验证的标准答案。历史是开发样本，不能将这些审核当作独立保留集评估。\n\n这里只含 11 段历史的 12 道已保存题；另外 19 段生成失败的原始记录保留在研究 ledger，不能据此判定具体题目对错。`private-mapping.json` 不提供给审核者，它用于事后对应原始运行。\n'''
(OUT/'填写说明.md').write_text(instructions,encoding='utf8')
for name,files in [('双人盲审包-12题-v2.zip',['填写说明.md','reviewer-1.json','reviewer-2.json']),('reviewer-1-盲审包.zip',['填写说明.md','reviewer-1.json']),('reviewer-2-盲审包.zip',['填写说明.md','reviewer-2.json'])]:
 with zipfile.ZipFile(OUT/name,'x',zipfile.ZIP_DEFLATED) as z:
  for file in files:z.write(OUT/file,file)
print(json.dumps({'questions':len(items),'reviewed_histories':len(histories),'failed_histories_preserved':19,'material_sha256':material_sha,'output':str(OUT)},ensure_ascii=False))
