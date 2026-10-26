"""Create/resume one visible synthetic demo group through the running API.

Does not replace or clear the service database. Provider keys stay on the server.
A failed first attempt is retained, never automatically retried. Six predeclared
runs reuse one generated suite. --resume only continues never-started steps;
--inspect refreshes saved results without inference. Use verify_presentation_demo
for offline evidence reconstruction. This is engineering demonstration, not gold.
"""
from __future__ import annotations
import argparse
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse
import uuid

MODEL='openai/gpt-6-luna'
DIMENSIONS={'accuracy','freshness','conflict_resolution','appropriate_use'}


def now():return datetime.now(timezone.utc).isoformat()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(value):return hashlib.sha256(value).hexdigest()
def suite_fingerprint(suite):
    fields=('dimension','prompt','expected_behavior','supporting_memory_ids','generator_version','test_type','probe_variant')
    values=[{key:test.get(key) for key in fields} for test in suite]
    return sha(canonical(sorted(values,key=canonical)).encode())


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.demo-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if Path(temp).exists():Path(temp).unlink()


def source_release(directory):
    paths={name:Path(directory)/(name+'.json') for name in ('conversation','curated-inventory','settings')}
    values={name:json.loads(path.read_text()) for name,path in paths.items()}
    source=values['conversation'];inventory=values['curated-inventory'];settings=values['settings']
    actual_hashes={name:sha(path.read_bytes()) for name,path in paths.items()}
    for document,key,expected in ((inventory,'source_sha256',actual_hashes['conversation']),
            (settings,'source_sha256',actual_hashes['conversation']),
            (settings,'curated_inventory_sha256',actual_hashes['curated-inventory'])):
        if key in document and document[key]!=expected:
            raise ValueError('Declared demo release hash differs: '+key)
    if source.get('source_origin')!='synthetic' or source.get('authorised') is not True or source.get('research_evidence') is not False:
        raise ValueError('Only the explicitly authorised synthetic demo release is accepted.')
    messages={message['message_id']:message for message in source['messages']}
    memories={memory['memory_id']:memory for memory in inventory['memories']}
    if len(messages)!=len(source['messages']) or len(memories)!=len(inventory['memories']):raise ValueError('Duplicate source/inventory IDs.')
    for memory in memories.values():
        ids=memory['source_message_ids']
        if not ids or not set(ids)<=set(messages):raise ValueError('Unbound curated memory.')
        quote=memory.get('source_quote',memory['canonical_value'])
        if not any(quote in messages[key]['content'] for key in ids):raise ValueError('Curated source quote is not literal.')
    edges=inventory.get('relationships')
    if edges is None:
        edges=[{'source_memory_id':memory['memory_id'],**edge} for memory in memories.values() for edge in memory.get('relationships',[])]
    for edge in edges:
        if edge['source_memory_id'] not in memories or edge['target_memory_id'] not in memories or not set(edge['evidence_message_ids'])<=set(messages):
            raise ValueError('Unbound curated relationship.')
    if settings.get('test_budget',8)!=8 or settings.get('repetitions',3)!=3:raise ValueError('This demo predeclares six runs and eight questions.')
    return values,edges,{str(path.name):sha(path.read_bytes()) for path in paths.values()}


def normalized_time(value):
    if not value:return value
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def conversation_fingerprint(conversation):
    values=[{**{key:m.get(key) for key in ('message_id','role','content','original_timestamp')},
             'timestamp':normalized_time(m.get('timestamp'))} for m in conversation.get('messages',[])]
    return sha(canonical({'authorised':conversation.get('authorised'),'source_origin':conversation.get('source_origin'),'messages':values}).encode())


def inventory_fingerprint(memories):
    values=[]
    for memory in memories:
        if memory.get('status') not in ('confirmed','edited'):continue
        values.append({key:memory.get(key) for key in ('memory_id','canonical_value','source_message_ids','status')}
                      | {'timestamp':normalized_time(memory.get('timestamp')),'relationships':sorted(memory.get('relationships',[]),key=canonical)})
    return sha(canonical(sorted(values,key=lambda m:m['memory_id'])).encode())


