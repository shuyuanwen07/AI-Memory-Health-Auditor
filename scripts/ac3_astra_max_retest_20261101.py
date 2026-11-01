"""Frozen source-bound AC3 Astra-max rerun; old data is never relabelled.

Targets use the production route. The candidate retains the source/question/
answer taxonomy rubric but makes one OpenAI Responses request at max effort.
The exact earlier rule-v65 archive is replayed offline on the same new answers.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
REL = Path('output/proposal-delivery/ac3-astra-max-retest-20261101-v2')
OUT = ROOT/REL
OLD = ROOT/'output/ac3-generated/paired-authorized-retest-20261029-v1'
BASELINE = ROOT/'output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6/paired-baseline-shared-environment-candidate.zip'
ROLE = 'ac3_astra_max_retest_v2'
THRESHOLDS = {'failure_detection_recall_min':.8,'failure_classification_accuracy_min':.8,
              'test_validity_min':.9,'false_positive_rate_max':.1}
SCHEMA = {'type':'object','additionalProperties':False,
    'required':['passed','reason','evidence_memory_ids','failure_type','classification_reason'],
    'properties':{'passed':{'type':['boolean','null']},'reason':{'type':'string'},
        'evidence_memory_ids':{'type':'array','items':{'type':'string'}},
        'failure_type':{'type':['string','null'],'enum':['accuracy','freshness','conflict_resolution','appropriate_use',None]},
        'classification_reason':{'type':'string'}}}


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def write(path, obj, exclusive=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if exclusive:
        with path.open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
    else:
        tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


def container(args, timeout=2400):
    return subprocess.run(['docker','compose','exec','-T','backend','python','/scripts/ac3_astra_max_retest_20261101.py',*args],cwd=ROOT,capture_output=True,text=True,timeout=timeout)


def snapshot():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,MessageModel,MemoryModel,TestCaseModel
    from app.api.routes import audit_schema,memory_schema,public_test_schema
    staged=read(OLD/'staged.json');frozen=read(OLD/'frozen-canonical.json')
    expected={h['history_id']:h for h in frozen['suite']['cases']}
    sources=[]
    with SessionLocal() as db:
        for hid,rid in staged['history_runs'].items():
            a=db.get(AuditRunModel,rid)
            if not a or a.conversation_id!=staged['history_conversations'][hid]:raise ValueError('Approved source missing')
            tests=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==rid)).all())
            if len(tests)!=4:raise ValueError('Frozen question count differs')
            qs=[public_test_schema(t).model_dump(mode='json') for t in tests]
            if sorted((q['prompt'],q['expected_behavior'],q['dimension']) for q in qs)!=sorted((q['question'],q['expected_behavior'],q['dimension']) for q in expected[hid]['tests']):raise ValueError('Source question changed')
            msgs=list(db.scalars(select(MessageModel).where(MessageModel.conversation_id==a.conversation_id).order_by(MessageModel.sequence)).all())
            if [(m.source_message_id,m.role,m.content) for m in msgs]!=[(m['message_id'],m['role'],m['text']) for m in expected[hid]['source_messages']]:raise ValueError('Approved source messages changed')
            memories=list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==a.conversation_id)).all())
            sources.append({'history_id':hid,'source_run_id':rid,'audit':audit_schema(a).model_dump(mode='json'),
                'questions':qs,'messages':[{'message_id':m.source_message_id,'role':m.role,'content':m.content,'timestamp':m.observation_timestamp.isoformat()} for m in msgs],
                'confirmed_memories':[memory_schema(db,m).model_dump(mode='json') for m in memories]})
    print(json.dumps({'sources':sources},ensure_ascii=False))


def prepare():
    if OUT.exists():raise ValueError('Existing study is preserved')
    p=container(['--snapshot']);p.check_returncode();sources=json.loads(p.stdout)
    if len(sources['sources'])!=30 or any(len(s['questions'])!=4 for s in sources['sources']):raise ValueError('Expected30sources120questions')
    OUT.mkdir(parents=True);write(OUT/'sources.json',sources,True)
    rubric=(ROOT/'backend/app/evaluator/taxonomy_evaluator.py').read_text()
    protocol={'format':'ac3-astra-max-retest-v2','frozen_at_utc':now(),'provider':'openai','model':'gpt-6-astra','reasoning_effort':'max',
        'source_snapshot_sha256':sha(OUT/'sources.json'),'old_frozen_sha256':sha(OLD/'frozen-canonical.json'),
        'old_baseline_snapshot_sha256':sha(BASELINE),'script_sha256':sha(__file__),
        'old_candidate_model':{'provider':'openrouter','model':'openai/gpt-6-luna'},
        'target':{'target_configuration':'strong','memory_strategy':'strong_rule_based','target_memory_writer':'rule_based',
            'memory_maintenance_policy':'update_aware_consolidation','target_memory_capacity':50,
            'max_retrieved_records':50,'context_character_budget':16000,'output_token_limit':8192,
            'provider_attempts':1,'timeout_seconds':300,'temperature_sent':None,'seed_sent':None},
        'scorer':{'provider':'openai','model':'gpt-6-astra','reasoning_effort':'max','prompt_version':'astra-taxonomy-max-v1',
            'rubric_source_sha256':hashlib.sha256(rubric.encode()).hexdigest(),'schema':SCHEMA,'output_token_limit':8192,'provider_attempts':1,'timeout_seconds':300,
            'provider_only':True,'dimension_label_supplied':False,'expected_behavior_supplied':False,'human_labels_supplied':False},
        'thresholds':THRESHOLDS,'minimum_consensus_pass':30,'minimum_consensus_fail':30,'minimum_auto_coverage':.8,
        'histories':30,'questions':120,'planned_target_calls':120,'planned_scorer_calls':120,'workers':3,
        'app_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))},
        'source_review':'Previously user-confirmed independent source reviews from the archived AC3 cohort; new answer review is pending.',
        'limitations':['Reused related synthetic histories; no unseen-population claim.','Target and candidate judge are Astra max; same-model error correlation remains possible.',
            'New target model and larger output cap differ from the historical Luna run. This is an Astra-specific validation cohort, not isolated model causation.',
            'Independent AI answer reviews are not human reviews; human confirmation stays pending.','Missing/error/uncertain results retained; no outcome-dependent paid retries.']}
    write(OUT/'protocol.json',protocol,True)
    print(json.dumps({'protocol':str(OUT/'protocol.json'),'sha256':sha(OUT/'protocol.json'),'model_calls':0}))


def check():
    p=read(OUT/'protocol.json')
    if sha(__file__)!=p['script_sha256'] or sha(OUT/'sources.json')!=p['source_snapshot_sha256']:raise ValueError('Frozen study implementation/source changed')
    def app_path(k):
        return Path('/app/app')/Path(k).relative_to('backend/app') if ROOT==Path('/') else ROOT/k
    if any(sha(app_path(k))!=v for k,v in p['app_sha256'].items()):raise ValueError('Application changed after freeze')
    return p


def register():
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import AuditRunModel,TestCaseModel
    from app.schemas import AuditCreate
    from app.api.routes import audit_schema,audit_run_lock,build_audit,persist_generated_tests
    check();sources=read(OUT/'sources.json')['sources'];regs=[]
    with SessionLocal() as db,audit_run_lock(ROLE,db=db):
        if any((r.reproducibility_metadata or {}).get('study_role')==ROLE for r in db.scalars(select(AuditRunModel))):raise ValueError('Prior registration exists; inspect it')
        for s in sources:
            source=db.get(AuditRunModel,s['source_run_id']);a=audit_schema(source)
            profile=a.target_memory_profile.model_copy(update={'label':'AC3 Astra max fixed target','output_token_limit':8192,'max_retrieved_records':50,'context_character_budget':16000})
            new=build_audit(AuditCreate(conversation_id=source.conversation_id,target_configuration='strong',provider='openai',model='gpt-6-astra',
                test_budget=4,temperature=a.temperature,random_seed=a.random_seed,prompt_template_version=a.prompt_template_version,
                pipeline_provider='rule_based',pipeline_model='rule-based-v2',evaluator_provider='rule_based',
                memory_strategy='strong_rule_based',memory_maintenance_policy=a.memory_maintenance_policy,target_memory_capacity=50,
                target_memory_writer='rule_based',target_memory_profile=profile),db)
            row=db.get(AuditRunModel,new.run_id)
            originals=list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==source.id).order_by(TestCaseModel.id)).all())
            copies=persist_generated_tests(db,row,originals)
            for old,q in zip(originals,copies,strict=True):
                q.target_memory_context=[];q.comparison_test_id=old.id;q.quality_status='accepted';q.grounding_status='grounded'
                q.human_validity_status='accepted'
                q.human_validity_note='Previously user-confirmed independent source/question approval from the archived frozen AC3 cohort; new answers still require independent review.'
            meta=dict(row.reproducibility_metadata);meta.update(study_role=ROLE,diagnostic_source_run_id=source.id,
                history_id=s['history_id'],protocol_sha256=sha(OUT/'protocol.json'),human_validation='pending',validation_split='reused_source_development_retest')
            row.reproducibility_metadata=meta;row.status='TESTS_GENERATED'
            regs.append({'history_id':s['history_id'],'source_run_id':source.id,'run_id':row.id})
        db.commit()
    print(json.dumps({'registrations':regs,'protocol_sha256':sha(OUT/'protocol.json')}))


def worker(run_id):
    from app.database.session import SessionLocal
    from app.api.routes import execute,target_memory_trace_payload,public_test_schema
    from app.models import AuditRunModel,TestCaseModel,TargetResponseModel
    from sqlalchemy import select
    import app.target_ai.providers as providers
    check();providers._REQUEST_TIMEOUT_SECONDS=300
    with SessionLocal() as db:
        result={'state':'dispatched','run_id':run_id,'started_utc':now()}
        try:
            if list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==run_id))):raise ValueError('Run already has answers')
            with providers.single_attempt_target_request():answers=execute(run_id,db)
            result.update(state='returned',responses=[a.model_dump(mode='json') for a in answers])
        except Exception as exc:
            result.update(state='failed_without_retry',error_type=type(exc).__name__,status=getattr(exc,'status_code',None),
                responses=[{'response_id':a.id,'test_id':a.test_id,'run_id':a.run_id,'response_text':a.response_text,'model':a.model,'temperature':a.temperature,'execution_metadata':a.execution_metadata} for a in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==run_id))])
        row=db.get(AuditRunModel,run_id)
        result['trace']=target_memory_trace_payload(row,db).model_dump(mode='json')
        result['questions']=[public_test_schema(q).model_dump(mode='json') for q in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==run_id))]
        result['completed_utc']=now();print(json.dumps(result,ensure_ascii=False))


def execute():
    check();regs=read(OUT/'registrations.json')['registrations']
    def one(reg):
        path=OUT/'target-responses'/f"{reg['history_id']}.json"
        if path.exists():return {'history_id':reg['history_id'],'status':'existing_attempt_not_redispatched'}
        state={**reg,'state':'dispatched','started_utc':now()};write(path,state,True)
        try:
            p=container(['--worker',reg['run_id']],1600)
            raw=OUT/'raw-target'/f"{reg['history_id']}.stdout";raw.parent.mkdir(exist_ok=True);raw.write_text(p.stdout)
            if p.returncode:raise ValueError('Target worker failed; inspect before any later action')
            payload=json.loads(p.stdout)
            for answer in payload.get('responses',[]):
                meter=answer['execution_metadata']
                if meter.get('reported_model')!='gpt-6-astra' or meter.get('requested_reasoning_effort')!='max' or meter.get('request_attempts')!=1:raise ValueError('Target model/effort/attempt receipt mismatch')
            state.update(payload,raw_sha256=sha(raw))
        except Exception as exc:state.update(state='ambiguous_without_retry',error_type=type(exc).__name__)
        write(path,state);print(json.dumps({'history_id':reg['history_id'],'state':state['state'],'answers':len(state.get('responses',[]))}),flush=True)
        return {'history_id':reg['history_id'],'state':state['state'],'answers':len(state.get('responses',[]))}
    with ThreadPoolExecutor(max_workers=3) as pool:summary=list(pool.map(one,regs))
    write(OUT/'target-collection-summary.json',{'planned':120,'saved':sum(x.get('answers',0) for x in summary),'histories':summary,'human_review':'pending'})


def collect_inputs():
    sources={s['history_id']:s for s in read(OUT/'sources.json')['sources']};items=[]
    for path in sorted((OUT/'target-responses').glob('*.json')):
        record=read(path);s=sources[record['history_id']];questions={q['test_id']:q for q in record.get('questions',[])}
        for answer in record.get('responses',[]):
            q=questions[answer['test_id']]
            items.append({'history_id':s['history_id'],'test':q,'response':answer,'memories':s['confirmed_memories']})
    return items


def pack():
    check();items=collect_inputs();sources=read(OUT/'sources.json')['sources']
    rng=random.Random(20261102);rng.shuffle(items)
    history_ids={s['history_id']:'S'+digest(s['messages'])[:16] for s in sources}
    public_sources=[{'source_handle':history_ids[s['history_id']],'messages':s['messages']} for s in sources]
    blank=[];mapping=[]
    for item in items:
        rid=digest({'protocol':sha(OUT/'protocol.json'),'response':item['response']['response_id']})[:20]
        blank.append({'review_id':rid,'source_handle':history_ids[item['history_id']],'question':item['test']['prompt'],
            'reference_behavior':item['test']['expected_behavior'],'answer':item['response']['response_text'],
            'question_validity':None,'verdict':None,'failure_type':None,'reason':None})
        mapping.append({'review_id':rid,'history_id':item['history_id'],'test_id':item['test']['test_id'],'response_id':item['response']['response_id']})
    material={'format':'ac3-astra-compact-blind-v2','reviewer_declaration':{'reviewer_kind':'ai','completed_by_human':False,'human_confirmation_pending':True},
        'instructions':['Use sources to judge question/reference validity and answer correctness separately.','No model,strategy,automatic verdict,otherreview or intended dimension is supplied.',
            'If failing, classify actual observed failure only:accuracy,freshness,conflict_resolution,appropriate_use,or null if ambiguous.','Safe but incomplete clarification is separate from unsupported factual claims.'],
        'sources':public_sources,'items':blank}
    write(OUT/'blind-review/compact-all.json',material)
    write(OUT/'private-review-key.json',{'material_sha256':sha(OUT/'blind-review/compact-all.json'),'mapping':mapping})
    write(OUT/'private-scorer-inputs.json',{'items':items})
    print(json.dumps({'answers':len(blank),'source_count':len(public_sources),'pack':str(OUT/'blind-review/compact-all.json')}))


def judge_worker(test_id):
    import httpx
    from app.evaluator.taxonomy_evaluator import RUBRIC
    from app.evaluator.llm_judge import LLMBehaviourEvaluator
    check();item=next(x for x in read(OUT/'private-scorer-inputs.json')['items'] if x['test']['test_id']==test_id)
    memories=[{'memory_id':m['memory_id'],'canonical_value':m['canonical_value'],'timestamp':m.get('timestamp')} for m in item['memories']]
    prompt='Question: '+item['test']['prompt']+'\nTarget answer: '+item['response']['response_text']+'\nConfirmed memory records: '+json.dumps(memories,ensure_ascii=False)
    payload={'model':'gpt-6-astra','reasoning':{'effort':'max'},'max_output_tokens':8192,'instructions':RUBRIC,'input':prompt,
        'text':{'format':{'type':'json_schema','name':'ac3_taxonomy_judgment','strict':True,'schema':SCHEMA}}}
    result={'state':'dispatched','test_id':test_id,'started_utc':now(),'request_payload_sha256':digest(payload),'provider':'openai','model':'gpt-6-astra','reasoning_effort':'max','output_token_limit':8192,'request_attempts':1}
    try:
        response=httpx.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'},json=payload,timeout=300)
        result['http_status']=response.status_code
        if not response.is_success:raise ValueError('Judge request failed')
        data=response.json()
        text=''.join(p.get('text','') for o in data.get('output',[]) if o.get('type')=='message' for p in o.get('content',[]) if p.get('type')=='output_text')
        judgment=json.loads(text);allowed={m['memory_id'] for m in memories}
        LLMBehaviourEvaluator._validated_result(judgment,allowed)
        if judgment.get('passed') is not None and not judgment.get('evidence_memory_ids'):raise ValueError('A decided verdict must cite supplied evidence')
        if data.get('model')!='gpt-6-astra' or data.get('status')!='completed':raise ValueError('Judge model/completion mismatch')
        result.update(state='returned',judgment=judgment,usage=data.get('usage'),reported_model=data.get('model'),provider_response_id=data.get('id'),completion_status=data.get('status'))
    except Exception as exc:result.update(state='failed_without_retry',error_type=type(exc).__name__)
    result['completed_utc']=now();print(json.dumps(result,ensure_ascii=False))


def score():
    check();items=read(OUT/'private-scorer-inputs.json')['items']
    def one(item):
        tid=item['test']['test_id'];path=OUT/'candidate-scores'/f'{tid}.json'
        if path.exists():return {'test_id':tid,'state':'existing_attempt_not_redispatched'}
        write(path,{'test_id':tid,'state':'dispatched','started_utc':now()},True)
        try:
            p=container(['--judge-worker',tid],420)
            raw=OUT/'raw-scorer'/f'{tid}.stdout';raw.parent.mkdir(exist_ok=True);raw.write_text(p.stdout)
            if p.returncode:raise ValueError('Scorer worker failed')
            result=json.loads(p.stdout);result['raw_sha256']=sha(raw)
        except Exception as exc:result={'test_id':tid,'state':'ambiguous_without_retry','error_type':type(exc).__name__}
        write(path,result);print(json.dumps({'test_id':tid,'state':result['state']}),flush=True)
        return {'test_id':tid,'state':result['state']}
    with ThreadPoolExecutor(max_workers=3) as pool:summary=list(pool.map(one,items))
    write(OUT/'scorer-collection-summary.json',{'planned':len(items),'completed':sum(x['state']=='returned' for x in summary),'items':summary})


def baseline_worker():
    # Fresh process: import only archived evaluator modules ahead of current app.
    folder=Path(tempfile.mkdtemp(prefix='ac3-old-rule-'))
    with ZipFile(BASELINE) as z:z.extractall(folder)
    sys.path.insert(0,str(folder))
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    from app.schemas import TestCase,TargetResponse,Memory
    if RuleBasedBehaviourEvaluator.VERSION!='rule-based-v65':raise ValueError('Wrong prior rule evaluator')
    records=[]
    for item in read(OUT/'private-scorer-inputs.json')['items']:
        q=item['test'];a=item['response']
        test=TestCase(test_id=q['test_id'],run_id=q['run_id'],dimension=q['dimension'],prompt=q['prompt'],expected_behavior=q['expected_behavior'],supporting_memory_ids=q['supporting_memory_ids'],generator_version=q['generator_version'])
        response=TargetResponse(response_id=a['response_id'],test_id=a['test_id'],run_id=a['run_id'],response_text=a['response_text'],model=a['model'],temperature=a['temperature'])
        result=RuleBasedBehaviourEvaluator().evaluate(test,response,[Memory.model_validate(m) for m in item['memories']])
        records.append(result.model_dump(mode='json'))
    print(json.dumps({'evaluator':'rule-based-v65','snapshot_sha256':sha(BASELINE),'items':records},ensure_ascii=False))


def baseline():
    check();p=container(['--baseline-worker']);p.check_returncode();write(OUT/'baseline-scores.json',json.loads(p.stdout));print('Archived rule-v65 baseline replayed offline; no model call.')


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    for flag in ('snapshot','prepare','register','execute','pack','score','baseline','baseline-worker'):m.add_argument('--'+flag,action='store_true')
    m.add_argument('--worker');m.add_argument('--judge-worker');a=p.parse_args()
    if a.snapshot:snapshot()
    elif a.prepare:prepare()
    elif a.register:register()
    elif a.worker:worker(a.worker)
    elif a.execute:execute()
    elif a.pack:pack()
    elif a.judge_worker:judge_worker(a.judge_worker)
    elif a.score:score()
    elif a.baseline_worker:baseline_worker()
    else:baseline()


if __name__=='__main__':main()
