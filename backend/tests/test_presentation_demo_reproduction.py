"""Temp-SQLite and fake-HTTP reproduction guards; never model/network calls.

Previously observed repeat-only gaps have explicit rejection regressions.
All database operations below use temporary synthetic SQLite stores.
"""
import copy
from datetime import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0,str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2]/'scripts'))
from run_presentation_demo import (source_release,suite_fingerprint,pin_repeat_suite,
    recovery_source_guard,recovery_database_guard,API)
from app.database.session import Base
from app.models import (ConversationModel,MessageModel,MemoryModel,ExperimentModel,
    AuditRunModel,TestCaseModel,TargetResponseModel)


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    import httpx
    def blocked(*args,**kwargs):pytest.fail('No HTTP or model request is allowed in reproduction guard tests.')
    monkeypatch.setattr(httpx.Client,'request',blocked)
    monkeypatch.setattr(httpx,'post',blocked)


def audit(rid,experiment,status='CREATED'):
    return AuditRunModel(id=rid,conversation_id='C-DEMO',experiment_id=experiment,status=status,
      target_configuration='strong',provider='openrouter',model='openai/gpt-6-luna',temperature=0,
      random_seed=42,test_budget=8,prompt_template_version='synthetic-v1',reproducibility_metadata={})


def make_case(tid,rid,index):
    return TestCaseModel(id=tid,run_id=rid,dimension=['accuracy','freshness','conflict_resolution','appropriate_use'][index%4],
      prompt='Synthetic question '+str(index),expected_behavior='Synthetic supported answer '+str(index),
      supporting_memory_ids=['M-REF'],generator_version='synthetic-v1')


def snapshot(db,models):
    return {model.__tablename__:[{c.name:getattr(row,c.name) for c in model.__table__.columns}
      for row in db.scalars(select(model).order_by(model.id)).all()] for model in models}


@pytest.fixture
def repeat_db(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'repeat.db'))
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    import app.database.session as sessions
    monkeypatch.setattr(sessions,'SessionLocal',factory)
    from app.api.routes import conversation_schema,memory_schema,public_test_schema
    with factory() as db:
        source=ConversationModel(id='C-DEMO',authorised=True,source_origin='synthetic')
        db.add(source)
        db.add(MessageModel(id='MSG-DB',conversation_id='C-DEMO',source_message_id='DEMO001',sequence=1,
          role='user',content='The object is blue.',timestamp=datetime(2026,2,2,10),original_timestamp='2026-02-02T10:00:00+00:00'))
        memory=MemoryModel(id='M-REF',conversation_id='C-DEMO',canonical_value='The object is blue.',
          status='confirmed',source_message_ids=['DEMO001'],timestamp=datetime(2026,2,2,10));db.add(memory)
        old=ExperimentModel(id='EXP-OLD',conversation_id='C-DEMO',label='Original demonstration',status='COMPLETED',
          test_suite_configuration={},test_suite_metadata={'test_count':8})
        new=ExperimentModel(id='EXP-NEW',conversation_id='C-DEMO',label='New repeated demonstration',status='CREATED',
          test_suite_configuration={},test_suite_metadata={})
        db.add_all([old,new]);db.flush()
        db.add(audit('SOURCE','EXP-OLD','COMPLETED'))
        for i in range(6):db.add(audit('PEER'+str(i),'EXP-NEW'))
        db.flush()
        for i in range(8):db.add(make_case('ORIGINAL'+str(i),'SOURCE',i))
        old.test_suite_source_run_id='SOURCE';db.commit()
        tests=[public_test_schema(t).model_dump(mode='json') for t in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id=='SOURCE')).all()]
        previous={'experiment_id':'EXP-OLD','conversation_id':'C-DEMO',
          'steps':{'import-source':{'body':conversation_schema(db,source).model_dump(mode='json')}},
          'confirmation':{'inventory':[memory_schema(db,memory).model_dump(mode='json')]},
          'frozen_suite':{'source_run_id':'SOURCE','fingerprint':suite_fingerprint(tests),'suite':tests}}
        report={'experiment_id':'EXP-NEW','conversation_id':'C-DEMO','runs':[{'run_id':'PEER'+str(i)} for i in range(6)],
          'repeat_from':{'report_sha256':'a'*64}}
    yield factory,previous,report
    engine.dispose()


