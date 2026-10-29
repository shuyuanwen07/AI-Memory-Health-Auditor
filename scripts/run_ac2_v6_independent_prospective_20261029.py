"""Frozen exploratory v6 product scope study; no target answering or paid calls."""
import argparse, hashlib, json, pathlib, random, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/proposal-delivery/ac2-independent-source-proposal-20261029/histories.json'
OUT = ROOT / 'output/proposal-delivery/ac2-v6-independent-prospective-product-20261029-v1'
SCRIPT = pathlib.Path(__file__).resolve()
URL = 'http://127.0.0.1:8000/api/v1'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def write(path, value, mode='w'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding='utf8') as f: json.dump(value, f, indent=2, ensure_ascii=False); f.write('\n')
def utc(): return datetime.now(timezone.utc).isoformat()
def app_hashes(): return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
def load_source():
    d=json.loads(SOURCE.read_bytes()); rows=d['conversations']
    if len(rows)!=30 or len({r['conversation_id'] for r in rows})!=30: raise ValueError('Expected exactly 30 unique histories')
    for row in rows:
        ids=[m['source_id'] for m in row['messages']]
        if not all(ids) or len(ids)!=len(set(ids)): raise ValueError('Invalid source IDs')
    return rows

def freeze():
    rows=load_source(); OUT.mkdir(parents=True,exist_ok=False)
    p={'format':'ac2-v6-prospective-product-freeze-v1','frozen_at_utc':utc(),
       'source_path':str(SOURCE.relative_to(ROOT)),'source_sha256':sha(SOURCE),'history_ids':[x['conversation_id'] for x in rows],
       'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       'application_sha256':app_hashes(),'runner_sha256':sha(SCRIPT), 'expected_generator_version':'rule-based-v40', 'expected_scope_version':'source-scope-review-v6',
       'source_provenance':'30 new AI-authored synthetic conversations; author reports no access to prior project cases or outcomes. No human validation, independent authorship authentication, or random-user sampling. AI reviewer flagged IND-002 relation uncertain and IND-030 type semantic concern; these author interpretations are not gold and do not drive candidate confirmation.',
       'design':'For every frozen history in order, import exact source messages, run rule-based extraction, simulate confirmation of every candidate (provisional, not a human finding), create rule-based audit budget 4, generate once, save before state, invoke product scope-review v6 once, save after state. Never execute target answers. No paid models, no retries or post-outcome selection.',
       'requested_question_slots':120,'generation_failure_rule':'Record every whole-suite failure or missing question; no invented per-question verdict, no replacement history.',
       'review':'Two separate blind packets with all generated questions, expected behaviour, cited provisional memories and complete original source. Remove pre/post gate statuses and warnings; preserve reviewer labels as blank pending human review. AI agents may provide separate provisional reviews but are not human reviewers.',
       'analysis':'Against independent human-consensus question validity, report invalid rejected or pending and valid rejected or pending before and after, question and history coverage, disagreement/uncertainty, proportion pending and per-history workload. Cluster by history, do not count unanswered slots as invalid. No post hoc acceptance threshold or claim of causality.',
       'limits':['The changed v6 source-scope rule is optional, advisory and may raise false warnings.','Provisional source extraction and author references are not human gold.','These 30 AI-authored synthetic sources share design patterns and are not representative of a population.','Historic v3 and current v6 have different source-selection behaviour; this is before/after opt-in product checking, not a separately isolated v3/v6 deployment comparison.']}
    write(OUT/'protocol.json',p,'x'); print('Frozen',len(rows),'histories; no questions generated.',flush=True)

