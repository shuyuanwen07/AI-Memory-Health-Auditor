"""Source-frozen synthetic product smoke. Simulated review, not a validity study."""
import argparse, hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/current-source-timestamp-smoke-20261029-v1'
SCRIPT=Path(__file__).resolve(); API='http://127.0.0.1:8000/api/v1'
MODEL='openai/gpt-6-luna'; TEXT='I prefer jasmine tea.'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def app_hashes():return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def freeze():
    OUT.mkdir(parents=True,exist_ok=False)
    protocol={'created_at_utc':now(),'script_sha256':sha(SCRIPT),'app_sha256':app_hashes(),
              'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'source':TEXT,'source_date':'not provided','target_provider':'openrouter','target_model':MODEL,
              'pipeline_provider':'openrouter','pipeline_model':MODEL,'coverage_policy':'evidence_supported_only_v1','test_budget':1,
              'operator':'Simulated: confirm the only extracted candidate if source-backed; accept the one pending question only if it asks about tea and expected behaviour explicitly contains jasmine tea.',
              'stop':'No retries after a dispatched failure or timeout; stop if code or frozen configuration changes.',
              'scope':'One synthetic example, simulated operator decisions and automatic assessment. Functional demonstration, not independent validity or population accuracy.'}
    write(OUT/'protocol.json',protocol);print('Frozen one synthetic source; no model call.')
def check(p):
    assert sha(SCRIPT)==p['script_sha256'] and app_hashes()==p['app_sha256']
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==p['git_head']
def run():
    p=json.loads((OUT/'protocol.json').read_text());check(p);path=OUT/'ledger.json'
    if path.exists():raise RuntimeError('Existing ledger; no repeat')
    ledger={'protocol_sha256':sha(OUT/'protocol.json'),'started_at_utc':now(),'requests':[],'status':'running'}
    def save():write(path,ledger)
    def call(method,url,body=None):
        check(p); item={'method':method,'path':url,'request':body,'state':'dispatched','started_at_utc':now()};ledger['requests'].append(item);save()
        req=Request(API+url,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=900) as resp:item.update(state='returned',status=resp.status,response=json.loads(resp.read()))
        except HTTPError as exc:item.update(state='http_error',status=exc.code,response=exc.read().decode(errors='replace'))
        except Exception as exc:item.update(state='transport_error',error_type=type(exc).__name__)
        item['finished_at_utc']=now();save()
        if item['state']!='returned':raise RuntimeError('Request did not return successfully; not retried')
        return item['response']
    save()
    try:
        c=call('POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':[{'message_id':'M1','role':'user','content':TEXT}]})
        assert c['messages'][0]['original_timestamp'] is None
        cid=c['conversation_id'];ledger['conversation_id']=cid;save()
        exported=call('GET',f'/conversations/{cid}/export'); assert exported['conversation']['messages'][0]['original_timestamp'] is None
        memories=call('POST',f'/conversations/{cid}/extract',{'provider':'rule_based'})
        assert len(memories)==1 and 'jasmine tea' in memories[0]['canonical_value'].lower() and memories[0]['source_message_ids']==['M1']
        call('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':[memories[0]['memory_id']]})
        audit=call('POST','/audits',{'conversation_id':cid,'target_configuration':'strong','provider':'openrouter','model':MODEL,
          'pipeline_provider':'openrouter','pipeline_model':MODEL,'semantic_review_provider':'openrouter','semantic_review_model':MODEL,
          'evaluator_provider':'rule_based','test_budget':1,'coverage_policy':'evidence_supported_only_v1',
          'random_seed':42,'temperature':0,'memory_strategy':'strong_rule_based'})
        rid=audit['run_id'];ledger['run_id']=rid;save()
        call('POST',f'/audits/{rid}/generate-tests')
        suite=call('GET',f'/audits/{rid}/test-review');assert len(suite['tests'])==1
        test=suite['tests'][0];assert test['quality_status']=='pending' and 'tea' in test['prompt'].lower() and 'jasmine tea' in test['expected_behavior'].lower()
        call('PATCH',f"/audits/{rid}/tests/{test['test_id']}/review",{'quality_status':'accepted','note':'Simulated smoke review against the synthetic source; not a human label.'})
        call('POST',f'/audits/{rid}/execute');call('POST',f'/audits/{rid}/evaluate')
        result=call('GET',f'/audits/{rid}/results');assert result['run_id']==rid
        saved=call('GET',f'/audits/{rid}');assert saved['status']=='COMPLETED'
        call('GET',f'/audits/{rid}/agent-executions')
        ledger['status']='completed'
    except Exception as exc:
        ledger['status']='stopped';ledger['error_type']=type(exc).__name__;ledger['error']=str(exc)
    ledger['finished_at_utc']=now();save();print(json.dumps({'status':ledger['status'],'conversation_id':ledger.get('conversation_id'),'run_id':ledger.get('run_id'),'error':ledger.get('error')},ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);globals()[parser.parse_args().stage]()