def test_exact_original_eight_pin_and_six_private_clones_never_overwrite_old_rows(repeat_db):
    factory,previous,report=repeat_db;before_previous=copy.deepcopy(previous)
    with factory() as db:
        old_suite=[{c.name:getattr(row,c.name) for c in TestCaseModel.__table__.columns}
          for row in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id=='SOURCE').order_by(TestCaseModel.id)).all()]
        source_group=db.get(ExperimentModel,'EXP-OLD')
        old_group={c.name:getattr(source_group,c.name) for c in ExperimentModel.__table__.columns}
    preflight=pin_repeat_suite(report,previous,preflight_only=True)
    assert preflight['status']=='passed' and preflight['database_not_replaced'] is True
    receipt=pin_repeat_suite(report,previous)
    assert receipt['model_generation_calls']==0 and receipt['source_run_id']=='SOURCE'
    from app.api.routes import clone_shared_suite,public_test_schema
    with factory() as db:
        originals=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id=='SOURCE').order_by(TestCaseModel.id)).all()
        for i in range(6):
            copies=clone_shared_suite(db,originals,db.get(AuditRunModel,'PEER'+str(i)))
            assert len(copies)==8
            assert {row.suite_test_id for row in copies}=={row.id for row in originals}
            assert suite_fingerprint([public_test_schema(row).model_dump(mode='json') for row in copies])==previous['frozen_suite']['fingerprint']
        db.commit()
        assert len(db.scalars(select(TestCaseModel)).all())==56
        after=[{c.name:getattr(row,c.name) for c in TestCaseModel.__table__.columns} for row in originals]
        assert after==old_suite
        source_group=db.get(ExperimentModel,'EXP-OLD')
        assert {c.name:getattr(source_group,c.name) for c in ExperimentModel.__table__.columns}==old_group
    assert previous==before_previous


@pytest.mark.parametrize('mutation',['source','ground_truth','suite','missing_slot','extra_slot','different_source'])
def test_repeat_rejects_changed_inputs_or_group_before_pin(repeat_db,mutation):
    factory,previous,report=repeat_db
    with factory() as db:
        if mutation=='source':db.get(MessageModel,'MSG-DB').content='Changed source.'
        if mutation=='ground_truth':db.get(MemoryModel,'M-REF').canonical_value='Changed reference.'
        if mutation=='suite':db.get(TestCaseModel,'ORIGINAL0').expected_behavior='Changed expected behavior.'
        if mutation=='missing_slot':report['runs'].pop()
        if mutation=='extra_slot':db.add(audit('EXTRA','EXP-NEW'))
        if mutation=='different_source':db.get(ExperimentModel,'EXP-NEW').test_suite_source_run_id='PEER0'
        db.commit()
    with pytest.raises(ValueError):pin_repeat_suite(report,previous)
    with factory() as db:assert db.get(ExperimentModel,'EXP-NEW').status=='CREATED'


def test_repeat_wrong_cli_database_rejected(repeat_db,tmp_path,monkeypatch):
    _,previous,report=repeat_db
    engine=create_engine('sqlite:///'+str(tmp_path/'different.db'));Base.metadata.create_all(engine)
    import app.database.session as sessions
    monkeypatch.setattr(sessions,'SessionLocal',sessionmaker(bind=engine))
    try:
        with pytest.raises(ValueError,match='database'):pin_repeat_suite(report,previous,preflight_only=True)
    finally:engine.dispose()


def test_repeat_must_reject_new_group_with_existing_target_response(repeat_db):
    # Preserve the rejecting regression for the previously observed guard gap.
    factory,previous,report=repeat_db
    with factory() as db:
        db.add(make_case('NEW-SAVED-TEST','PEER0',0));db.flush()
        db.add(TargetResponseModel(id='NEW-ANSWER',test_id='NEW-SAVED-TEST',run_id='PEER0',
          response_text='A saved prior target.',model='openai/gpt-6-luna',temperature=0,execution_metadata={}))
        db.get(AuditRunModel,'PEER0').status='COMPLETED';db.commit()
    with pytest.raises(ValueError):pin_repeat_suite(report,previous)


