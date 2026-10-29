"""Same-source development retest through the local product; never calls a model."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
SOURCE = ROOT / 'output/proposal-delivery/ac2-prospective-new-histories-20261029/histories.json'
ORIGINAL = ROOT / 'output/proposal-delivery/ac2-v37-same-source-development-20261029-v1/protocol.json'
OUT = ROOT / 'output/proposal-delivery/ac2-v39-same-source-development-20261029-v1'
URL = 'http://127.0.0.1:8000/api/v1'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def write(path, data, mode='w'):
    with path.open(mode, encoding='utf8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
def app_hashes(): return {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'backend/app').rglob('*.py'))}
def sources():
    original=json.loads(ORIGINAL.read_text()); rows=json.loads(SOURCE.read_text())['conversations']
    if sha(SOURCE)!=original['source_sha256'] or [r['conversation_id'] for r in rows]!=original['history_ids']:
        raise ValueError('Sources differ from the original frozen 30-history study.')
    return rows


def freeze():
    rows=sources(); OUT.mkdir(parents=True, exist_ok=False)
    write(OUT/'protocol.json', {
        'format':'ac2-v39-same-source-development-freeze-v1','frozen_at_utc':utc(),
        'source_path':str(SOURCE.relative_to(ROOT)), 'source_sha256':sha(SOURCE),
        'prior_protocol_path':str(ORIGINAL.relative_to(ROOT)), 'prior_protocol_sha256':sha(ORIGINAL),
        'history_ids':[r['conversation_id'] for r in rows],
        'application_sha256':app_hashes(),'runner_sha256':sha(SCRIPT),
        'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'settings':{'extraction_provider':'rule_based','memory_confirmation':'simulated: all extracted candidates; not human reference gold',
                    'pipeline_provider':'rule_based','generator_version':'rule-based-v39',
                    'target_provider':'rule_based','test_budget_maximum_per_history':4,'random_seed':42,
                    'target_execution':False,'scope_review_execution':True,'model_calls':False},
        'design':'Every original source once, original order. Use real product conversation, extraction, simulated confirmation, audit creation and test generation APIs. Record whole-suite failure, all generated questions and saved per-candidate filter observation. Invoke optional source-scope review once, recording before and after. Never execute target or call a model.',
        'interpretation':'Development retest after examining the same source outcomes; not independent validation or a human validity measurement. AI-authored histories share patterns; Previous development outcomes remain preserved.',
        'stop':'Stop immediately on source, application or runner hash change; never retry or replace an attempted history.',
    },'x')
    print('Frozen 30 histories and current source; no product requests yet.',flush=True)


def run():
    p=json.loads((OUT/'protocol.json').read_text()); rows=sources()
    def assert_frozen():
        if (sha(SOURCE)!=p['source_sha256'] or sha(ORIGINAL)!=p['prior_protocol_sha256'] or
                sha(SCRIPT)!=p['runner_sha256'] or app_hashes()!=p['application_sha256']):
            raise RuntimeError('FROZEN_SOURCE_CHANGED')
    assert_frozen()
    if (OUT/'ledger.json').exists(): raise ValueError('Ledger exists; do not repeat.')
    ledger={'format':'ac2-v39-same-source-development-ledger-v1','protocol_sha256':sha(OUT/'protocol.json'),
            'started_at_utc':utc(),'histories':[{'history_id':x['conversation_id'],'status':'not_started','requests':[]} for x in rows]}
    write(OUT/'ledger.json',ledger,'x')
    def request(method,path,data,entry):
        assert_frozen()
        record={'method':method,'path':path,'requested_at':utc(),'request':data,'status':'dispatched'}
        entry['requests'].append(record);write(OUT/'ledger.json',ledger)
        req=urllib.request.Request(URL+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=120) as response:
                record.update(status='returned',http_status=response.status,response=json.loads(response.read()))
        except urllib.error.HTTPError as exc:
            record.update(status='http_error',http_status=exc.code,response=exc.read().decode(errors='replace'))
        except Exception as exc:
            record.update(status='transport_error',error_type=type(exc).__name__,error=str(exc))
        write(OUT/'ledger.json',ledger)
        assert_frozen()
        return record
    for source,entry in zip(rows,ledger['histories']):
        entry['status']='in_progress';write(OUT/'ledger.json',ledger)
        try:
            messages=[{'message_id':m['source_message_id'],'role':m['role'],'content':m['text'],
                       'timestamp':m['timestamp'],'original_timestamp':m['timestamp']} for m in source['messages']]
            def must(method,path,data):
                r=request(method,path,data,entry)
                if r['status']!='returned': raise ValueError(f"{r['status']} in {path}")
                return r['response']
            conversation=must('POST','/conversations',{'authorised':True,'source_origin':'synthetic','messages':messages})
            cid=conversation['conversation_id'];entry['product_conversation_id']=cid
            extracted=must('POST',f'/conversations/{cid}/extract',{'provider':'rule_based'})
            entry['extracted_count']=len(extracted)
            if not extracted: raise ValueError('No extracted candidates to confirm.')
            entry['simulated_confirmed_memories']=must('POST',f'/conversations/{cid}/confirm-ground-truth',{'confirmed_memory_ids':[m['memory_id'] for m in extracted]})
            a=must('POST','/audits',{'conversation_id':cid,'target_configuration':'weak','provider':'rule_based',
                'model':'rule-based-target-ai','pipeline_provider':'rule_based','evaluator_provider':'rule_based',
                'semantic_review_provider':'rule_based','test_budget':4,'random_seed':42,'temperature':0,'memory_strategy':'weak_first_hit'})
            rid=a['run_id'];entry['run_id']=rid
            signature=a.get('reproducibility',{}).get('audit_runtime_signature',{})
            if signature.get('generator')!='rule-based-v39': raise RuntimeError('UNEXPECTED_GENERATOR')
            result=request('POST',f'/audits/{rid}/generate-tests',None,entry)
            saved=must('GET',f'/audits/{rid}',None)
            entry['generation_observations']=saved.get('reproducibility',{}).get('generation_observations',[])
            if result['status']=='returned':
                entry['tests']=result['response'];entry['review']=must('GET',f'/audits/{rid}/test-review',None)
                entry['scope_review']=must('POST',f'/audits/{rid}/tests/scope-review',None)
                if {t['test_id'] for t in entry['review']['tests']} != {t['test_id'] for t in entry['scope_review']['tests']}: raise RuntimeError('SCOPE_REVIEW_CHANGED_SUITE')
                entry['status']='completed'
            else:
                entry['status']='generation_failed';entry['generation_error']=result
        except RuntimeError as exc:
            entry['status']='stopped';entry['error']=str(exc);ledger['stopped_at_utc']=utc();write(OUT/'ledger.json',ledger)
            print('STOP',entry['history_id'],str(exc),flush=True);raise
        except Exception as exc:
            entry.update(status='failed',error_type=type(exc).__name__,error=str(exc))
        write(OUT/'ledger.json',ledger);print(entry['history_id'],entry['status'],flush=True)
    ledger['finished_at_utc']=utc();write(OUT/'ledger.json',ledger);summarise()


def summarise():
    ledger=json.loads((OUT/'ledger.json').read_text()); counters=Counter(); reasons=Counter(); dims=Counter()
    for entry in ledger['histories']:
        counters[entry['status']]+=1
        for t in entry.get('tests',[]): dims[t['dimension']]+=1
        for obs in entry.get('generation_observations',[]):
            counters['rejected_candidates']+=obs.get('rejected_candidate_count',0)
            for reject in obs.get('rejected_candidates',[]): reasons[reject['reason']]+=1
    summary={'format':'ac2-v39-same-source-development-summary-v1','protocol_sha256':sha(OUT/'protocol.json'),
        'ledger_sha256':sha(OUT/'ledger.json'),'planned_histories':30,'max_question_budget_per_history':4,
        'histories_by_status':dict(counters),'saved_questions':sum(dims.values()),'saved_questions_by_dimension':dict(dims),
        'rejected_by_local_validator':counters['rejected_candidates'],'rejection_reasons':dict(reasons),
        'short_histories':sum(1 for e in ledger['histories'] if e.get('review',{}).get('count_target_met') is False),
        'cost':{'paid_model_calls':0,'provider_reported_cost_usd':0},
        'scope':'Same-source post-outcome development retest; rule extraction and simulated confirmation; generated questions are not human validated, no target answers executed.',
        'limits':['The old and new observations are separate runs; source and source outcomes were already observed.',
                  'Prior failed suites did not yield per-question labels; no claim of question-validity improvement.',
                  'Rule-extracted memories and simulated confirmation are not source-reviewed ground truth.',
                  'Four is a per-history maximum, not a guaranteed number or formal minimum.']}
    write(OUT/'summary.json',summary,'x');print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['freeze','run']);args=parser.parse_args();globals()[args.stage]()