def pin_repeat_suite(report,previous,*,preflight_only=False):
    """Only add a reference to the unchanged original suite in the NEW group.

    This explicit backend-CLI transaction is required because the public API
    correctly freezes membership after generation. Cross-checking API-created
    IDs, full conversation, confirmed inventory and suite refuses a different DB.
    """
    import sys
    backend=Path(__file__).resolve().parents[1]/'backend'
    if Path('/app/app').exists():sys.path.insert(0,'/app')
    elif backend.exists():sys.path.insert(0,str(backend))
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import ExperimentModel,AuditRunModel,ConversationModel,MemoryModel,TestCaseModel,TargetResponseModel
    from app.api.routes import conversation_schema,memory_schema,public_test_schema
    with SessionLocal() as db:
        old=db.get(ExperimentModel,previous['experiment_id']);new=db.get(ExperimentModel,report['experiment_id']) if not preflight_only else None
        cid=previous['conversation_id'];source=previous['frozen_suite']['source_run_id']
        if not old or old.conversation_id!=cid or (not preflight_only and (not new or new.id==old.id or new.conversation_id!=cid)):
            raise ValueError('CLI database does not match the API-created demo groups.')
        current=db.get(ConversationModel,cid)
        actual=conversation_schema(db,current).model_dump(mode='json') if current else {}
        expected=previous['steps']['import-source']['body']
        if conversation_fingerprint(actual)!=conversation_fingerprint(expected):
            raise ValueError('Original demo conversation changed or CLI DB differs.')
        memories=[memory_schema(db,m).model_dump(mode='json') for m in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==cid)).all()]
        if inventory_fingerprint(memories)!=inventory_fingerprint(previous['confirmation']['inventory']):raise ValueError('Confirmed reference inventory changed.')
        originals=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==source)).all()
        tests=[public_test_schema(t).model_dump(mode='json') for t in originals]
        if old.test_suite_source_run_id!=source or suite_fingerprint(tests)!=previous['frozen_suite']['fingerprint']:
            raise ValueError('Original suite changed; no regeneration permitted.')
        if preflight_only:return {'status':'passed','source_experiment_id':old.id,'source_run_id':source,'suite_fingerprint':suite_fingerprint(tests),'database_not_replaced':True}
        members=db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id==new.id)).all()
        if {m.id for m in members}!={r['run_id'] for r in report['runs']} or len(members)!=6:raise ValueError('New demo group membership differs.')
        member_ids=[m.id for m in members]
        if (any(m.status!='CREATED' for m in members)
                or db.scalar(select(TestCaseModel.id).where(TestCaseModel.run_id.in_(member_ids)).limit(1)) is not None
                or db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id.in_(member_ids)).limit(1)) is not None):
            raise ValueError('Repeat suite pin requires six CREATED peers without saved tests or responses.')
        if new.test_suite_source_run_id not in (None,source):raise ValueError('New group already has a different frozen suite.')
        provenance={'source_experiment_id':old.id,'source_run_id':source,'suite_fingerprint':suite_fingerprint(tests),
          'original_question_ids':[t['test_id'] for t in previous['frozen_suite']['suite']],
          'source_report_sha256':report['repeat_from']['report_sha256'],'model_generation_calls':0,
          'database_identity_check':'API IDs + full source + confirmed inventory + original suite matched'}
        new.test_suite_source_run_id=source
        new.test_suite_metadata={**old.test_suite_metadata,'study_role':'presentation_demo_repeat',
          'diagnostic_source_run_id':source,'presentation_repeat_provenance':provenance}
        new.status='TEST_SUITE_GENERATED';db.commit()
        return provenance