def failed_pre_generation_report():
    rid='OLD0';key='suite-'+rid
    step={'method':'POST','path':'/audits/'+rid+'/generate-tests','status':'failed','status_code':502,
          'body':{'detail':'The configured pipeline model reached its output limit before completing the required result.'}}
    return {'runs':[{'run_id':'OLD'+str(i)} for i in range(6)],'steps':{key:step},'requests':[copy.deepcopy(step)],
            'export_bundle':{'frozen_test_suite':[],'runs':[]}}


def test_recovery_guard_preserves_exact_original_failed_report():
    previous=failed_pre_generation_report();before=copy.deepcopy(previous)
    key,step=recovery_source_guard(previous)
    assert key=='suite-OLD0' and step==before['steps'][key]
    step['body']['detail']='Caller changed only its returned copy.'
    assert previous==before


@pytest.mark.parametrize('mutation',['frozen','tests','responses','evaluations','http_not_truncation','execute_dispatch','recovery_again','multiple_suites','not_six'])
def test_recovery_source_guard_never_retries_saved_answers_or_scores(mutation):
    report=failed_pre_generation_report()
    if mutation=='frozen':report['frozen_suite']={'suite':[{}]}
    if mutation in {'tests','responses','evaluations'}:report['runs'][0][mutation]=[{'saved':True}]
    if mutation=='http_not_truncation':report['steps']['suite-OLD0']['body']={'detail':'Some unrelated rejection.'}
    if mutation=='execute_dispatch':report['requests'].append({'method':'POST','path':'/audits/OLD0/execute'})
    if mutation=='recovery_again':report['generation_recovery']={'already':True}
    if mutation=='multiple_suites':report['steps']['suite-OLD1']=copy.deepcopy(report['steps']['suite-OLD0'])
    if mutation=='not_six':report['runs'].pop()
    with pytest.raises(ValueError):recovery_source_guard(report)


def test_source_release_and_question_fingerprint_are_exact_and_order_independent(tmp_path):
    source={'source_origin':'synthetic','authorised':True,'research_evidence':False,
            'messages':[{'message_id':'D1','role':'user','content':'The object is blue.','timestamp':'2026-02-02T10:00:00Z'}]}
    inventory={'memories':[{'memory_id':'M1','canonical_value':'The object is blue.','source_quote':'The object is blue.',
      'source_message_ids':['D1'],'timestamp':'2026-02-02T10:00:00Z'}],'relationships':[]}
    for name,value in [('conversation',source),('curated-inventory',inventory),('settings',{'test_budget':8,'repetitions':3})]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value))
    values,edges,hashes=source_release(tmp_path)
    assert edges==[] and len(hashes)==3 and values['conversation']==source
    tests=[{'test_id':'T'+str(i),'run_id':'RUN','dimension':'accuracy','prompt':'Q'+str(i),
      'expected_behavior':'A'+str(i),'supporting_memory_ids':['M1'],'generator_version':'v1'} for i in range(8)]
    peers=[{**row,'test_id':'NEW'+str(i),'run_id':'PEER'} for i,row in enumerate(reversed(tests))]
    assert suite_fingerprint(tests)==suite_fingerprint(peers)
    peers[0]['expected_behavior']='Changed exact suite answer.'
    assert suite_fingerprint(tests)!=suite_fingerprint(peers)
    inventory['memories'][0]['source_quote']='Not present in the source.'
    (tmp_path/'curated-inventory.json').write_text(json.dumps(inventory))
    with pytest.raises(ValueError,match='literal'):source_release(tmp_path)


def test_fake_http_journal_failed_step_cannot_be_implicitly_retried(tmp_path):
    class FakeHTTP:
        calls=0
        def request(self,method,path,**kwargs):
            self.calls+=1
            return SimpleNamespace(status_code=502,content=b'failure',headers={'content-type':'application/json'},
              json=lambda:{'detail':'Synthetic output limit.'},text='Synthetic output limit.')
    report={'steps':{},'requests':[]};client=FakeHTTP();api=API(client,report,tmp_path/'report.json')
    with pytest.raises(RuntimeError):api.request('suite-first','POST','/audits/SYN/generate-tests')
    with pytest.raises(RuntimeError):api.request('suite-first','POST','/audits/SYN/generate-tests')
    assert client.calls==1 and len(report['requests'])==1 and report['requests'][0]['status']=='failed'
    assert (tmp_path/'report.json').stat().st_mode & 0o777==0o600


