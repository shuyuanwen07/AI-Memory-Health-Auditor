"""Prepare genuine human review inputs; never submit an acceptance declaration."""
import argparse,hashlib,html,json,random,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-20261027'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
def api(path):
 req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=b'{}',headers={'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
def main():
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['templates','blind']);a=p.parse_args();b=json.loads((D/'B-live.json').read_text());hist=json.loads((ROOT/'datasets/phase4-candidate-v1/source-histories.json').read_text());sources={h['scenario_id']:h for h in hist}
 if a.stage=='templates':
  folder=D/'researcher-preexecution';folder.mkdir(exist_ok=True);plans=[]
  for h in b['scenarios']:
   file=folder/(h['scenario_id']+'.json')
   if file.exists():plans.append(json.loads(file.read_text()));continue
   source=next((r for r in h['runs'] if r.get('result')),None)
   if source is None:continue
   pack=api('/audits/'+source['run_id']+'/method-comparison')
   memories=[m for m in h['memories'] if m['status'] in ['confirmed','edited']]
   by_source={sid:m['memory_id'] for m in memories for sid in m['source_message_ids']}
   defs=[]
   for label,dimension,indices,description in [('STALE','freshness',[1,2],'Potential failure: answering with the superseded database rather than the explicit migration.'),('CONTEXT','appropriate_use',[3,4],'Potential failure: applying the general language preference instead of the course requirement.'),('CONFLICT','conflict_resolution',[5,6,7],'Potential failure: selecting one unresolved deployment instruction without clarification.')]:
    ids=[sources[h['scenario_id']]['messages'][i]['message_id'] for i in indices]
    defs.append({'defect_id':h['scenario_id']+'-'+label,'dimension':dimension,'supporting_memory_ids':sorted({by_source[sid] for sid in ids}),'source_message_ids':ids,'explanation':description})
   candidate={'scenario_id':h['scenario_id'],'source_run_id':source['run_id'],'source_messages':sources[h['scenario_id']]['messages'],'confirmed_memories':memories,'comparison':pack,'proposed_inventory':{**pack['inventory_template'],'defects':defs},'review_status':'AI-prepared candidate only. Researcher must verify source, potential defects and all four questions. No human declaration submitted.'}
   file.write_text(json.dumps(candidate,indent=2));plans.append(candidate)
  content=['<!doctype html><meta charset="utf-8"><title>Phase 4 researcher review</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto;line-height:1.5}article{border:1px solid #bbb;padding:20px;margin:20px 0}pre{white-space:pre-wrap}</style><h1>研究者执行前审查 / Researcher pre-execution review</h1><p>These are candidate materials, not confirmed human labels. Verify source, inventory, question, expected behaviour and evidence. Record edits and your researcher pseudonym. No condition has been generated or executed for A.</p>']
  for item in plans:
   content.append('<h2>'+item['scenario_id']+'</h2><h3>Source</h3>'+''.join('<p>'+html.escape(m['message_id']+': '+m['content'])+'</p>' for m in item['source_messages']))
   content.append('<h3>Potential defect inventory — confirm or edit</h3><pre>'+html.escape(json.dumps(item['proposed_inventory']['defects'],indent=2))+'</pre><h3>Fixed rule draft — confirm or edit each question</h3>')
   for q in item['comparison']['inventory_template']['fixed_template_questions']:content.append('<article><b>'+html.escape(q['dimension'])+'</b><p>'+html.escape(q['prompt'])+'</p><p>Expected: '+html.escape(q['expected_behavior'])+'</p><small>'+html.escape(', '.join(q['source_message_ids']))+'</small></article>')
  (folder/'review.html').write_text(''.join(content));print(folder/'review.html');return
 assert b['status']=='complete_automatic_collection','Finish actual answer collection before freezing packets'
 folder=D/'blind-review';folder.mkdir(exist_ok=True);private=D/'private';private.mkdir(exist_ok=True);key={};cases=[];questions=[];extractions=[]
 for h in b['scenarios']:
  source=sources[h['scenario_id']]['messages']
  for j,t in enumerate(h['runs'][0]['tests']):
   questions.append({'item_id':h['scenario_id']+'-Q'+str(j+1),'source_messages':source,'question':t['prompt'],'expected_behavior':t['expected_behavior'],'dimension':t['dimension'],'supporting_memory_ids':t['supporting_memory_ids'],'memories':[m for m in h['memories'] if m['status'] in ['confirmed','edited']]})
  extractions.append({'item_id':h['scenario_id']+'-EXTRACTION','source_messages':source,'candidates':h['extracted_candidates']})
  for r in h['runs']:
   ts={t['test_id']:t for t in r['tests']};es={e['response_id']:e for e in r['evaluations']}
   for answer in r['responses']:
    ident='BL-'+digest(answer['response_id'])[:14];t=ts[answer['test_id']]
    cases.append({'item_id':ident,'source_messages':source,'question':t['prompt'],'response':answer['response_text'],'question_dimension':t['dimension']})
    key[ident]={'scenario_id':h['scenario_id'],'run_id':r['run_id'],'response_id':answer['response_id'],'strategy':r['strategy'],'repetition':r['repetition'],'automated':es[answer['response_id']],'answer_sha256':hashlib.sha256(answer['response_text'].encode()).hexdigest()}
 assert len(cases)==72 and len(key)==72
 manifest={'schema_version':'phase4-blind-v1','response_items':sorted(key),'question_items':[q['item_id'] for q in questions],'extraction_items':[x['item_id'] for x in extractions],'question_source':questions,'extraction_source':extractions,'human_results_received':False}
 (private/'identity-key.json').write_text(json.dumps(key,indent=2));(private/'review-manifest.json').write_text(json.dumps(manifest,indent=2))
 for index in [1,2]:
  packet=folder/f'reviewer-{index}';packet.mkdir(exist_ok=True);items=list(cases);random.Random(917+index).shuffle(items)
  data={'instructions':['Work independently without consulting the other reviewer or automated results.','For each response decide pass/fail/uncertain from the source and question. Cite source message IDs. If fail, choose observed failure dimension, not merely the question dimension.','Review every question for grounding, clarity and answer leakage.','For extraction, label every candidate include/exclude/uncertain; write every missing fact with exact supporting source IDs. Review each proposed relationship and add missing relationships.','Use your own pseudonym and confirm actual independent review only when completed. Leave unknown values null.'], 'responses':items,'question_validity':questions,'extraction_and_relationships':extractions}
  (packet/'materials.json').write_text(json.dumps(data,indent=2))
  material_hash=digest(data);manifest.setdefault('material_sha256',[]).append(material_hash)
  labels={'material_sha256':material_hash,'schema_version':'phase4-blind-labels-v1','reviewer_id':None,'independently_completed':False,'response_labels':[{'item_id':x['item_id'],'verdict':None,'failure_dimension':None,'source_message_ids':[],'note':''} for x in items],'question_labels':[{'item_id':q['item_id'],'valid':None,'note':''} for q in questions],'extraction_labels':[{'item_id':e['item_id'],'candidate_labels':[{'memory_id':m['memory_id'],'include':None,'source_message_ids':[],'note':''} for m in e['candidates']],'missing_facts':[],'relationship_labels':None,'missing_relationships':[],'complete':False} for e in extractions]}
  (packet/'labels-to-complete.json').write_text(json.dumps(labels,indent=2))
  with zipfile.ZipFile(folder/f'reviewer-{index}.zip','w',zipfile.ZIP_DEFLATED) as z:
   for f in packet.iterdir():z.write(f,f.name)
 (private/'review-manifest.json').write_text(json.dumps(manifest,indent=2))
 (folder/'packet-manifest.json').write_text(json.dumps({'scope':'72 actual B answers,12 question-validity items,3 extraction/relationship histories','labels_pending':True,'private_identity_key_included':False,'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.glob('*.zip')}},indent=2));print(folder)
if __name__=='__main__':main()