def recovery_source_guard(previous):
    """Narrow technical recovery: no saved suite or target execution exists."""
    runs=previous.get('runs',[])
    if len(runs)!=6 or len({r['run_id'] for r in runs})!=6 or previous.get('frozen_suite'):
        raise ValueError('Recovery requires the original six pre-suite runs.')
    if previous.get('generation_recovery') or any(r.get(key) for r in runs for key in ('tests','responses','evaluations')):
        raise ValueError('This recovery cannot repeat recovery or target/question attempts.')
    failed=[(key,value) for key,value in previous['steps'].items() if key.startswith('suite-')]
    if len(failed)!=1:raise ValueError('Exactly one failed initial suite attempt is required.')
    key,step=failed[0]
    if (step.get('status')!='failed' or step.get('status_code')!=502 or step.get('method')!='POST'
            or key!='suite-'+runs[0]['run_id'] or not isinstance(step.get('body'),dict)
            or 'output limit' not in str(step['body'].get('detail','')).lower()):
        raise ValueError('Only the recorded initial HTTP502 output-limit generation failure may recover.')
    if any(row.get('method')=='POST' and row.get('path','').endswith(('/execute','/evaluate')) for row in previous.get('requests',[])):
        raise ValueError('A target or scoring attempt has already been dispatched.')
    bundle=previous.get('export_bundle') or {}
    if bundle.get('frozen_test_suite') or any(run.get('answers') for run in bundle.get('runs',[])):
        raise ValueError('Saved questions/answers prevent technical pre-generation recovery.')
    return key,copy.deepcopy(step)


def recovery_database_guard(report):
    """Read-only current-DB guard supplements API CREATED/empty-tests checks."""
    import sys
    backend=Path(__file__).resolve().parents[1]/'backend'
    if Path('/app/app').exists():sys.path.insert(0,'/app')
    elif backend.exists():sys.path.insert(0,str(backend))
    from sqlalchemy import select,func
    from app.database.session import SessionLocal
    from app.models import ExperimentModel,AuditRunModel,TestCaseModel,TargetResponseModel
    from app.services.runtime_freeze import audit_runtime_signature
    with SessionLocal() as db:
        group=db.get(ExperimentModel,report['experiment_id'])
        members=db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id==report['experiment_id'])).all()
        ids={run['run_id'] for run in report['runs']}
        if (not group or group.conversation_id!=report['conversation_id'] or group.status!='CREATED'
                or group.test_suite_source_run_id is not None or {m.id for m in members}!=ids
                or any(m.status!='CREATED' for m in members)):
            raise ValueError('Existing group is no longer a pre-generation six-run group or CLI DB differs.')
        counts={}
        for model,label in ((TestCaseModel,'tests'),(TargetResponseModel,'responses')):
            counts[label]=db.scalar(select(func.count()).select_from(model).where(model.run_id.in_(ids)))
        if any(counts.values()):raise ValueError('Saved tests/responses prohibit generation recovery.')
        source=db.get(AuditRunModel,report['runs'][0]['run_id'])
        history=(source.reproducibility_metadata or {}).get('generation_observations') or []
        if not history or history[-1].get('status')!='failed':raise ValueError('Current DB lacks the failed unsaved generation observation.')
        current=audit_runtime_signature()
        if current.get('pipeline_output_token_cap')!='8192':raise ValueError('Recovery requires the repaired service budget of8192 in this backend CLI environment.')
        return {'status':'passed','database_read_only':True,'counts':counts,
          'run_ids':sorted(ids),'previous_runtime_signatures':{m.id:(m.reproducibility_metadata or {}).get('audit_runtime_signature') for m in members},
          'current_runtime_signature':current,'last_generation_status':history[-1]['status']}


class API:
    def __init__(self,client,report,path):self.client=client;self.report=report;self.path=path
    def save(self):atomic_json(self.path,self.report)
    def request(self,key,method,path,payload=None,*,optional=False,refresh=False):
        previous=self.report['steps'].get(key)
        if previous and not refresh:
            if previous['status']=='completed':return previous.get('body')
            # A timed-out request may already have committed. Never dispatch an
            # ambiguous model/mutation step again in a resume operation.
            if optional:return None
            raise RuntimeError('Saved first attempt failed or is ambiguous: '+key)
        entry={'key':key,'method':method,'path':path,'started_at':now(),'status':'started'}
        self.report['requests'].append(entry);self.report['steps'][key]=entry;self.save()
        try:
            response=self.client.request(method,'/api/v1'+path,json=payload) if payload is not None else self.client.request(method,'/api/v1'+path)
            kind=response.headers.get('content-type','')
            body=response.json() if response.content and 'json' in kind else response.text
            entry.update(status_code=response.status_code,body=body,
                         status='completed' if response.status_code in (200,201,204) else 'failed')
        except Exception as exc:
            entry.update(status='failed',error_type=type(exc).__name__)
        entry['finished_at']=now();self.save()
        if entry['status']!='completed':
            if optional:return None
            raise RuntimeError('API step did not complete: '+key)
        return entry.get('body')


