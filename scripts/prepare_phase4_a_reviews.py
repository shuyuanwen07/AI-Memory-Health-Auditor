"""Freeze separate A response-review packets; do not reveal automated verdicts."""
import hashlib,html,json,random,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-20261027';s=json.loads((D/'A-live.json').read_text());assert s['status']=='complete_target_collection_independent_response_review_pending'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
items=[];private={}
for h in s['scenarios']:
 source=json.loads((D/'researcher-preexecution'/(h['scenario_id']+'.json')).read_text())
 for run in h['runs']:
  tests={t['test_id']:t for t in run['tests']};evals={e['response_id']:e for e in run['evaluations']}
  for response in run['responses']:
   ident='A-'+hashlib.sha256(response['response_id'].encode()).hexdigest()[:14];t=tests[response['test_id']]
   items.append({'item_id':ident,'source_messages':source['source_messages'],'question':t['prompt'],'response':response['response_text'],'frozen_defects':source['proposed_inventory']['defects']})
   private[ident]={'scenario_id':h['scenario_id'],'comparison_id':h['comparison_id'],'run_id':run['run_id'],'condition_label':run['label'],'response_id':response['response_id'],'test_id':response['test_id'],'evaluation':evals[response['response_id']],'inventory_fingerprint_sha256':h['frozen_inventory']['inventory_fingerprint_sha256'],'answer_sha256':hashlib.sha256(response['response_text'].encode()).hexdigest()}
assert len(items)==36 and len(private)==36
folder=D/'A-blind-review';folder.mkdir(exist_ok=True);material_hashes=[]
for i in [1,2]:
 out=folder/f'reviewer-{i}';out.mkdir(exist_ok=True);ordered=list(items);random.Random(8271+i).shuffle(ordered)
 material={'schema_version':'phase4-A-review-material-v1','instructions':['Review independently before viewing automated A assessments; do not consult the other reviewer.','Judge each actual response from the original source and question: pass/fail/uncertain. Cite source message IDs.','For a failed answer identify the observed failure dimension. Do not infer failure from the question category.','Map a failed response to any actually demonstrated frozen defect IDs; record an empty list if none apply. No matching dimension alone establishes a mapping.','Disclose whether you have already seen automated A results. Identities and independence are declarations, not authenticated signatures.'],'items':ordered};mh=digest(material);material_hashes.append(mh)
 (out/'materials.json').write_text(json.dumps(material,ensure_ascii=False,indent=2))
 labels={'schema_version':'phase4-A-response-labels-v1','material_sha256':mh,'reviewer_id':None,'independently_completed':False,'has_seen_automated_A_results':None,'labels':[{'item_id':x['item_id'],'verdict':None,'failure_dimension':None,'source_message_ids':[],'defect_ids':None,'note':''} for x in ordered]}
 (out/'labels-to-complete.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2))
 parts=['<!doctype html><meta charset="utf-8"><title>Experiment A independent answer review</title><style>body{font:17px system-ui;max-width:1000px;margin:40px auto;line-height:1.55}article{padding:20px;border:1px solid #bbb;margin:24px 0}pre{white-space:pre-wrap}</style><h1>Experiment A: independent actual-answer review</h1><p>Read every item independently; complete labels-to-complete.json. Automated verdicts and method labels are omitted. Do not inspect the private identity key or automated report before reviewing.</p>']
 for x in ordered:
  parts.append('<article><h2>'+x['item_id']+'</h2><details><summary>Original source messages</summary>'+''.join('<p>'+html.escape(m['message_id']+': '+m['content'])+'</p>' for m in x['source_messages'])+'</details><h3>Question</h3><p>'+html.escape(x['question'])+'</p><h3>Actual response</h3><pre>'+html.escape(x['response'])+'</pre><details><summary>Frozen potential defects for mapping</summary>'+''.join('<p>'+html.escape(d['defect_id']+': '+d['explanation'])+'</p>' for d in x['frozen_defects'])+'</details></article>')
 (out/'review.html').write_text(''.join(parts))
 with zipfile.ZipFile(folder/f'reviewer-{i}.zip','w',zipfile.ZIP_DEFLATED) as z:
  for f in out.iterdir():z.write(f,f.name)
private_dir=D/'private';private_dir.mkdir(exist_ok=True);(private_dir/'A-identity-key.json').write_text(json.dumps(private,indent=2));(private_dir/'A-review-manifest.json').write_text(json.dumps({'item_ids':sorted(private),'material_sha256':material_hashes,'items':items,'labels_received':False},indent=2))
(folder/'packet-manifest.json').write_text(json.dumps({'count':36,'two_independent_returns_pending':True,'private_key_in_zip':False,'packets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.zip')}},indent=2));print('Two independent A review packets prepared;36 actual answers each; no labels fabricated.')