def request(method,path,data,entry):
    item={'method':method,'path':path,'requested_at':utc(),'request':data,'status':'dispatched'};entry['requests'].append(item);write(OUT/'ledger.json',ledger)
    req=urllib.request.Request(URL+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as r:
            item.update(status='returned',http_status=r.status,response=json.loads(r.read()))
    except urllib.error.HTTPError as e:
        item.update(status='http_error',http_status=e.code,response=e.read().decode(errors='replace'))
    except Exception as e:
        item.update(status='transport_error',error_type=type(e).__name__,message=str(e))
    write(OUT/'ledger.json',ledger)
    if item['status']!='returned': raise RuntimeError(f"{item['status']} in {path}")
    return item['response']

def run():
    global ledger
    protocol=json.loads((OUT/'protocol.json').read_bytes()); rows=load_source()
    if sha(SOURCE)!=protocol['source_sha256'] or sha(SCRIPT)!=protocol['runner_sha256'] or app_hashes()!=protocol['application_sha256']:
        raise ValueError('Frozen source, runner or app changed; stop')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=protocol['git_revision']: raise ValueError('Revision changed; stop')
    if (OUT/'ledger.json').exists(): raise ValueError('Ledger already exists; do not repeat or retry')
    ledger={'format':'ac2-v6-prospective-ledger-v1','protocol_sha256':sha(OUT/'protocol.json'),'started_at_utc':utc(),
            'histories':[{'history_id':r['conversation_id'],'status':'not_started','requests':[]} for r in rows]}
    write(OUT/'ledger.json',ledger,'x')
    for source,entry in zip(rows,ledger['histories']):
        if app_hashes()!=protocol['application_sha256'] or sha(SCRIPT)!=protocol['runner_sha256'] or sha(SOURCE)!=protocol['source_sha256']:
            entry['status']='stopped_source_drift'; ledger['stopped_at_utc']=utc(); write(OUT/'ledger.json',ledger); print('Stopped due to source drift',flush=True); break
        try:
            entry['status']='in_progress';write(OUT/'ledger.json',ledger)
            messages=[{'message_id':m['source_id'],'role':m['role'],'content':m['text'],'timestamp':m['timestamp'],'original_timestamp':m['timestamp']} for m in source['messages']]
            c=request('POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':messages},entry); cid=c['conversation_id'];entry['product_conversation_id']=cid
            extracted=request('POST',f'/conversations/{cid}/extract',{'provider':'rule_based'},entry)
            entry['candidate_count']=len(extracted)
            if not extracted: raise ValueError('No candidates generated')
            confirmed=request('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':[m['memory_id'] for m in extracted]},entry)
            entry['provisional_memories']=confirmed
            a=request('POST','/audits',{'conversation_id':cid,'target_configuration':'weak','provider':'rule_based','model':'rule-based-target-ai','pipeline_provider':'rule_based','evaluator_provider':'rule_based','semantic_review_provider':'rule_based','test_budget':4,'random_seed':42,'temperature':0,'memory_strategy':'weak_first_hit'},entry)
            rid=a['run_id'];entry['run_id']=rid
            request('POST',f'/audits/{rid}/generate-tests',None,entry)
            before=request('GET',f'/audits/{rid}/test-review',None,entry);entry['before']=before
            if any(t.get('generator_version') != protocol['expected_generator_version'] for t in before['tests']): raise ValueError('Running generator differs from frozen expected version')
            after=request('POST',f'/audits/{rid}/tests/scope-review',None,entry);entry['after']=after
            old={x['test_id'] for x in before['tests']}; new={x['test_id'] for x in after['tests']}
            if old!=new: raise ValueError('Before and after suite IDs differ')
            entry['status']='completed'
        except Exception as e:
            entry.update(status='failed',error_type=type(e).__name__,error=str(e))
        write(OUT/'ledger.json',ledger);print(entry['history_id'],entry['status'],flush=True)
    ledger['finished_at_utc']=utc();write(OUT/'ledger.json',ledger)
    pack()

def pack():
    data=json.loads((OUT/'ledger.json').read_bytes()); p=json.loads((OUT/'protocol.json').read_bytes()); rows=load_source()
    if sha(SOURCE)!=p['source_sha256'] or data['protocol_sha256']!=sha(OUT/'protocol.json'):raise ValueError('Frozen source or protocol changed')
    by_history={h['conversation_id']:h for h in rows}; items=[]; key={}; statuses={}
    for e in data['histories']:
        if 'before' not in e: continue
        byid={m['memory_id']:m for m in e['provisional_memories']}
        post={t['test_id']:t for t in e.get('after',{}).get('tests',[])}
        for t in e['before']['tests']:
            bid=hashlib.sha256((p['source_sha256']+':'+e['history_id']+':'+t['test_id']).encode()).hexdigest()[:24]
            if bid in key: raise ValueError('Duplicate blind ID')
            refs=[]
            for mid in t['supporting_memory_ids']:
                m=byid.get(mid)
                refs.append({'memory_id':mid,'canonical_value':m.get('canonical_value') if m else None,'source_message_ids':m.get('source_message_ids') if m else [],'relationships':m.get('relationships',[]) if m else []})
            items.append({'blind_id':bid,'history_id':e['history_id'],'question':t['prompt'],'expected_behavior':t['expected_behavior'],'supporting_provisional_memories':refs,'grounding':None,'executability':None,'reason':''})
            key[bid]={'history_id':e['history_id'],'product_run_id':e.get('run_id'),'test_id':t['test_id'],'dimension':t['dimension'],'before':t['quality_status'],'after':post[t['test_id']]['quality_status'] if t['test_id'] in post else None}
        statuses[e['history_id']]=e['status']
    random.Random(42029).shuffle(items)
    ledger_by_history={e['history_id']:e for e in data['histories']}
    reviewed_histories=[{'history_id':hid,'messages':by_history[hid]['messages'], 'provisional_memories':[{'memory_id':m['memory_id'],'canonical_value':m['canonical_value'],'source_message_ids':m['source_message_ids'],'relationships':m['relationships']} for m in ledger_by_history[hid]['provisional_memories']]} for hid in sorted({i['history_id'] for i in items})]
    material={'histories':reviewed_histories,'items':items}; material_hash=hashlib.sha256(canonical(material)).hexdigest()
    for i in (1,2):
        packet={'format':'ac2-v6-prospective-blind-review-v1','reviewer_slot':i,'material_sha256':material_hash,
                'instructions':'Independently judge source grounding and structural executability for each generated question and expected behaviour. Enter valid, invalid, or uncertain and a short reason. Do not view the other reviewer or any automatic warning/score before reviewing. AI assistance must be disclosed. Source histories and extracted memories were AI-authored/automatically produced, and no human validity is assumed.',
                'reviewer_declaration':{'reviewer_label':None,'completed_by_human':None,'completed_independently':None,'seen_other_review':None,'seen_automatic_scores_or_warnings':None,'used_ai_assistance':None},**material}
        write(OUT/f'reviewer-{i}.json',packet,'x')
    write(OUT/'private-mapping.json',{'format':'ac2-v6-prospective-private-mapping-v1','material_sha256':material_hash,'items':key,'history_status':statuses},'x')
    print('Prepared',len(items),'blind questions from',len(reviewed_histories),'histories; human labels remain empty.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run','pack']);args=parser.parse_args();globals()[args.stage]()
