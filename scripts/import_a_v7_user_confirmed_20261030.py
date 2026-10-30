"""Import a single user-confirmed reference and mapping, never AI as human reviewers."""
import json,hashlib,os
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/experiment-a-expanded-20261030'
packet_path=D/'v7-48条回答-待人工确认.json';confirm_path=D/'v7-answer-user-confirmation.json';state_path=D/'v7-user-reference-import.json'
packet=json.loads(packet_path.read_text());confirmation=json.loads(confirm_path.read_text());sha=hashlib.sha256(packet_path.read_bytes()).hexdigest()
if not confirmation.get('human_confirmed') or confirmation.get('review_packet_sha256')!=sha:raise SystemExit('Explicit user confirmation for this exact packet required')
key=json.loads((D/'v7-blind-answer-key-private.json').read_text());questions=json.loads((D/'four-scenario-v7-question-ledger.json').read_text());state=json.loads(state_path.read_text()) if state_path.exists() else {'packet_sha256':sha,'operations':{}}
if state['packet_sha256']!=sha:raise SystemExit('Packet changed')
def save():
 p=state_path.with_suffix('.tmp');p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(p,state_path)
def request(method,path,body=None):
 req=Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urlopen(req,timeout=120) as r:return json.load(r)
by_run={}
for row in packet['items']:
 if row['ai_consensus'] not in ('pass','fail'):raise SystemExit('Uncertain verdict must be resolved separately')
 by_run.setdefault(key[row['case_id']]['run_id'],[]).append(row)
for hid,h in questions['histories'].items():
 inv=h['operations']['inventory']['response'];comp=h['operations']['inventory']['body']['comparison_id']
 for suite in h['suites']:
  rid=suite['run_id'];rows=by_run[rid];blind=request('GET',f'/audits/{rid}/blind-review');by_test={i['test']['test_id']:i for i in blind}
  if len(rows)!=4 or len(by_test)!=4:raise SystemExit('Response count mismatch')
  entries=[]
  for item in rows:
   ref=key[item['case_id']];saved=by_test[ref['test_id']]
   if saved['test']['prompt']!=item['question'] or saved['response']['response_text']!=item['answer']:raise SystemExit('Saved question or answer differs')
   eid=saved['automated']['evaluation_id'];op='review-'+eid
   body={'review_role':'reference','reviewer_label':'user-confirmed','human_passed':item['ai_consensus']=='pass','human_failure_type':None,'note':'One user confirmed this AI-assisted decision; two AI agents reviewed independently, not two human reviewers.'}
   if op not in state['operations']:
    state['operations'][op]={'status':'dispatched'};save();result=request('PATCH',f'/audits/{rid}/evaluations/{eid}/review',body);state['operations'][op]={'status':'returned','response':result};save()
   elif state['operations'][op]['status']!='returned':raise SystemExit(f'{op}: reconcile uncertain prior dispatch')
   entries.append({'response_id':ref['response_id'],'test_id':ref['test_id'],'defect_ids':item['candidate_defect_ids']})
  op='mapping-'+rid
  if op not in state['operations']:
   body={'schema_version':'mha-experiment-a-discovery-map-v1','comparison_id':comp,'inventory_fingerprint_sha256':inv['inventory_fingerprint_sha256'],'mapping_release_id':'v7-user-confirmed','reviewer_pseudonym':'user-confirmed','completed_by_human':True,'entries':entries}
   state['operations'][op]={'status':'dispatched'};save();result=request('POST',f'/audits/{rid}/method-comparison-discovery-mapping',body);state['operations'][op]={'status':'returned','response':result};save()
  elif state['operations'][op]['status']!='returned':raise SystemExit(f'{op}: reconcile uncertain prior dispatch')
  print(hid,suite['method'],'single reference and mapping saved',flush=True)
print('Done: one human reference per answer; not two-person human consensus.')
