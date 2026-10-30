"""Import one explicitly confirmed human reference per candidate answer.

Two independent AI judgments stay as separate artifacts, never as human rows.
"""
import json,hashlib,os
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/experiment-a-expanded-20261030'
packet_path=D/'检索复测-48组前后答案-待确认.json';confirm_path=D/'检索复测-人工确认.json';state_path=D/'retrieval-retest-human-import.json'
packet=json.loads(packet_path.read_text());confirm=json.loads(confirm_path.read_text());sha=hashlib.sha256(packet_path.read_bytes()).hexdigest()
if not confirm.get('human_confirmed') or confirm.get('review_packet_sha256')!=sha:raise SystemExit('Explicit human confirmation for this exact packet required')
key=json.loads((D/'retrieval-retest-blind-key-private.json').read_text());state=json.loads(state_path.read_text()) if state_path.exists() else {'packet_sha256':sha,'operations':{}}
if state['packet_sha256']!=sha:raise SystemExit('Packet changed')
def save():
 p=state_path.with_suffix('.tmp');p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(p,state_path)
def request(method,path,body=None):
 req=Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urlopen(req,timeout=120) as r:return json.load(r)
byrun={}
for row in packet['items']:
 if row['after_ai_consensus'] not in ('pass','fail'):raise SystemExit('Uncertain must remain unresolved')
 byrun.setdefault(key[row['case_id']]['candidate_run_id'],[]).append(row)
if len(byrun)!=12 or sum(map(len,byrun.values()))!=48:raise SystemExit('Incomplete review packet')
for rid,rows in byrun.items():
 blind=request('GET',f'/audits/{rid}/blind-review');tests={i['test']['test_id']:i for i in blind}
 if len(rows)!=4 or len(tests)!=4:raise SystemExit('Mismatch in candidate answers')
 for item in rows:
  identity=key[item['case_id']];saved=tests[identity['test_id']]
  if saved['test']['prompt']!=item['question'] or saved['response']['response_text']!=item['after_answer']:raise SystemExit('Question/answer changed')
  eid=saved['automated']['evaluation_id'];op='reference-'+eid
  body={'review_role':'reference','reviewer_label':'user-confirmed','human_passed':item['after_ai_consensus']=='pass','human_failure_type':None,'note':'User confirmed this answer following two independent AI blind reviews. This is one human reference, not two independent human reviews.'}
  if op in state['operations']:
   if state['operations'][op]['status']!='returned':raise SystemExit('Prior dispatch requires reconciliation')
   continue
  state['operations'][op]={'status':'dispatched'};save();result=request('PATCH',f'/audits/{rid}/evaluations/{eid}/review',body);state['operations'][op]={'status':'returned','response':result};save()
 print('Saved human references for',rid,flush=True)
print('Saved 48 single-human references; independent AI review artifacts remain separate.')