def test_recovery_current_database_rejects_actual_saved_targets(repeat_db,monkeypatch):
    factory,_,_=repeat_db
    report={'experiment_id':'EXP-NEW','conversation_id':'C-DEMO','runs':[{'run_id':'PEER'+str(i)} for i in range(6)]}
    with factory() as db:
        source=db.get(AuditRunModel,'PEER0');source.reproducibility_metadata={'generation_observations':[{'status':'failed'}]}
        db.add(make_case('SAVED-QUESTION','PEER0',0));db.flush()
        db.add(TargetResponseModel(id='SAVED-RESPONSE',test_id='SAVED-QUESTION',run_id='PEER0',
          response_text='A prior response.',model='openai/gpt-6-luna',temperature=0,execution_metadata={}));db.commit()
    with pytest.raises(ValueError,match='tests/responses'):recovery_database_guard(report)


@pytest.mark.parametrize('file_name,hash_key',[('curated-inventory','source_sha256'),('settings','source_sha256'),('settings','curated_inventory_sha256')])
def test_source_release_must_reject_declared_hash_binding_mismatch(tmp_path,file_name,hash_key):
    # Preserve each cross-file binding rejection independently.
    source={'source_origin':'synthetic','authorised':True,'research_evidence':False,
      'messages':[{'message_id':'D1','role':'user','content':'The object is blue.'}]}
    inventory={'memories':[{'memory_id':'M1','canonical_value':'The object is blue.','source_message_ids':['D1']}],
      'relationships':[]}
    settings={'test_budget':8,'repetitions':3}
    payloads={'conversation':source,'curated-inventory':inventory,'settings':settings}
    payloads[file_name][hash_key]='0'*64
    for name,value in payloads.items():(tmp_path/(name+'.json')).write_text(json.dumps(value))
    with pytest.raises(ValueError):source_release(tmp_path)


@pytest.mark.parametrize('state',['TESTS_GENERATED','COMPLETED'])
def test_repeat_rejects_noncreated_peer_even_without_answer(repeat_db,state):
    factory,previous,report=repeat_db
    with factory() as db:
        db.get(AuditRunModel,'PEER0').status=state;db.commit()
    with pytest.raises(ValueError,match='CREATED'):pin_repeat_suite(report,previous)
    with factory() as db:assert db.get(ExperimentModel,'EXP-NEW').test_suite_source_run_id is None


def test_repeat_rejects_saved_test_even_if_peer_status_was_left_created(repeat_db):
    factory,previous,report=repeat_db
    with factory() as db:
        db.add(make_case('SAVED-UNEXECUTED','PEER0',0));db.commit()
    with pytest.raises(ValueError,match='saved tests'):pin_repeat_suite(report,previous)
    with factory() as db:assert db.get(ExperimentModel,'EXP-NEW').status=='CREATED'


def test_source_release_accepts_matching_declared_rawbyte_hashes(tmp_path):
    import hashlib
    source={'source_origin':'synthetic','authorised':True,'research_evidence':False,
      'messages':[{'message_id':'D1','role':'user','content':'The object is blue.'}]}
    source_bytes=json.dumps(source).encode();source_hash=hashlib.sha256(source_bytes).hexdigest()
    inventory={'source_sha256':source_hash,'memories':[{'memory_id':'M1','canonical_value':'The object is blue.',
      'source_message_ids':['D1']}],'relationships':[]}
    inventory_bytes=json.dumps(inventory).encode()
    settings={'test_budget':8,'repetitions':3,'source_sha256':source_hash,
      'curated_inventory_sha256':hashlib.sha256(inventory_bytes).hexdigest()}
    (tmp_path/'conversation.json').write_bytes(source_bytes)
    (tmp_path/'curated-inventory.json').write_bytes(inventory_bytes)
    (tmp_path/'settings.json').write_text(json.dumps(settings))
    _,_,hashes=source_release(tmp_path)
    assert hashes['conversation.json']==source_hash