def authenticate(client,password_env):
    status=client.get('/api/v1/access/status');status.raise_for_status();body=status.json()
    if body.get('requires_sign_in') and not body.get('authenticated'):
        password=os.environ.get(password_env,'') if password_env else ''
        if not password:raise RuntimeError('Workspace sign-in required; provide operator password through --password-env, not a provider API key.')
        response=client.post('/api/v1/access/sign-in',json={'password':password});response.raise_for_status();body=response.json()
    token=body.get('csrf_token')
    if token:client.headers['x-csrf-token']=token
    return {'mode':body.get('mode'),'authenticated':body.get('authenticated',True)}


def collect_run(api,run,*,refresh=False):
    rid=run['run_id']
    for field,suffix in [('configuration',''),('result','/results'),('memory_trace','/target-memory-trace'),
                         ('diagnosis','/diagnosis'),('agents','/agent-executions')]:
        result=api.request('read-'+rid+'-'+field,'GET','/audits/'+rid+suffix,optional=True,refresh=refresh)
        if result is not None:run[field]=result
    api.save()


def export_group(api,directory):
    eid=api.report['experiment_id']
    for field,suffix in [('analytics','/results'),('export_bundle','/reproducibility-bundle.json'),('export_csv','/export.csv')]:
        body=api.request('export-'+field,'GET','/experiments/'+eid+suffix,optional=True,refresh=True)
        if body is not None:api.report[field]=body
    if 'export_bundle' in api.report:atomic_json(directory/'experiment.bundle.json',api.report['export_bundle'])
    if isinstance(api.report.get('export_csv'),str):
        path=directory/'experiment.csv';path.write_text(api.report['export_csv']);path.chmod(0o600)
    api.report['frontend_paths']={'experiment':'/experiments/'+eid,'history':'/history',
      'runs':[{'run_id':r['run_id'],'results':'/audits/'+r['run_id']+'/results'} for r in api.report['runs']]}
    api.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'datasets/demo/presentation-memory-v1')
    parser.add_argument('--output',type=Path,required=True,help='New evidence directory, or existing directory with --resume/--inspect')
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--password-env',help='Optional environment variable containing workspace operator password; never recorded')
    parser.add_argument('--recover-generation-from-report',type=Path,help='One explicit technical budget repair of the known failed unsaved suite; NEW evidence output, same existing group, no target rerun')
    parser.add_argument('--recovery-reason',default='Coverage-planning output budget repaired and pipeline cap raised to8192 before any saved question or target response.')
    parser.add_argument('--repeat-from-report',type=Path,help='New six-run peer group using the saved original suite, no extraction/generation; execute this CLI in the backend DB environment')
    parser.add_argument('--execute',action='store_true',help='Explicitly dispatch actual API mutations/model calls')
    parser.add_argument('--resume',action='store_true',help='Continue only never-started steps in the saved group; no failed-call retry')
    parser.add_argument('--inspect',action='store_true',help='Read saved group/results only; no inference or data edits')
    args=parser.parse_args();parsed=urlparse(args.base_url)
    if parsed.hostname not in {'localhost','127.0.0.1','::1','backend'} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use the existing local service URL without embedded credentials.')
    if args.recover_generation_from_report and (args.resume or args.repeat_from_report or args.inspect):raise ValueError('Generation recovery is separate from resume/repeat/inspect.')
    release,edges,hashes=source_release(args.source)
    directory=args.output.resolve();path=directory/'presentation-demo-report.json'
    if not args.execute and not args.inspect:
        print(canonical({'status':'prepared_not_executed','source_hashes':hashes,'planned_runs':6,'questions_per_run':8,'database':'existing running service, never replaced'}));return 0
    if args.recover_generation_from_report:
        if path.exists() or directory.exists() and any(directory.iterdir()):raise ValueError('Recovery requires a NEW empty evidence directory; original report must remain unchanged.')
        original_path=args.recover_generation_from_report.resolve()
        previous_failed=json.loads(original_path.read_text());failed_key,failed_step=recovery_source_guard(previous_failed)
        if previous_failed.get('source_hashes')!=hashes:raise ValueError('Recovery source/inventory/settings hashes changed.')
        report=copy.deepcopy(previous_failed)
        report['original_failed_steps']={failed_key:failed_step}
        report['generation_recovery']={'original_report_path':str(original_path),'original_report_sha256':sha(original_path.read_bytes()),
          'original_group_id':report['experiment_id'],'permitted_removed_cache_key':failed_key,'reason':args.recovery_reason,
          'requested_at':now(),'target_or_score_retry':False,'new_extraction_calls':0,'new_groups_or_runs':0,'technical_generation_recovery_attempts':1}
        del report['steps'][failed_key]
        report.update(status='recovery_pending_preflight',quality_retries=0)
        report.pop('finished_at',None);report.pop('error_type',None)
        atomic_json(path,report)
    elif path.exists():
        if not (args.resume or args.inspect):raise ValueError('Never overwrite a prior demo attempt; use --resume or --inspect.')
        report=json.loads(path.read_text())
        if report['source_hashes']!=hashes:raise ValueError('Demo release bytes changed; saved group cannot silently adopt new inputs.')
    else:
        if args.resume or args.inspect:raise ValueError('No saved group to resume/inspect.')
        report={'scope':'presentation_synthetic_engineering_demo_not_research_gold','research_evidence':False,
          'database':'existing_running_service_database','database_replaced':False,'existing_data_deleted':False,
          'source_hashes':hashes,'base_url':args.base_url,'request_key':uuid.uuid4().hex,'started_at':now(),
          'status':'running','steps':{},'requests':[],'runs':[],'planned_repetitions_per_strategy':3,
          'planned_questions_per_dimension':2,'quality_retries':0,'new_human_annotation':False}
        atomic_json(path,report)
    previous=json.loads(args.repeat_from_report.read_text()) if args.repeat_from_report else None
    if previous is not None:
        if previous.get('source_hashes')!=hashes or not previous.get('frozen_suite') or not previous.get('confirmation'):raise ValueError('Repeat source/reference/suite release differs or is incomplete.')
        report['repeat_from']={'path':str(args.repeat_from_report.resolve()),'report_sha256':sha(args.repeat_from_report.read_bytes()),
          'experiment_id':previous['experiment_id'],'source_run_id':previous['frozen_suite']['source_run_id']}
        report['new_extraction_calls']=0;report['new_suite_generation_calls']=0
    import httpx
    with httpx.Client(base_url=args.base_url,timeout=900.0) as client:
        api=API(client,report,path)
        try:
            report['access']=authenticate(client,args.password_env);api.save()
            if args.inspect:
                for run in report['runs']:collect_run(api,run,refresh=True)
                if report.get('experiment_id'):export_group(api,directory)
                report['last_inspected_at']=now();api.save();print(canonical({'status':'saved_group_read_only','experiment_id':report.get('experiment_id')}));return 0
            source=release['conversation'];inventory=release['curated-inventory'];settings=release['settings']
            if args.recover_generation_from_report:
                for run in report['runs']:
                    rid=run['run_id']
                    current=api.request('recovery-config-'+rid,'GET','/audits/'+rid,refresh=True)
                    tests=api.request('recovery-empty-tests-'+rid,'GET','/audits/'+rid+'/tests',refresh=True)
                    if current.get('status')!='CREATED' or tests:raise ValueError('API run has saved questions/execution; recovery forbidden.')
                report['generation_recovery']['preflight']=recovery_database_guard(report);api.save()
            if previous is not None:
                cid=previous['conversation_id'];report['conversation_id']=cid
                actual=api.request('repeat-source-check','GET','/conversations/'+cid)
                if conversation_fingerprint(actual)!=conversation_fingerprint(previous['steps']['import-source']['body']):raise ValueError('Saved source conversation changed.')
                memories=api.request('repeat-reference-check','GET','/conversations/'+cid+'/memories')
                if inventory_fingerprint(memories)!=inventory_fingerprint(previous['confirmation']['inventory']):raise ValueError('Saved reference inventory changed.')
                report['repeat_database_preflight']=pin_repeat_suite(report,previous,preflight_only=True)
                report['confirmation']=previous['confirmation']
                report['extraction_provenance']={'reused_from_report_sha256':report['repeat_from']['report_sha256'],'new_extraction_calls':0}
                api.save()
            else:
                conversation=api.request('import-source','POST','/conversations',{'creation_request_key':report['request_key']+'-source',**{k:source[k] for k in ('authorised','source_origin','messages')}})
                cid=conversation['conversation_id'];report['conversation_id']=cid;api.save()
                api.request('extract-first-attempt','POST','/conversations/'+cid+'/extract',{'provider':'openrouter','model':MODEL},optional=True)
                candidates=api.request('extracted-candidates','GET','/conversations/'+cid+'/memories')
                report['extraction_agents']=api.request('extraction-agents','GET','/conversations/'+cid+'/agent-executions')
                selected={};used=set();actions=[]
                for item in inventory['memories']:
                    logical=item['memory_id'];match=next((m for m in candidates if m['memory_id'] not in used and m.get('status')!='rejected'
                        and set(m.get('source_message_ids',[]))==set(item['source_message_ids'])),None)
                    payload={k:item[k] for k in ('canonical_value','source_message_ids','timestamp') if k in item}
                    if match:
                        memory=api.request('curate-'+logical,'PATCH','/memories/'+match['memory_id'],{**payload,'status':'edited','relationships':[]})
                        used.add(match['memory_id']);kind='edit_existing_candidate'
                    else:
                        memory=api.request('curate-'+logical,'POST','/memories',{'conversation_id':cid,**payload});kind='add_source_bound_memory'
                    selected[logical]=memory['memory_id'];actions.append({'logical_memory_id':logical,'actual_memory_id':memory['memory_id'],'action':kind})
                for candidate in candidates:
                    if candidate['memory_id'] not in used:api.request('reject-'+candidate['memory_id'],'DELETE','/memories/'+candidate['memory_id'])
                for item in inventory['memories']:
                    relationships=[{'type':edge['type'],'target_memory_id':selected[edge['target_memory_id']],
                      'evidence_message_ids':edge['evidence_message_ids']} for edge in edges if edge['source_memory_id']==item['memory_id']]
                    api.request('relations-'+item['memory_id'],'PATCH','/memories/'+selected[item['memory_id']],{'relationships':relationships})
                confirmed=api.request('confirm-engineering-inventory','POST','/conversations/'+cid+'/confirm-ground-truth',{'confirmed_memory_ids':list(selected.values())})
                report['confirmation']={'kind':'engineering_curated_synthetic_demo_only','independent_human_gold':False,
                  'inventory_mapping':selected,'actions':actions,'inventory':[m for m in confirmed if m['status'] in ('confirmed','edited')]};api.save()
            roles={'pipeline_provider':'openrouter','pipeline_model':MODEL,'semantic_review_provider':'openrouter',
              'semantic_review_model':MODEL,'evaluator_provider':'openrouter','evaluator_model':MODEL}
            experiment=api.request('create-demo-group','POST','/experiments',{'creation_request_key':report['request_key']+'-group',
              'conversation_id':cid,'label':('Presentation demo repeat · ' if previous else '')+settings.get('label','Presentation demo · synthetic · Weak vs Strong · 3 repeats'),
              'test_suite_configuration':{**roles,'test_budget':8,'random_seed':42,'dimensions':sorted(DIMENSIONS)}})
            report['experiment_id']=experiment['experiment_id'];api.save()
            profile={**settings.get('target_memory_profile',{}),'output_token_limit':8192,'reasoning_effort':'medium',
              'max_retrieved_records':100,'context_character_budget':24000,'answer_validation':'off'}
            for repetition in (1,2,3):
                for strategy in ('weak_first_hit','strong_rule_based'):
                    key='create-run-'+str(repetition)+'-'+strategy
                    audit=api.request(key,'POST','/audits',{'creation_request_key':report['request_key']+'-'+str(repetition)+'-'+strategy,
                      'conversation_id':cid,'experiment_id':report['experiment_id'],'target_configuration':'weak' if strategy=='weak_first_hit' else 'strong',
                      'provider':'openrouter','model':MODEL,**roles,'test_budget':8,'random_seed':42,'temperature':0,
                      'memory_strategy':strategy,'memory_maintenance_policy':settings.get('memory_maintenance_policy','update_aware_consolidation'),
                      'target_memory_capacity':100,'target_memory_writer':'rule_based','target_memory_profile':profile,
                      'target_system_adapter':'controlled-memory','retrieval_mode':'fixed'})
                    if not any(r['run_id']==audit['run_id'] for r in report['runs']):report['runs'].append({'strategy':strategy,'repetition':repetition,'run_id':audit['run_id'],'configuration':audit})
                    api.save()
            if previous is not None:
                report['repeat_suite_pin']=pin_repeat_suite(report,previous);api.save()
            for index,run in enumerate(report['runs']):
                rid=run['run_id']
                suite=api.request('suite-'+rid,'POST','/audits/'+rid+'/generate-tests')
                if len(suite)!=8 or Counter(t['dimension'] for t in suite)!=Counter({d:2 for d in DIMENSIONS}):raise ValueError('Generated suite must contain exactly two questions per dimension; original suite retained.')
                fingerprint=suite_fingerprint(suite);run['tests']=suite;run['suite_fingerprint']=fingerprint
                if index==0:report['frozen_suite']={'source_run_id':rid,'original_question_ids':[t['test_id'] for t in suite],
                  'fingerprint':fingerprint,'generator_dispatches':0 if previous else 1,'suite':suite,
                  'original_source_question_ids':previous['frozen_suite']['original_question_ids'] if previous else [t['test_id'] for t in suite]}
                if previous and fingerprint!=previous['frozen_suite']['fingerprint']:raise ValueError('Repeated group did not clone the original suite.')
                elif fingerprint!=report['frozen_suite']['fingerprint']:raise ValueError('Shared suite content changed between conditions.')
                api.save()
                responses=api.request('execute-'+rid,'POST','/audits/'+rid+'/execute',optional=True)
                if responses is not None:
                    run['responses']=responses
                    evaluations=api.request('evaluate-'+rid,'POST','/audits/'+rid+'/evaluate',optional=True)
                    if evaluations is not None:run['evaluations']=evaluations
                collect_run(api,run);api.save()
            export_group(api,directory)
            failures=[row['key'] for row in report['requests'] if row['status']!='completed']
            complete=len(report['runs'])==6 and all(len(run.get('responses',[]))==len(run.get('evaluations',[]))==8 for run in report['runs'])
            recovered=report.get('generation_recovery')
            historical=({recovered['permitted_removed_cache_key']} if recovered else set())
            current_failures=[key for key in failures if key not in historical]
            report['status']=('completed_after_generation_recovery' if recovered else 'completed') if complete and not current_failures else 'partial_failure'
            report['core_execution_complete']=complete
            report['preserved_historical_generation_failure']=bool(recovered)
            report['first_attempt_failures']=failures
        except Exception as exc:
            report.update(status='failed',error_type=type(exc).__name__)
            if report.get('experiment_id'):
                try:export_group(api,directory)
                except Exception:pass
        finally:
            report['finished_at']=now();api.save()
    print(canonical({'status':report['status'],'experiment_id':report.get('experiment_id'),'report':str(path)}))
    return 0 if report['status'] in {'completed','completed_after_generation_recovery'} else 1


if __name__=='__main__':raise SystemExit(main())
