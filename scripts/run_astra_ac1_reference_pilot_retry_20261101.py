"""Freeze and collect four source-only Astra AC1 extraction observations."""
import argparse
import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/astra-ac1-reference-pilot-20261101-v2'
SOURCE = ROOT / 'output/proposal-delivery/ac1-ac2-source-only-2026-10-28-v3/reviewed-source.json'
SCRIPT = Path(__file__).resolve()
IDS = ('AC3-H01', 'AC3-H05', 'AC3-H10', 'AC3-H20')
API = 'http://127.0.0.1:8000/api/v1'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
now = lambda: datetime.now(timezone.utc).isoformat()

def save(path, value, exclusive=False):
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8') as f: f.write(content)
    else:
        temp = path.with_suffix('.tmp'); temp.write_text(content); temp.replace(path)

def app_hashes():
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}

def freeze():
    source = json.loads(SOURCE.read_text())
    histories = [h for h in source['histories'] if h['history_id'] in IDS]
    if tuple(h['history_id'] for h in histories) != IDS:
        raise ValueError('Missing or reordered source histories')
    OUT.mkdir(parents=True, exist_ok=False)
    save(OUT/'reference-and-sources.json', {'histories': histories, 'scope': source['scope'],
         'reference_qualifications': source['reference_qualifications'], 'review_provenance': source['review_provenance']}, True)
    protocol = {'format':'astra-ac1-source-only-pilot-v1', 'frozen_utc':now(), 'ids':IDS,
        'source_sha256':sha(SOURCE), 'reference_sha256':sha(OUT/'reference-and-sources.json'),
        'runner_sha256':sha(SCRIPT), 'application_sha256':app_hashes(),
        'model':{'provider':'openai', 'model':'gpt-6-astra', 'reasoning_effort':'max'},
        'design':'Four selected previously studied synthetic histories. Freeze the existing reference before extraction. Independent source-only reference completeness review and separate post-extraction coverage review; the API receives source messages only.',
        'limitations':['Previously studied, template-related synthetic histories; not a representative sample.',
                       'Existing references are selected, may combine multiple facts, and are not assumed exhaustive.',
                       'Automated references and reviews are not human gold; explicitly record later human review.',
                       'No retry by this runner after an ambiguous dispatch; provider retries are recorded by the application.']}
    save(OUT/'protocol.json',protocol,True)
    for n in (1,2):
        save(OUT/f'reference-reviewer-{n}-blank.json', {'reviewer':f'ai-reviewer-{n}',
            'instructions':'Review source and provided reference only. Identify unsupported or partially supported reference entries, omitted substantive source information, and questionable relationship labels. Do not see extraction output. Do not treat AI work as human review.',
            'histories':[{**h,'review':{'unsupported_or_partial_facts':[], 'omitted_source_information':[],
            'questionable_relationships':[], 'completeness':'', 'note':''}} for h in histories]},True)
    print('Frozen four sources and source-only reference review packets; no model calls.')

def run():
    protocol=json.loads((OUT/'protocol.json').read_text())
    if sha(SOURCE)!=protocol['source_sha256'] or sha(OUT/'reference-and-sources.json')!=protocol['reference_sha256'] or sha(SCRIPT)!=protocol['runner_sha256'] or app_hashes()!=protocol['application_sha256']:
        raise ValueError('Frozen inputs or application changed')
    histories=json.loads((OUT/'reference-and-sources.json').read_text())['histories']
    def one(h):
        dest=OUT/(h['history_id']+'-extraction.json')
        if dest.exists(): return {'history_id':h['history_id'],'status':'existing_attempt_not_repeated'}
        record={'history_id':h['history_id'],'protocol_sha256':sha(OUT/'protocol.json'),'status':'started','operations':[]}
        save(dest,record,True)
        def call(method,path,body=None):
            if app_hashes()!=protocol['application_sha256']: raise RuntimeError('Application changed after freeze')
            item={'method':method,'path':path,'request':body,'state':'dispatched','time':now()};record['operations'].append(item);save(dest,record)
            req=Request(API+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            try:
                with urlopen(req,timeout=1200) as response: item.update(state='returned',status=response.status,response=json.load(response))
            except HTTPError as e: item.update(state='http_error',status=e.code,error=e.read().decode(errors='replace')[:1500])
            except Exception as e: item.update(state='ambiguous',error_type=type(e).__name__)
            save(dest,record)
            if item['state']!='returned': raise RuntimeError('Request failed or has unknown outcome; no automatic retry')
            return item['response']
        try:
            messages=[{'message_id':m['message_id'],'role':m['role'],'content':m['text'],
                       'timestamp':f"2000-01-01T00:00:{i:02}Z"} for i,m in enumerate(h['source_messages'])]
            c=call('POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':messages})
            cid=c['conversation_id']; record['conversation_id']=cid;save(dest,record)
            candidates=call('POST',f'/conversations/{cid}/extract',{'provider':'openai','model':'gpt-6-astra'})
            trace=call('GET',f'/conversations/{cid}/agent-executions')
            record.update(status='completed_reference_review_pending',candidate_count=len(candidates),agent_trace_count=len(trace))
        except Exception as e: record.update(status='stopped',error_type=type(e).__name__,error=str(e)[:300])
        save(dest,record);print(h['history_id'],record['status'],flush=True)
        return {'history_id':h['history_id'],'status':record['status']}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(one,histories))
    save(OUT/'collection-summary.json',{'runs':result,'reference_review':'pending','extraction_review':'pending'},True)
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('freeze','run'));globals()[p.parse_args().stage]()
