"""Source-frozen three-method A replay using OpenAI GPT-6 Astra max.

The48questions and inventories are the exact previously user-approved v7
release. All three generators were deterministic; no model generation is
relabeled. New target answers remain AI/human-review pending.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/a-astra-max-retest-20261101-v2'
OLD=ROOT/'output/experiment-a-expanded-20261030'
ROLE='a_astra_max_target_retest_v2'
METHODS=['Direct questions','Fixed templates','Contextual/indirect Auditor tests']

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v,exclusive=False):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    if exclusive:
        with p.open('x') as f: json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
    else:
        t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def signature(q): return (q['dimension'],q['prompt'],q['expected_behavior'],tuple(sorted(q['supporting_memory_ids'])))
def docker(*args,timeout=1800):
    p=subprocess.run(['docker','compose','exec','-T','backend','python','/scripts/a_astra_max_retest_20261101.py',*args],cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError('Container worker failed without redispatch: '+p.stderr[-500:])
    return json.loads(p.stdout)

def snapshot():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,ExperimentModel,TestCaseModel,MessageModel
    from app.api.routes import audit_schema,public_test_schema
    ledger=read(OLD/'four-scenario-v7-question-ledger.json')
    frozen=read(OLD/'four-scenario-frozen-input.json')
    confirmation=read(OLD/'four-scenario-v7-user-confirmation.json')
    if confirmation.get('question_ledger_sha256')!=sha(OLD/'four-scenario-v7-question-ledger.json') or confirmation.get('questions_confirmed') is not True:
        raise ValueError('The original48-question release is not explicitly confirmed')
    sources=[]
    with SessionLocal() as db:
        for hid,h in ledger['histories'].items():
            source=next(x for x in frozen['histories'] if x['history_id']==hid)
            conditions=[]
            for fixture in h['suites']:
                audit=db.get(AuditRunModel,fixture['run_id'])
                if not audit or audit.status!='COMPLETED':raise ValueError('Missing completed prior condition')
                tests=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==audit.id)).all())
                public=[public_test_schema(t).model_dump(mode='json') for t in tests]
                if len(tests)!=4 or sorted(map(signature,public))!=sorted(map(signature,fixture['tests'])):raise ValueError('Original question fixture changed')
                if any(t.human_validity_status!='accepted' for t in tests):raise ValueError('Prior questions lack recorded user acceptance')
                group=db.get(ExperimentModel,audit.experiment_id)
                if not group or not (group.test_suite_metadata or {}).get('failure_inventory'):raise ValueError('Original frozen inventory missing')
                conf=audit_schema(audit).model_dump(mode='json')
                if conf['pipeline_provider']!='rule_based' or conf['semantic_review_provider']!='rule_based':raise ValueError('Unexpected model-backed generator; source audit first')
                if any(t.generator_version not in {'direct-ground-truth-v13','human-reviewed-fixed-template-v1','contextual-indirect-auditor-v13'} for t in tests):raise ValueError('Unexpected generator implementation')
                conditions.append({'method':fixture['method'],'source_run_id':audit.id,'source_configuration':conf,
                    'questions':public,'original_inventory':group.test_suite_metadata['failure_inventory']})
            ids={m['message_id'] for m in source['messages']}
            live=list(db.scalars(select(MessageModel).where(MessageModel.conversation_id==audit.conversation_id)).all())
            if {m.source_message_id:m.content for m in live}!={m['message_id']:m['content'] for m in source['messages']}:raise ValueError('Source messages differ from approved fixture')
            sources.append({'history_id':hid,'domain':source['domain'],'messages':source['messages'],
                'candidate_failure_patterns':source['candidate_failure_patterns'],'conditions':conditions})
    print(json.dumps({'sources':sources,'original_question_confirmation':confirmation},ensure_ascii=False))

def prepare():
    if OUT.exists():raise ValueError('Existing retest folder retained')
    material=docker('--snapshot')
    if len(material['sources'])!=4 or sum(len(c['questions']) for h in material['sources'] for c in h['conditions'])!=48:raise ValueError('Need4histories×3methods×4questions')
    OUT.mkdir(parents=True)
    save(OUT/'sources.json',material,True)
    plan={'format':'a-astra-max-three-method-retest-v2','frozen_at_utc':now(),
        'source_snapshot_sha256':sha(OUT/'sources.json'),'prior_files_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [OLD/'four-scenario-frozen-input.json',OLD/'four-scenario-v7-question-ledger.json',OLD/'four-scenario-v7-user-confirmation.json']},
        'provider':'openai','model':'gpt-6-astra','requested_reasoning_effort':'max','reader':'weak','memory_strategy':'weak_first_hit','writer':'rule_based',
        'output_token_limit':8192,'max_retrieved_records':50,'context_character_budget':16000,'memory_capacity':50,
        'histories':4,'methods':METHODS,'questions_per_method_per_history':4,'planned_answers_per_method':16,'planned_answers':48,'repetitions':1,
        'generator_provenance':'All48questions are exactpreviouslyuserapproved deterministic direct/fixed/contextual rule releases; no model generation was used in their construction.',
        'provider_attempt_limit':1,'provider_timeout_seconds':300,
        'source_review_scope':'Source/question acceptance inherited only for identical frozen prior release. New answers are AI-review and human-confirmation pending.',
        'primary_metrics':['strictsourcegroundedanswerpass','unique frozen candidate defects exposed per method','outofinventoryfailures separately'],
        'limitations':['Four purposely authored scenarios,not a random population sample.','One repetition per method; does not estimate run stability.','Target changes Luna toAstra and outputbudget1024to8192; no isolated model causal comparison.','Candidate defects are potential failures,not proof they occurred; do not force every incorrect or incomplete answer into a frozen candidate.'],
        'app_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))},'script_sha256':sha(__file__)}
    save(OUT/'protocol.json',plan,True)
    print(json.dumps({'frozen_protocol':str(OUT/'protocol.json'),'sha256':sha(OUT/'protocol.json'),'planned_answers':48,'paid_calls':0}))

def register():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,ExperimentModel,TestCaseModel
    from app.api.routes import audit_schema,audit_run_lock
    from app.api.quality_routes import fork_conditions
    plan=read(OUT/'protocol.json');material=read(OUT/'sources.json')
    if sha(OUT/'sources.json')!=plan['source_snapshot_sha256']:raise ValueError('Sources changed')
    regs=[]
    with SessionLocal() as db,audit_run_lock(ROLE,db=db):
        if any((x.test_suite_metadata or {}).get('study_role')==ROLE for x in db.scalars(select(ExperimentModel)).all()):raise ValueError('Prior registration exists; do not duplicate')
        for hi,h in enumerate(material['sources']):
            order=METHODS[hi%3:]+METHODS[:hi%3]
            for method in order:
                old=next(c for c in h['conditions'] if c['method']==method)
                source=db.get(AuditRunModel,old['source_run_id'])
                original=audit_schema(source)
                tests=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==source.id)).all())
                if sorted(signature({'dimension':t.dimension,'prompt':t.prompt,'expected_behavior':t.expected_behavior,'supporting_memory_ids':t.supporting_memory_ids}) for t in tests)!=sorted(map(signature,old['questions'])):raise ValueError('Livequestions changed')
                profile=original.target_memory_profile.model_copy(update={'label':f'Astra A {h["history_id"]} {method}', 'output_token_limit':8192,'max_retrieved_records':50,'context_character_budget':16000})
                package=fork_conditions(source,db,[profile],role=ROLE,note='Exactpriorapprovedquestions/inventory; only new AstraMAXtargetanswers. No new human answer labels.',same_suite=True,target_provider='openai',target_model='gpt-6-astra',target_evaluator_provider='rule_based',target_evaluator_model='rule-based-v66',preserve_target_configuration=True,commit=False)
                run=db.get(AuditRunModel,package['runs'][0]['run_id'])
                copies=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run.id)).all())
                by_sig={signature({'dimension':t.dimension,'prompt':t.prompt,'expected_behavior':t.expected_behavior,'supporting_memory_ids':t.supporting_memory_ids}):t for t in tests}
                for c in copies:
                    t=by_sig[signature({'dimension':c.dimension,'prompt':c.prompt,'expected_behavior':c.expected_behavior,'supporting_memory_ids':c.supporting_memory_ids})]
                    c.human_validity_status=t.human_validity_status;c.human_validity_reviewer=t.human_validity_reviewer;c.human_validity_note=t.human_validity_note;c.human_validity_reviewed_at=t.human_validity_reviewed_at
                run.reproducibility_metadata={**run.reproducibility_metadata,'a_method':method,'a_scenario_id':h['history_id'],'a_protocol_sha256':sha(OUT/'protocol.json'),'human_validation':'pending','inherited_exact_question_release_sha256':sha(OLD/'four-scenario-v7-question-ledger.json'),'execution_budget':{'max_target_calls':4,'max_execution_seconds':1400},'target_retry_policy':{'max_attempts':1,'timeout_seconds':300}}
                regs.append({'history_id':h['history_id'],'method':method,'source_run_id':source.id,'run_id':run.id,'experiment_id':package['experiment_id']})
        db.commit()
    print(json.dumps({'protocol_sha256':sha(OUT/'protocol.json'),'registrations':regs},ensure_ascii=False))

def check():
    p=read(OUT/'protocol.json')
    if sha(OUT/'sources.json')!=p['source_snapshot_sha256'] or sha(__file__)!=p['script_sha256']:raise ValueError('Frozen script or source changed')
    if any(sha(ROOT/path)!=value for path,value in p['app_sha256'].items()):raise ValueError('Backend implementation changed')
    return p

def worker(rid):
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,TestCaseModel,TargetResponseModel
    from app.api.routes import execute,public_test_schema,response_schema,target_memory_trace_payload,audit_schema
    from app.target_ai import providers
    from sqlalchemy import select
    providers._REQUEST_TIMEOUT_SECONDS=300.0
    result={'run_id':rid,'state':'dispatched'}
    with SessionLocal() as db:
        try:
            check()
            with providers.single_attempt_target_request():answers=execute(rid,db)
            result.update(state='returned',response=[r.model_dump(mode='json') for r in answers])
        except Exception as error:
            result.update(state='failed_without_retry',error_type=type(error).__name__,status=getattr(error,'status_code',None),error=str(getattr(error,'detail',''))[:350])
        audit=db.get(AuditRunModel,rid)
        result['audit']=audit_schema(audit).model_dump(mode='json')
        result['questions']=[public_test_schema(q).model_dump(mode='json') for q in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==rid)).all()]
        result['saved_responses']=[response_schema(a).model_dump(mode='json') for a in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==rid)).all()]
        result['trace']=target_memory_trace_payload(audit,db)
    print(json.dumps(result,ensure_ascii=False),flush=True)

def collect():
    check();reg=read(OUT/'registrations.json');histories=[h['history_id'] for h in read(OUT/'sources.json')['sources']]
    def one_history(hid):
        for row in [r for r in reg['registrations'] if r['history_id']==hid]:
            path=OUT/'executions'/f"{hid}-{METHODS.index(row['method'])+1}.json"
            if path.exists():continue
            state={**row,'state':'dispatched','started_at_utc':now()};save(path,state,True)
            try:
                check();result=docker('--worker',row['run_id'],timeout=1600)
                answers=result.get('saved_responses',[])
                if len(answers)==4:
                    for a in answers:
                        m=a['execution_metadata']
                        if m.get('reported_model')!='gpt-6-astra' or m.get('requested_reasoning_effort')!='max' or m.get('request_attempts')!=1:raise ValueError('Model or attemptreceiptmismatch')
                state.update(state='completed_ai_review_pending' if len(answers)==4 else 'partial_without_retry',result=result)
            except Exception as e:state.update(state='ambiguous_without_retry',error_type=type(e).__name__)
            state['completed_at_utc']=now();save(path,state)
            print(json.dumps({'history':hid,'method':row['method'],'state':state['state'],'answers':len(state.get('result',{}).get('saved_responses',[]))}),flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(one_history,histories))
    prepare_reviews()

def prepare_reviews():
    material=read(OUT/'sources.json');items=[];mapping=[];sources=[]
    for h in material['sources']:
        sid='S'+hashlib.sha256(h['history_id'].encode()).hexdigest()[:16]
        sources.append({'source_id':sid,'messages':h['messages'],'candidate_failure_patterns':h['candidate_failure_patterns']})
        for path in sorted((OUT/'executions').glob(h['history_id']+'-*.json')):
            run=read(path);result=run.get('result',{});tests={q['test_id']:q for q in result.get('questions',[])}
            for answer in result.get('saved_responses',[]):
                q=tests[answer['test_id']];rid=hashlib.sha256(answer['response_id'].encode()).hexdigest()[:20]
                items.append({'review_id':rid,'source_id':sid,'dimension':q['dimension'],'question':q['prompt'],'expected_behavior':q['expected_behavior'],'answer':answer['response_text'],'question_validity':None,'reference_validity':None,'answer_verdict':None,'safe_but_incomplete':None,'detected_defect_ids':None,'outside_inventory_errors':None,'reason':None})
                mapping.append({'review_id':rid,'history_id':h['history_id'],'method':run['method'],'run_id':run['run_id'],'test_id':q['test_id'],'response_id':answer['response_id']})
    random.Random(20261102).shuffle(items)
    pack={'format':'a-astra-max-independent-ai-review-v2','human_confirmation_pending':True,
        'instructions':['Review onlysources andquestion/expectedbehavior/answer. Do not see automatic scores,model,methodidentity or another reviewer.','Apply expectedbehavior with source-aligned factualrequirements; safeabstention alone may be incomplete. Preserve source/question/reference ambiguity.','Map defects ONLY when the actualanswer exhibits the exactpre-frozenpattern. Candidates are potentialproblems,not proof. Record other errors separately.'],
        'sources':sources,'items':items}
    save(OUT/'blind-review/material.json',pack)
    for n in (1,2):save(OUT/f'blind-review/reviewer-{n}.blank.json',pack)
    save(OUT/'private-review-key.json',{'mapping':mapping})
    counts={m:sum(x['method']==m for x in mapping) for m in METHODS}
    save(OUT/'collection-summary.json',{'planned':48,'saved':len(items),'missing':48-len(items),'by_method':counts,'score_status':'two_independent_AI_reviews_then_human_confirmation_pending','protocol_sha256':sha(OUT/'protocol.json')})
    print(json.dumps({'saved':len(items),'by_method':counts,'blind_material':str(OUT/'blind-review/material.json')}))

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--snapshot',action='store_true');g.add_argument('--prepare',action='store_true');g.add_argument('--register',action='store_true');g.add_argument('--execute',action='store_true');g.add_argument('--prepare-reviews',action='store_true');g.add_argument('--worker')
    args=p.parse_args()
    if args.snapshot:snapshot()
    elif args.prepare:prepare()
    elif args.register:register()
    elif args.worker:worker(args.worker)
    elif args.execute:collect()
    else:prepare_reviews()
if __name__=='__main__':main()
