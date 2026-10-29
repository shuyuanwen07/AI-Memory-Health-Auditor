"""Copy-based c11 product diagnostic; same sample, no independent validity claim."""
import argparse,hashlib,json,pathlib,urllib.request,urllib.error
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
OLD=ROOT/'output/proposal-delivery/ac2-v40-same-source-development-20261029-v1/ledger.json'
OUT=ROOT/'output/proposal-delivery/ac2-scope-v5-c11-development-20261029-v1'
SCRIPT=pathlib.Path(__file__).resolve();URL='http://127.0.0.1:8000/api/v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hashes():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def write(p,data,mode='w'):
 with p.open(mode,encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
def freeze():
 old=json.loads(OLD.read_bytes()); c=next(x for x in old['histories'] if x['history_id']=='prospective-11')
 if c['status']!='completed':raise ValueError('Original c11 did not complete')
 OUT.mkdir(parents=True,exist_ok=False)
 write(OUT/'protocol.json',{'format':'ac2-scope-v5-c11-copy-freeze-v1','time_utc':datetime.now(timezone.utc).isoformat(),
 'source_ledger_sha256':sha(OLD),'source_run_id':c['run_id'],'conversation_id':c['product_conversation_id'],
 'application_sha256':hashes(),'script_sha256':sha(SCRIPT),'v4_snapshot_sha256':sha(ROOT/'backend/app/test_generator/frozen_scope_review_v4.py'),
 'design':'Create one new rule-based audit from original confirmed conversation; generate once, require exact match to both original questions by wording, reference, dimension, type and memory IDs; then run v5 scope review on the copy only. Preserve old run; no paid model or target execution.',
 'interpretation':'Single previously examined synthetic history with simulated confirmation; post-outcome development diagnostic, not human validation, independent held-out evidence, or population result.'},'x');print('Frozen; no product operation yet.')
def run():
 p=json.loads((OUT/'protocol.json').read_bytes());old=json.loads(OLD.read_bytes());entry=next(x for x in old['histories'] if x['history_id']=='prospective-11')
 def frozen():
  if sha(OLD)!=p['source_ledger_sha256'] or sha(SCRIPT)!=p['script_sha256'] or hashes()!=p['application_sha256']:raise RuntimeError('Frozen source changed; stop')
 frozen(); ledger={'format':'ac2-scope-v5-c11-copy-ledger-v1','protocol_sha256':sha(OUT/'protocol.json'),'calls':[]};write(OUT/'ledger.json',ledger,'x')
 def request(method,path,data=None):
  frozen();row={'method':method,'path':path,'request':data,'status':'dispatched'};ledger['calls'].append(row);write(OUT/'ledger.json',ledger)
  q=urllib.request.Request(URL+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(q,timeout=120) as r:row.update(status='returned',http_status=r.status,response=json.loads(r.read()))
  except urllib.error.HTTPError as e:row.update(status='failed',http_status=e.code,error=e.read().decode(errors='replace'))
  write(OUT/'ledger.json',ledger);frozen()
  if row['status']!='returned':raise RuntimeError('API request failed; no retries')
  return row['response']
 def key(t):return (t['dimension'],t['test_type'],t['prompt'],t['expected_behavior'],tuple(sorted(t['supporting_memory_ids'])))
 original_before=request('GET',f"/audits/{entry['run_id']}/test-review")
 if {key(x) for x in original_before['tests']}!={key(x) for x in entry['scope_review']['tests']}:raise ValueError('Original suite changed; stop')
 request_body=next(x['request'] for x in entry['requests'] if x['method']=='POST' and x['path']=='/audits')
 created=request('POST','/audits',request_body);rid=created['run_id'];ledger['copy_run_id']=rid
 if created.get('reproducibility',{}).get('audit_runtime_signature',{}).get('generator')!='rule-based-v40':raise RuntimeError('Unexpected generator')
 generated=request('POST',f'/audits/{rid}/generate-tests');before=request('GET',f'/audits/{rid}/test-review')
 old_by={key(x):x for x in original_before['tests']};new_by={key(x):x for x in before['tests']}
 if len(old_by)!=len(new_by) or set(old_by)!=set(new_by) or len(generated)!=len(new_by):raise ValueError('Copy is not exactly comparable; no scope review run')
 after=request('POST',f'/audits/{rid}/tests/scope-review');after_by={key(x):x for x in after['tests']}
 if set(after_by)!=set(old_by):raise ValueError('Question content changed')
 old_after=request('GET',f"/audits/{entry['run_id']}/test-review")
 if old_after!=original_before:raise ValueError('Original audit was modified')
 pairs=[{'question':k[2],'v4_status':old_by[k]['quality_status'],'v5_status':after_by[k]['quality_status'],'v5_note':after_by[k]['validation_notes']} for k in sorted(old_by)]
 if any(x['v5_status']=='pending' and not x['v5_note'].startswith('source-scope-review-v5:') for x in pairs):raise ValueError('Unexpected scope version')
 ledger['status']='completed';ledger['pairs']=pairs;write(OUT/'ledger.json',ledger)
 write(OUT/'summary.json',{'format':'ac2-scope-v5-c11-copy-summary-v1','protocol_sha256':sha(OUT/'protocol.json'),'ledger_sha256':sha(OUT/'ledger.json'),'pair_count':len(pairs),'pairs':pairs,'original_unchanged':True,'paid_model_calls':0,'limitations':['One previously observed synthetic history; simulated confirmations are not human gold.','Pending is advisory, not a validity judgment; this is not independent validation.']},'x')
 print(json.dumps(pairs,ensure_ascii=False))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);globals()[parser.parse_args().stage]()
