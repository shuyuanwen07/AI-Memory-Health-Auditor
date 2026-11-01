"""Retest generation on the same saved confirmed-memory conversation."""
import concurrent.futures,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'output/proposal-delivery/ac2-workout-revised-product-20261101-v1'
OUT=ROOT/'output/proposal-delivery/ac2-workout-intent-timeout-retest-20261101-v1'
API='http://127.0.0.1:8000/api/v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.now(timezone.utc).isoformat()
def save(p,v,exclusive=False):
    text=json.dumps(v,ensure_ascii=False,indent=2)+'\n'
    if exclusive:
        with p.open('x',encoding='utf8') as f:f.write(text)
    else:
        tmp=p.with_suffix('.tmp');tmp.write_text(text);tmp.replace(p)
def hashes():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
old=json.loads((OLD/'summary.json').read_text()); runs=old['runs']
if len(runs)!=1 or any(x['status']!='generation_failed' for x in runs):raise SystemExit('Unexpected baseline state')
OUT.mkdir(parents=True,exist_ok=False)
protocol={'format':'ac2-generation-repair-retest-v1','frozen_utc':now(),'old_summary_sha256':sha(OLD/'summary.json'),
 'old_runs':runs,'application_sha256':hashes(),'runner_sha256':sha(Path(__file__)),'design':'Post-discovery development retest. Reuse the exact same saved conversation and confirmed memory state for each previously failed audit. New audit uses same target, model, budget and coverage settings. No extraction is rerun. Generate once; preserve failures. User confirmation remains simulated.',
 'limitations':['Previously observed synthetic data; not held out.','Provider sampling remains uncontrolled.','No automatic retry after a failed or ambiguous request.','Generated questions require source-based review; passing the automatic gate is not human validity.']}
save(OUT/'protocol.json',protocol,True)
def run(row):
    hid=row['history_id'];path=OUT/(hid+'.json');data={'history_id':hid,'status':'started','requests':[]};save(path,data,True)
    oldrun=json.loads((OLD/(hid+'.json')).read_text())
    oldaudit=next(x['request'] for x in oldrun['requests'] if x['path']=='/audits' and x['status']=='returned')
    def call(method,route,body=None):
        if hashes()!=protocol['application_sha256']:raise RuntimeError('Application changed after freeze')
        req={'method':method,'path':route,'request':body,'status':'dispatched','time':now()};data['requests'].append(req);save(path,data)
        try:
            with urlopen(Request(API+route,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=1200) as response:req.update(status='returned',http_status=response.status,response=json.load(response))
        except HTTPError as e:req.update(status='http_error',http_status=e.code,response=e.read().decode(errors='replace')[:2000])
        except Exception as e:req.update(status='ambiguous',error_type=type(e).__name__)
        save(path,data);return req
    try:
        original=next(x['response'] for x in oldrun['requests'] if x['path'].endswith('/extract') and x['status']=='returned')
        live=call('GET',f"/conversations/{row['conversation_id']}/memories")
        if live['status']!='returned':raise RuntimeError('Could not verify saved memories')
        signature=lambda m:(m['memory_id'],m['canonical_value'],tuple(m['source_message_ids']),json.dumps(m['relationships'],sort_keys=True))
        if sorted(map(signature,original))!=sorted(map(signature,live['response'])) or any(m['status'] not in ('confirmed','edited') for m in live['response']):raise RuntimeError('Saved memories differ from baseline')
        audit=call('POST','/audits',oldaudit)
        if audit['status']!='returned':raise RuntimeError('Audit creation failed or ambiguous')
        rid=audit['response']['run_id'];data['run_id']=rid;save(path,data)
        generated=call('POST',f'/audits/{rid}/generate-tests')
        call('GET',f'/audits/{rid}/agent-executions')
        call('GET',f'/audits/{rid}')
        if generated['status']=='returned':
            data['generated_count']=len(generated['response']);call('GET',f'/audits/{rid}/test-review')
            data['status']='completed_human_review_pending'
        else:data['status']='generation_failed_or_ambiguous'
    except Exception as e:data.update(status='stopped',error_type=type(e).__name__,error=str(e)[:300])
    save(path,data);print(hid,data['status'],data.get('generated_count',0),flush=True);return {'history_id':hid,'status':data['status'],'generated_count':data.get('generated_count',0),'sha256':sha(path)}
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:results=list(pool.map(run,runs))
save(OUT/'summary.json',{'runs':results,'planned_questions':4,'generated_questions':sum(x['generated_count'] for x in results),'scope':protocol['limitations']},True)
print(json.dumps(results),flush=True)
