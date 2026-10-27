"""Prepare unfilled human worksheets for the complete A/B reference review."""
import hashlib,json,random,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'artifacts/local/phase4-20261027';OUT=ROOT/'artifacts/local/phase4-formal-review-20261027';priv=OUT/'private';priv.mkdir(exist_ok=True)
def ident(prefix,value):return prefix+hashlib.sha256(value.encode()).hexdigest()[:16]
def load(path):return json.loads(path.read_text())
a=load(OLD/'A-live.json');b=load(OLD/'B-live.json');sources=load(ROOT/'datasets/phase4-candidate-v1/source-histories.json');histories={h['scenario_id']:h['messages'] for h in sources}
items={};keys={};question_conditions={}
assessments={}
for p in [ROOT/'artifacts/local/phase4-followup-20261027/saved-answer-reassessment.json',OUT/'B-current-assessor/saved-answer-reassessment.json']:
 data=load(p);assert data['status']=='complete'
 for run in data['runs']:
  for answer in run['result']['answers']:
   response=answer['response'];oid=response['execution_metadata']['shared_source_response_id']
   assessments[oid]={'automated':answer['evaluation'],'current_run_id':run['run_id'],'current_response_id':response['response_id'],'current_test_id':answer['test']['test_id'],'current_evaluation_id':answer['evaluation']['evaluation_id']}
for study,data in [('A',a),('B',b)]:
 for h in data['scenarios']:
  for run in h['runs']:
   suffix=run['label'] if study=='A' else str(run['repetition'])+':'+run['strategy'];condition=study+':'+h['scenario_id']+':'+suffix;tests={t['test_id']:t for t in run['tests']};evals={e['response_id']:e for e in run['evaluations']}
   for response in run['responses']:
    t=tests[response['test_id']];rid=ident('R-',response['response_id']);qid=ident('Q-',t['test_id'] if study=='A' else h['scenario_id']+t['dimension']+t['prompt'])
    items.setdefault(qid,{'kind':'question','history':h['scenario_id'],'question':t['prompt'],'proposed_reference':t['expected_behavior']});keys.setdefault(qid,{'dimension':t['dimension']});question_conditions.setdefault(qid,[]).append(condition)
    items[rid]={'kind':'response','study':study,'history':h['scenario_id'],'question':t['prompt'],'answer':response['response_text'],'question_id':qid,'defects':h['submitted_inventory']['defects'] if study=='A' else []}
    known=[x['defect_id'] for x in h['submitted_inventory']['defects']] if study=='A' else []
    keys[rid]={**assessments[response['response_id']],'condition':condition,'source_run_id':run['run_id'],'source_response_id':response['response_id'],'source_test_id':t['test_id'],'source_evaluation_id':evals[response['response_id']]['evaluation_id'],'known_defect_ids':known,'comparison_id':h.get('comparison_id'),'inventory_fingerprint_sha256':h.get('frozen_inventory',{}).get('inventory_fingerprint_sha256'),'answer_sha256':hashlib.sha256(response['response_text'].encode()).hexdigest()}
for h in b['scenarios']:
 history=h['scenario_id'];candidates=h['extracted_candidates'];cids=[]
 for m in candidates:
  cid=ident('C-',m['memory_id']);cids.append(cid);items[cid]={'kind':'candidate','history':history,'text':m['canonical_value'],'proposed_source_ids':m['source_message_ids']};keys[cid]={'source_memory_id':m['memory_id']}
 for memory in h['memories']:
  if memory['status'] not in ['confirmed','edited']:continue
  gid=ident('G-',memory['memory_id']);items[gid]={'kind':'reference','history':history,'text':memory['canonical_value'],'source_ids':memory['source_message_ids'],'candidate_ids':list(cids)};keys[gid]={'source_memory_id':memory['memory_id']}
 # Three declared source-backed pairs; evaluate missed edges as NONE.
 for si,ti,needle in [(3,2,'migrated'),(5,4,'requires'),(7,6,'South')]:
  lookup=lambda i,text:next(m for m in candidates if any(s.endswith('S'+str(i)) for s in m['source_message_ids']) and text.lower() in m['canonical_value'].lower())
  src=lookup(si,needle);target=lookup(ti,'');edge=next((e for e in src.get('relationships',[]) if e['target_memory_id']==target['memory_id']),None);eid=ident('E-',src['memory_id']+target['memory_id']);items[eid]={'kind':'relationship','history':history,'from_text':src['canonical_value'],'to_text':target['canonical_value']};keys[eid]={'predicted_type':edge['type'] if edge else 'NONE'}
