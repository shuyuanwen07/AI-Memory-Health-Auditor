"""Execute at most six separate engineering probes; preserve every old answer."""
import json,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'artifacts/local/phase4-followup-20261027';source=ROOT/'backend/.engineering-smoke/phase4-followup/clarification.json';p=D/'clarification-live.json'
s=json.loads((p if p.exists() else source).read_text());s.setdefault('http_events',[])
def save():p.write_text(json.dumps(s,indent=2))
def api(method,path):
 req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,data=b'{}' if method=='POST' else None,headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=300) as r:result=json.load(r)
 except urllib.error.HTTPError as e:s['http_events'].append({'path':path,'status':e.code,'error':e.read().decode()});save();raise
 s['http_events'].append({'method':method,'path':path,'response':result});save();return result
assert len(s['runs'])==6
for run in s['runs']:
 path='/audits/'+run['run_id']
 if 'responses' not in run:run['responses']=api('POST',path+'/execute');save()
 if 'evaluations' not in run:run['evaluations']=api('POST',path+'/evaluate');save()
 run['result']=api('GET',path+'/results');run['trace']=api('GET',path+'/target-memory-trace');save()
 assert len(run['responses'])==1
 print('Completed new development probe',run['history'],run['method'],flush=True)
s['status']='complete_development_probes_not_formal_A';s['estimated_completed_target_usage_usd']=sum((r['execution_metadata'].get('input_tokens') or 0)*1e-7+(r['execution_metadata'].get('output_tokens') or 0)*5e-7 for run in s['runs'] for r in run['responses']);assert s['estimated_completed_target_usage_usd']<0.1;s['original_A_unchanged']=True;save()
