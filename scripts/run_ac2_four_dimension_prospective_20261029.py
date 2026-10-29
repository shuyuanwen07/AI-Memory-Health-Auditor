"""Freeze then run a small new-source four-dimension AC2 feasibility study.

Synthetic records and graph edges are authored for this study and simulated as
operator-confirmed. No target answers, human validity or population claims.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1'
API = 'http://127.0.0.1:8000/api/v1'
MODEL = 'openai/gpt-6-luna'
PARAMS = [
    ('Solstice', 'email', 'text messages', 'east shed', 'west shed', 'greenhouse', 'courtyard'),
    ('Cobalt', 'phone calls', 'email', 'north room', 'south room', 'auditorium', 'garden'),
    ('Fern', 'a paper notebook', 'a shared digital notebook', 'upper cabinet', 'lower cabinet', 'studio', 'hall'),
    ('Orion', 'a shared board', 'a printed log', 'blue cupboard', 'red cupboard', 'lobby', 'terrace'),
    ('Willow', 'email', 'phone calls', 'front store', 'back store', 'classroom', 'workshop'),
    ('Marble', 'text messages', 'email', 'small locker', 'large locker', 'library', 'museum'),
    ('Saffron', 'a digital calendar', 'a paper calendar', 'indoor cabinet', 'outdoor cabinet', 'gallery', 'atrium'),
    ('Tern', 'phone calls', 'text messages', 'east shelf', 'west shelf', 'kitchen', 'dining room'),
]

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def write(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
def app_hashes(): return {str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}

def dataset():
    rows=[]
    for n,(name,general,scoped,old,new,venue1,venue2) in enumerate(PARAMS,1):
        texts=[f'I generally use {general} for coordinating projects.',
               f'For the {name} activity, use {scoped} for coordinating projects; the general preference remains unchanged elsewhere.',
               f'The first {name} logistics note set the storage location to {old}.',
               f'A signed replacement moved the {name} storage location from {old} to {new}; the old location is no longer current.',
               f'For the {name} event, an active site plan says the {venue1} is the only final confirmed venue.',
               f'For the same {name} event, an active signed booking says the {venue2} is the only final confirmed venue. Neither record has priority and no replacement has been made.']
        rows.append({'id':f'FS{n:02}', 'texts':texts, 'edges':[{'source':1,'target':0,'type':'CONTEXTUAL_OVERRIDE'},
            {'source':3,'target':2,'type':'UPDATE'},{'source':5,'target':4,'type':'CONFLICT'}]})
    return rows

def freeze():
    OUT.mkdir(parents=True,exist_ok=False)
    write(OUT/'sources.json',{'kind':'authored synthetic, not human-verified','histories':dataset()})
    protocol={'created_at_utc':now(),'source_sha256':digest(OUT/'sources.json'),'runner_sha256':digest(Path(__file__).resolve()),
      'application_sha256':app_hashes(),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'model':MODEL,'histories':8,'budget':4,'coverage_policy':'strict_full_v1',
      'design':'For every frozen history in order: import synthetic user messages, add six authored candidate memories and three authored edges, simulate operator confirmation, preview, create one audit, generate once, save execution receipts and test review. Never run target answers.',
      'unit':'One history, not repeated answers; all eight use the same structural template.',
      'limitations':['New-source feasibility after observed development outcomes, not a random real-world sample.','Authored reference graph is not independently human-verified; confirmation is simulated.','Source structures are related templates, not eight independent populations.','Question validity requires source-based review; gate acceptance is not proof.','Model-controlled sampling; unknown failed-request costs are not zero.'],
      'stop_rule':'No retry after a dispatched request or transport timeout; stop on application, runner, source or git-head drift.'}
    write(OUT/'protocol.json',protocol);print('Frozen eight sources and protocol; no model calls.',flush=True)

def check(protocol):
    if digest(OUT/'sources.json')!=protocol['source_sha256'] or digest(Path(__file__).resolve())!=protocol['runner_sha256'] or app_hashes()!=protocol['application_sha256'] or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=protocol['git_head']:
        raise RuntimeError('Frozen inputs changed')

def run():
    protocol=json.loads((OUT/'protocol.json').read_text());check(protocol)
    ledger_path=OUT/'ledger.json'
    if ledger_path.exists(): raise RuntimeError('Ledger exists: no re-dispatch')
    ledger={'protocol_sha256':digest(OUT/'protocol.json'),'started_at_utc':now(), 'histories':[{'id':h['id'],'state':'not_started','requests':[]} for h in dataset()]}
    def save(): write(ledger_path,ledger)
    save()
    def request(entry, method, path, body=None):
        call={'method':method,'path':path,'body':body,'state':'dispatched','started_at':now()};entry['requests'].append(call);save()
        req=Request(API+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=900) as response: call.update(state='returned',status=response.status,response=json.loads(response.read()))
        except HTTPError as exc: call.update(state='http_error',status=exc.code,response=exc.read().decode(errors='replace'))
        except Exception as exc: call.update(state='transport_error',error_type=type(exc).__name__)
        call['finished_at']=now();save();return call
    def require(call):
        if call['state']!='returned': raise RuntimeError('Request did not return successfully')
        return call['response']
    for h,entry in zip(dataset(),ledger['histories']):
        try:
            check(protocol);entry['state']='in_progress';save()
            messages=[{'message_id':f"{h['id']}-M{i+1}",'role':'user','content':text,'timestamp':f'2026-01-{i+1:02}T09:00:00Z'} for i,text in enumerate(h['texts'])]
            cid=require(request(entry,'POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':messages}))['conversation_id']
            entry['conversation_id']=cid;ids=[]
            for i,value in enumerate(h['texts']):
                edge=next((e for e in h['edges'] if e['source']==i),None)
                relations=[] if edge is None else [{'type':edge['type'],'target_memory_id':ids[edge['target']],
                    'evidence_message_ids':[f"{h['id']}-M{edge['target']+1}",f"{h['id']}-M{i+1}"]}]
                body={'conversation_id':cid,'canonical_value':value,'source_message_ids':[f"{h['id']}-M{i+1}"],'relationships':relations}
                ids.append(require(request(entry,'POST','/memories',body))['memory_id'])
            require(request(entry,'POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':ids}))
            require(request(entry,'GET',f'/conversations/{cid}/test-coverage-preview?test_budget=4&coverage_policy=strict_full_v1'))
            audit={'conversation_id':cid,'target_configuration':'weak','provider':'rule_based','model':'rule-based-target-ai',
                   'pipeline_provider':'openrouter','pipeline_model':MODEL,'semantic_review_provider':'openrouter','semantic_review_model':MODEL,
                   'evaluator_provider':'rule_based','test_budget':4,'coverage_policy':'strict_full_v1','random_seed':42,'temperature':0,
                   'memory_strategy':'weak_first_hit'}
            rid=require(request(entry,'POST','/audits',audit))['run_id'];entry['run_id']=rid;save()
            generated=request(entry,'POST',f'/audits/{rid}/generate-tests')
            request(entry,'GET',f'/audits/{rid}/agent-executions');request(entry,'GET',f'/audits/{rid}')
            require(generated);require(request(entry,'GET',f'/audits/{rid}/test-review'))
            entry['state']='completed'
        except Exception as exc:
            entry['state']='stopped_source_drift' if str(exc)=='Frozen inputs changed' else 'failed';entry['error']=str(exc)
            save();print(h['id'],entry['state'],flush=True)
            if entry['state']=='stopped_source_drift':break
            continue
        save();print(h['id'],entry['state'],flush=True)
    ledger['finished_at_utc']=now();save()
    counts={};dimensions={};total=0
    for entry in ledger['histories']:
        counts[entry['state']]=counts.get(entry['state'],0)+1
        if entry['state']=='completed':
            tests=next(r['response']['tests'] for r in entry['requests'] if r['path'].endswith('/test-review') and r['state']=='returned')
            for test in tests: dimensions[test['dimension']]=dimensions.get(test['dimension'],0)+1
            total+=len(tests)
    write(OUT/'summary.json',{'protocol_sha256':digest(OUT/'protocol.json'),'ledger_sha256':digest(ledger_path),'states':counts,
        'saved_questions':total,'dimensions':dimensions,'limitations':protocol['limitations']})
    print(json.dumps({'states':counts,'saved_questions':total,'dimensions':dimensions}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);globals()[parser.parse_args().stage]()
