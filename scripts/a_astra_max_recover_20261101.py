"""Read-only recovery of A target answers after stdout trace serialization errors.

This helper cannot execute targets,generate questions,alter labels,or retry a
provider call. It reads already committed production rows and creates evidence.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/a-astra-max-retest-20261101-v2'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def snapshot():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,TestCaseModel,TargetResponseModel
    from app.api.routes import audit_schema,public_test_schema,response_schema,target_memory_trace_payload
    regs=read(OUT/'registrations.json')['registrations'];data=[]
    with SessionLocal() as db:
        for r in regs:
            audit=db.get(AuditRunModel,r['run_id'])
            data.append({**r,'audit':audit_schema(audit).model_dump(mode='json'),
                'questions':[public_test_schema(q).model_dump(mode='json') for q in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==audit.id)).all()],
                'responses':[response_schema(a).model_dump(mode='json') for a in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==audit.id)).all()],
                'trace':target_memory_trace_payload(audit,db).model_dump(mode='json')})
    print(json.dumps({'captured_at_utc':datetime.now(timezone.utc).isoformat(),'read_only':True,'runs':data},ensure_ascii=False))

def recover():
    p=subprocess.run(['docker','compose','exec','-T','backend','python','/scripts/a_astra_max_recover_20261101.py','--snapshot'],cwd=ROOT,capture_output=True,text=True,check=True)
    data=json.loads(p.stdout);save(OUT/'read-only-final-snapshot.json',data)
    frozen=read(OUT/'sources.json');byhist={h['history_id']:h for h in frozen['sources']}
    sources=[];items=[];mapping=[];receipts=[]
    for hid,h in byhist.items():
        sid='S'+hashlib.sha256(hid.encode()).hexdigest()[:16]
        sources.append({'source_id':sid,'messages':h['messages'],'candidate_failure_patterns':h['candidate_failure_patterns']})
        for run in [r for r in data['runs'] if r['history_id']==hid]:
            tests={q['test_id']:q for q in run['questions']}
            for a in run['responses']:
                q=tests[a['test_id']];rid=hashlib.sha256(a['response_id'].encode()).hexdigest()[:20]
                items.append({'review_id':rid,'source_id':sid,'dimension':q['dimension'],'question':q['prompt'],'expected_behavior':q['expected_behavior'],'answer':a['response_text'],
                    'question_validity':None,'reference_validity':None,'answer_verdict':None,'safe_but_incomplete':None,'detected_defect_ids':None,'outside_inventory_errors':None,'reason':None})
                mapping.append({'review_id':rid,'history_id':hid,'method':run['method'],'run_id':run['run_id'],'test_id':q['test_id'],'response_id':a['response_id']})
                m=a.get('execution_metadata',{})
                receipts.append({'response_id':a['response_id'],'provider':run['audit']['provider'],'reported_model':m.get('reported_model'),'requested_reasoning_effort':m.get('requested_reasoning_effort'),'request_attempts':m.get('request_attempts'),
                    'requested_output_token_limit':m.get('requested_output_token_limit'),'completion_status':m.get('completion_status'),
                    'record_count':(m.get('memory_input') or {}).get('record_count'),'memory_input':m.get('memory_input'),'input_tokens':m.get('input_tokens'),'output_tokens':m.get('output_tokens'),'reasoning_tokens':m.get('reasoning_tokens'),'reported_cost_usd':m.get('reported_cost_usd')})
    if len({m['review_id'] for m in mapping})!=len(items):raise ValueError('Duplicate answer identity')
    random.Random(20261102).shuffle(items)
    pack={'format':'a-astra-max-independent-ai-review-v2','human_confirmation_pending':True,
        'instructions':['Work independently on sources,questions,references andanswers only. No automated scores,model/method/repetition labels,or otherreviewer judgment.',
            'Judge factual completeness under the question/source-aligned expectedbehavior. Safeclarification can be safe_but_incomplete rather than fullycorrect; distinguish it from false sourceclaims.',
            'Independently check question/reference validity; preserve uncertainty. Correctcurrentvalue need notrepeat oldvalue unless prompt/reference explicitlyrequires it.',
            'Map detected_defect_ids ONLY if the actualanswer exhibits the exactfrozen candidate pattern. A failureoutside inventory must be recorded separately; do not force anygeneric failure into a candidate.'],
        'sources':sources,'items':items}
    save(OUT/'blind-review/material.json',pack)
    for n in (1,2):save(OUT/f'blind-review/reviewer-{n}.blank.json',pack)
    save(OUT/'private-review-key.json',{'mapping':mapping})
    bymethod=dict(Counter(m['method'] for m in mapping))
    summary={'format':'a-astra-max-collection-v2','planned':48,'saved':len(items),'missing':48-len(items),'by_method':bymethod,
        'raw_worker_journals_retained':True,'recovery':'read-onlyDBsnapshot; stdoutserializationerror after paidanswerscommitted; no providerrequestredispatched',
        'human_confirmation_pending':True,'protocol_sha256':sha(OUT/'protocol.json'),'source_snapshot_sha256':sha(OUT/'sources.json')}
    save(OUT/'collection-summary.json',summary)
    allcontrols=all(x['provider']=='openai' and x['reported_model']=='gpt-6-astra' and x['requested_reasoning_effort']=='max' and x['request_attempts']==1 and x['requested_output_token_limit']==8192 and x['completion_status']=='complete' and x['record_count'] in (0,1) for x in receipts)
    usage={k:sum(x.get(k) or 0 for x in receipts) for k in ('input_tokens','output_tokens','reasoning_tokens')}
    save(OUT/'delivery-control-check.json',{'format':'a-astra-max-controls-v2','planned':48,'saved':len(receipts),'all_actual_model_effort_attempt_reader_checks_passed':allcontrols,
        'provider':'openai','model':'gpt-6-astra','reasoning_effort':'max','output_token_limit':8192,'reader':'weak','maximum_sent_records_per_answer':1,'provider_redispatches':0,
        'empty_context_answers':sum(x['record_count']==0 for x in receipts),'empty_context_handling':'The frozen first-hit reader sends no record when no eligible candidate is found; the actual target answer remains included.',
        'same_target_setup_across_methods':True,'source_guard':'No referenceanswers or auditor memoryIDs enter the production target request.','usage_tokens':usage,'actual_billed_cost':'Not supplied by provider; do not infer exactbilling.',
        'receipts':receipts,'raw_journal_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((OUT/'executions').glob('*.json'))}})
    print(json.dumps({'saved':len(items),'missing':48-len(items),'bymethod':bymethod,'model_controls_passed':allcontrols,'blindpack':str(OUT/'blind-review/material.json')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',action='store_true');a=p.parse_args()
    snapshot() if a.snapshot else recover()
