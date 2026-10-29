"""Expanded same-history partial-coverage model generation probe; no target answers.

A descriptive development probe: not human labels or independent validation.
The five histories were previously observed. All failed steps are retained.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/proposal-delivery/ac2-independent-source-proposal-20261029/histories.json'
OUT = ROOT / 'output/proposal-delivery/ac2-partial-twenty-five-history-development-20261029-v1'
SCRIPT = Path(__file__).resolve()
API = 'http://127.0.0.1:8000/api/v1'
MODEL = 'openai/gpt-6-luna'
IDS = [f'IND-{n:03d}' for n in range(6, 31)]

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def write(path, obj, mode='w'):
    with path.open(mode, encoding='utf8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False); f.write('\n')
def app_hashes():
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def sources():
    corpus = json.loads(SOURCE.read_text())['conversations']
    by_id = {row['conversation_id']: row for row in corpus}
    if len(by_id) != len(corpus) or not all(i in by_id for i in IDS): raise ValueError('Frozen source IDs missing or duplicated')
    return [by_id[i] for i in IDS]

def freeze():
    sources(); OUT.mkdir(parents=True, exist_ok=False)
    protocol = {'format':'ac2-partial-twenty-five-history-development-freeze-v1','frozen_at_utc':now(),
      'source_path':str(SOURCE.relative_to(ROOT)), 'source_sha256':digest(SOURCE), 'history_ids':IDS,
      'runner_sha256':digest(SCRIPT), 'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'application_sha256':app_hashes(), 'model':MODEL,'provider':'openrouter', 'temperature':0,
      'max_questions_per_history':4,'coverage_policy':'evidence_supported_only_v1',
      'source_confirmation':'All rule-extracted candidate memories are provisionally confirmed by simulated operator; not human-reviewed gold.',
      'design':'Every selected history is processed once in fixed ID order. Import exact messages, rule-extract, simulate candidate confirmation, preview, create audit, invoke model generation once, then read persisted review and agent execution receipts. Do not call target or evaluator. Whole-suite failures and shortfalls remain in denominator.',
      'selection':'IDs 6–30 from previously observed AI-authored synthetic sources; development only, not independent validation.',
      'stop_rule':'Stop on code, source or runner hash drift; no automatic retry of any API request; continue to next history after a returned failure. Transport interruption is unknown, not assumed failed or free.',
      'cost':'No financial cap requested. Provider-reported request usage is recorded when available; missing or failed-request charges may be unknown and are not silently treated as zero.',
      'limitations':['Previously observed synthetic histories; not an unbiased sample.','Automatic extraction and simulated confirmation are provisional; no human labels.','Planning and generation use the product model agent with its own bounded internal retry/repair rules; receipt availability is not a complete invoice.','No target responses or performance claims.']}
    write(OUT/'protocol.json',protocol,'x');print('Frozen 25 histories and implementation; no model called.', flush=True)

def assert_frozen(protocol):
    if digest(SOURCE)!=protocol['source_sha256'] or digest(SCRIPT)!=protocol['runner_sha256'] or app_hashes()!=protocol['application_sha256']:
        raise ValueError('Source or code changed after freeze; no further calls')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=protocol['git_head']:
        raise ValueError('HEAD changed after freeze; no further calls')

def save(): write(OUT/'ledger.json', ledger)
def request(method,path,body,entry,timeout=900):
    call={'method':method,'path':path,'request':body,'started_at_utc':now(),'state':'dispatched'}
    entry['requests'].append(call);save()
    req=Request(API+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=timeout) as response:
            raw=response.read(); call.update(state='returned',http_status=response.status,response=json.loads(raw))
    except HTTPError as exc:
        call.update(state='http_error',http_status=exc.code,response=exc.read().decode(errors='replace'))
    except Exception as exc:
        call.update(state='transport_error',error_type=type(exc).__name__,message=str(exc))
    call['finished_at_utc']=now();save()
    return call

def run():
    global ledger
    protocol=json.loads((OUT/'protocol.json').read_text()); assert_frozen(protocol)
    if (OUT/'ledger.json').exists(): raise ValueError('Existing ledger; do not repeat requests')
    rows=sources();ledger={'format':'ac2-partial-twenty-five-history-development-ledger-v1',
      'protocol_sha256':digest(OUT/'protocol.json'),'started_at_utc':now(),
      'histories':[{'history_id':i,'state':'not_started','requests':[]} for i in IDS]};write(OUT/'ledger.json',ledger,'x')
    for source,entry in zip(rows,ledger['histories']):
        try:
            assert_frozen(protocol); entry['state']='in_progress';save()
            messages=[{'message_id':m['source_id'],'role':m['role'],'content':m['text'],
                       'timestamp':m['timestamp'],'original_timestamp':m['timestamp']} for m in source['messages']]
            call=request('POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':messages},entry)
            if call['state']!='returned': raise RuntimeError('conversation not returned')
            cid=call['response']['conversation_id'];entry['conversation_id']=cid;save()
            call=request('POST',f'/conversations/{cid}/extract',{'provider':'rule_based'},entry)
            if call['state']!='returned': raise RuntimeError('extraction not returned')
            memories=call['response'];entry['candidate_count']=len(memories)
            if not memories: raise RuntimeError('no extracted candidates')
            call=request('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':[m['memory_id'] for m in memories]},entry)
            if call['state']!='returned': raise RuntimeError('simulated confirmation not returned')
            call=request('GET',f'/conversations/{cid}/test-coverage-preview?test_budget=4&coverage_policy=evidence_supported_only_v1',None,entry)
            if call['state']!='returned': raise RuntimeError('preview not returned')
            call=request('POST','/audits',{'conversation_id':cid,'target_configuration':'weak','provider':'rule_based',
                 'model':'rule-based-target-ai','pipeline_provider':'openrouter','pipeline_model':MODEL,
                 'semantic_review_provider':'openrouter','semantic_review_model':MODEL,'evaluator_provider':'rule_based',
                 'test_budget':4,'coverage_policy':'evidence_supported_only_v1','random_seed':42,'temperature':0,
                 'memory_strategy':'weak_first_hit'},entry)
            if call['state']!='returned': raise RuntimeError('audit creation not returned')
            rid=call['response']['run_id'];entry['run_id']=rid;save()
            generation=request('POST',f'/audits/{rid}/generate-tests',None,entry)
            # These reads are diagnostic only and do not re-dispatch generation.
            request('GET',f'/audits/{rid}/agent-executions',None,entry)
            request('GET',f'/audits/{rid}',None,entry)
            if generation['state']!='returned': raise RuntimeError('generation not returned')
            review=request('GET',f'/audits/{rid}/test-review',None,entry)
            if review['state']!='returned': raise RuntimeError('review not returned')
            entry['state']='completed'
        except Exception as exc:
            entry['state']='stopped_source_drift' if 'changed after freeze' in str(exc) else 'failed'
            entry['error_type']=type(exc).__name__;entry['error']=str(exc)
            save(); print(entry['history_id'],entry['state'],flush=True)
            if entry['state']=='stopped_source_drift': break
            continue
        save();print(entry['history_id'],entry['state'],flush=True)
    ledger['finished_at_utc']=now();save()
    summarize()

def summarize():
    data=json.loads((OUT/'ledger.json').read_text());protocol=json.loads((OUT/'protocol.json').read_text());assert_frozen(protocol)
    states={};dimensions={};statuses={};total=0;histories=0
    for row in data['histories']:
        states[row['state']]=states.get(row['state'],0)+1
        if row['state']!='completed': continue
        review=next(x['response'] for x in row['requests'] if x['path'].endswith('/test-review') and x['state']=='returned')
        tests=review['tests'];histories+=1;total+=len(tests)
        for t in tests:
            dimensions[t['dimension']]=dimensions.get(t['dimension'],0)+1
            statuses[t['quality_status']]=statuses.get(t['quality_status'],0)+1
    summary={'format':'ac2-partial-twenty-five-history-development-summary-v1','protocol_sha256':digest(OUT/'protocol.json'),
       'ledger_sha256':digest(OUT/'ledger.json'),'planned_histories':len(IDS),'states':states,'histories_with_saved_suite':histories,
       'saved_questions':total,'dimensions':dimensions,'quality_states':statuses,
       'scope':'Same previously observed AI-authored histories; model-based question generation only. Simulated confirmation; no human labels, target answers, or validity claim.',
       'cost_note':'See per-run agent execution receipts and saved observations; provider reported amounts can be missing and are not a complete bill.',
       'limitations':['Same-source development probe; not independent validation.','Questions are not human-verified; quality states are not proof of validity.','Budget is a ceiling; excluded or unavailable abilities remain unmeasured.','Failed requests may incur unreported charges.']}
    write(OUT/'summary.json',summary,'x');print(json.dumps({k:summary[k] for k in ('states','histories_with_saved_suite','saved_questions','dimensions','quality_states')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);globals()[parser.parse_args().stage]()