material={'schema_version':'phase4-complete-material-v1','histories':histories,'items':items,'reference_unit_definition':'The24 proposed confirmed memory records are source-bound units. Review each unit for validity and full coverage by valid extracted candidates. Partial coverage is not full recall. Add any missing source fact separately for adjudication.','relationship_unit_definition':'Nine declared source-backed candidate pairs, including a potentially missing edge; this is not all-pairs relationship accuracy.','critical_error_definition':'Explicit wrong owner; asserting/recommending superseded current state; or committing to one unresolved conflicting instruction. Mere cautious abstention is not automatically critical.'}
counts={kind:sum(x['kind']==kind for x in items.values()) for kind in ['response','question','candidate','reference','relationship']};assert counts=={'response':108,'question':48,'candidate':27,'reference':24,'relationship':9},counts
key={'items':keys,'question_conditions':{q:sorted(set(c)) for q,c in question_conditions.items()},'material_sha256':[],'known_result_exposed_reviewer_ids':['yichao wang'],'known_exposure_basis':'This chat has shown Yichao Wang automatic and AI case results. Reference review remains possible; fresh blind authorship cannot be declared for these same cases.'}
js=(ROOT/'scripts/phase4_review_form.js').read_text()
for n in [1,2]:
 folder=OUT/f'reviewer-{n}';folder.mkdir(exist_ok=True);pairs=list(items.items());random.Random(4200+n).shuffle(pairs);copy={**material,'items':dict(pairs)};encoded=json.dumps(copy,ensure_ascii=False);mh=hashlib.sha256(encoded.encode()).hexdigest();key['material_sha256'].append(mh)
 blank={'schema_version':'phase4-complete-review-v1','material_sha256':mh,'reviewer_id':'','completed_by_human':False,'completed_independently':False,'used_ai_assistance':None,'has_seen_automated_results':None,'additional_missing_facts':{h:'' for h in histories},'labels':{}}
 for i,item in items.items():
  kind=item['kind'];row={'note':''}
  if kind=='response':row.update(verdict=None,failure_dimension=None,critical_error=None,source_message_ids=[]);row.update({'defect_ids':None} if item['study']=='A' else {})
  elif kind in ['question','candidate']:row.update(valid=None)
  elif kind=='reference':row.update(valid=None,coverage=None,candidate_ids=[])
  else:row.update(relationship_type=None)
  blank['labels'][i]=row
 (folder/'material.json').write_text(encoded);(folder/'blank-result.json').write_text(json.dumps(blank,indent=2));payload=json.dumps({'material':copy,'blank':blank},ensure_ascii=False).replace('<','\\u003c')
 html='<!doctype html><html lang="zh"><meta charset="utf-8"><title>独立审核表</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;line-height:1.5}article{border:1px solid #ccc;padding:16px;margin:18px 0}label{display:block;margin:8px 0}input[type=text],textarea{width:95%}select,button{padding:7px}pre{white-space:pre-wrap}.sticky{position:sticky;top:0;background:#fff;padding:12px;border:1px solid #aaa}small{color:#555}</style><h1>Phase4：独立人工审核表</h1><p>本表未填写任何人工结论，也不显示策略名称和自动评分。请由真实评审者独立填写。若已看过自动评分或参考AI复核，请如实声明；该结果可作参考审核，但不能作为盲审证据。</p><p>108条实际回答、48项题目有效性、27项候选记忆、24项参考记忆覆盖、9个关系对。每条来源可展开查看。对原缺陷清单，遗漏信息不等于选错信息；不要仅按维度选择缺陷。若题目有歧义可选“不确定”，系统会保留待裁决。</p><div class="sticky"><button id="save">保存本地草稿</button> <button id="export">下载审核结果 JSON</button> <span id="status"></span></div><section id="identity"></section><section id="forms"></section><script id="payload" type="application/json">'+payload+'</script><script>'+js+'</script></html>'
 (folder/'review.html').write_text(html)
 with zipfile.ZipFile(OUT/f'reviewer-{n}.zip','w',zipfile.ZIP_DEFLATED) as z:
  for f in folder.iterdir():z.write(f,f.name)
(priv/'material.json').write_text(json.dumps(material,ensure_ascii=False,indent=2));(priv/'key.json').write_text(json.dumps(key,indent=2));(OUT/'packet-manifest.json').write_text(json.dumps({'counts':counts,'human_returns_received':0,'labels_filled':0,'packets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('reviewer-*.zip')}},indent=2));print(counts)
