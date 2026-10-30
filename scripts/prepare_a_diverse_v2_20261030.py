"""New consistent-version A campaign; retain prior source runs and failures.

Reuses the four already imported source conversations, not their old target
answers. Makes at most 16 new source-audit target calls. Does not freeze A
inventories or submit human review decisions. Every request is checkpointed;
an uncertain dispatch stops without retry.
"""
import json,hashlib,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/experiment-a-expanded-20261030'
input_path=OUT/'four-scenario-frozen-input.json'; state_path=OUT/'four-scenario-v2-source-ledger.json'
data=json.loads(input_path.read_text());histories=data['histories'];sha=hashlib.sha256(input_path.read_bytes()).hexdigest()
prior={}
for name in ('four-scenario-preparation-ledger.json','garden-shop-preparation-ledger.json','shop-preparation-ledger.json'):
 p=OUT/name
 if p.exists():prior.update(json.loads(p.read_text())['histories'])
state=json.loads(state_path.read_text()) if state_path.exists() else {'source_sha256':sha,'campaign_id':'diverse-a-20261030-v2','histories':{}}
if state['source_sha256']!=sha:raise SystemExit('Frozen source changed')
def save():
 tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,state_path)
def call(row,key,method,path,body=None):
 op={'method':method,'path':path,'body':body};h=hashlib.sha256(json.dumps(op,sort_keys=True,ensure_ascii=False).encode()).hexdigest();prev=row['operations'].get(key)
 if prev:
  if prev['sha256']!=h or prev['status']!='returned':raise RuntimeError(f'{key}: inspect prior attempt before retry')
  return prev['response']
 row['operations'][key]={**op,'sha256':h,'status':'dispatched'};save()
 req=Request('http://127.0.0.1:8000/api/v1'+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urlopen(req,timeout=900) as response:value=json.load(response)
 except HTTPError as e:row['operations'][key].update(status='http_error',code=e.code,error=e.read().decode());save();raise
 except Exception:row['operations'][key]['status']='ambiguous';save();raise
 row['operations'][key].update(status='returned',response=value);save();print(row['history_id'],key,flush=True);return value
for history in histories:
 hid=history['history_id'];p=prior[hid];ops=p['operations'];cid=ops['conversation']['response']['conversation_id']
 mids=[ops[f'memory-{i}']['response']['memory_id'] for i in range(1,8)]
 row=state['histories'].setdefault(hid,{'history_id':hid,'conversation_id':cid,'memory_ids':mids,'operations':{}});save()
 try:
  body=ops['source-audit']['body'];audit=call(row,'source-audit','POST','/audits',body);rid=audit['run_id']
  tests=call(row,'source-generate','POST',f'/audits/{rid}/generate-tests')
  if len(tests)!=4 or any(t['quality_status']!='accepted' for t in tests):raise RuntimeError('source suite incomplete or quality review pending')
  call(row,'source-execute','POST',f'/audits/{rid}/execute',{})
  call(row,'source-evaluate','POST',f'/audits/{rid}/evaluate',{})
  detail=call(row,'source-completed','GET',f'/audits/{rid}')
  if detail['status']!='COMPLETED':raise RuntimeError('source run not completed')
  result=call(row,'campaign-register','POST',f'/audits/{rid}/method-comparison',{'campaign_id':state['campaign_id'],'scenario_id':hid,'planned_scenarios':4})
  row.update(source_run_id=rid,comparison_id=result['comparison_id'],status='prepared_inventory_not_frozen');save()
 except Exception as exc:
  row.update(status='stopped',error=str(exc));save();raise SystemExit(f'{hid} stopped: {exc}') from exc
print('Four new source audits complete; no A comparison questions or human verdicts were recorded.')
