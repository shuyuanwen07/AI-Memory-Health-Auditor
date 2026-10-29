"""Synthetic read-only checks; no human review or real database is implied."""
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TestCaseModel
from app.models.entities import Base
from app.services.ac3_retest_binding import verify_database_binding


@pytest.fixture
def fixture():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ConversationModel(id='c',authorised=True,source_origin='synthetic'))
        db.add(MessageModel(id='m',conversation_id='c',source_message_id='s',sequence=0,role='user',content='Tuesday',timestamp=datetime.now(timezone.utc)))
        db.add_all([MemoryModel(id='f1',conversation_id='c',status='confirmed',canonical_value='Tuesday',source_message_ids=['s']),
                    MemoryModel(id='f2',conversation_id='c',status='confirmed',canonical_value='Wednesday',source_message_ids=['s'])])
        db.add(MemoryRelationshipModel(id='e',memory_id='f2',target_memory_id='f1',relationship_type='UPDATE',evidence_message_ids=['s']))
        db.commit()
        stage={'histories':[{'history_id':'h','source_messages':[{'message_id':'s','order':1,'role':'user','text':'Tuesday'}],
            'reviewed_facts':[{'memory_id':'f1','source_message_id':'s','canonical_value':'Tuesday'},
                              {'memory_id':'f2','source_message_id':'s','canonical_value':'Wednesday'}],
            'reviewed_relationships':[{'memory_id':'f2','target_memory_id':'f1','relationship_type':'UPDATE','evidence_message_ids':['s']}]}],
            'questions':[{'test_id':'q'}]}
        yield db,stage
    engine.dispose()


def call(db,stage):
    with patch('app.services.ac3_retest_binding.compile_reference_stage',return_value=stage):
        return verify_database_binding(db,{},b'',b'',[],{}, {'h':'c'})


def test_matching_reference_is_read_only(fixture):
    db,stage=fixture
    result=call(db,stage)
    assert result['history_count']==result['question_count']==1
    assert not result['database_written'] and not result['execution_supported']
    assert not db.new and not db.dirty and not db.deleted


def test_changed_reference_and_relation_are_rejected(fixture):
    db,stage=fixture
    db.get(MemoryModel,'f1').canonical_value='wrong';db.commit()
    with pytest.raises(ValueError,match='memory differs'):call(db,stage)
    db.get(MemoryModel,'f1').canonical_value='Tuesday'
    db.get(MemoryRelationshipModel,'e').relationship_type='CONFLICT';db.commit()
    with pytest.raises(ValueError,match='relationships differ'):call(db,stage)


def test_pending_changes_rejected(fixture):
    db,stage=fixture
    db.get(MessageModel,'m').content='uncommitted'
    with pytest.raises(ValueError,match='clean read-only'):call(db,stage)


def test_quarantine_stages_matching_audit_and_verifies_repeat(fixture):
    from app.services.ac3_retest_staging import stage_paired_retest
    from app.services.runtime_freeze import assert_audit_runtime_frozen
    from app.services.audit_execution import AuditExecutionService
    from app.api.routes import audit_schema
    from fastapi import HTTPException
    db,stage=fixture
    db.add(AuditRunModel(id='r',conversation_id='c',status='CREATED',target_configuration='strong',
        provider='rule_based',model='fixture',temperature=0,random_seed=0,test_budget=1,
        prompt_template_version='fixture',memory_strategy='strong_rule_based'))
    db.commit()
    stage['questions']=[{'history_id':'h','test_id':'q','dimension':'accuracy','question':'Which day?',
                         'expected_behavior':'Tuesday','supporting_memory_ids':['f1']}]
    frozen={'protocol':{'target':{'provider':'rule_based','model':'fixture',
                                  'strategy':'strong_rule_based','prompt_template_version':'fixture'}}}
    with patch('app.services.ac3_retest_staging.verify_database_binding'), \
         patch('app.services.ac3_retest_staging.compile_reference_stage',return_value=stage):
        result=stage_paired_retest(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})
        assert result['test_count']==1 and not result['execution_supported'] and not result['model_called']
        saved=db.get(AuditRunModel,'r')
        assert saved.status=='RESEARCH_STAGED'
        assert audit_schema(saved).reproducibility.ac3_paired_retest['execution_supported'] is False
        saved.status='TESTS_GENERATED'
        with pytest.raises(HTTPException,match='staged only'):assert_audit_runtime_frozen(saved)
        blocked=AuditExecutionService.plan_for(__import__('types').SimpleNamespace(audit=audit_schema(saved)))
        assert blocked.next_stage is None and not blocked.retryable
        saved.status='RESEARCH_STAGED'
        assert db.query(TestCaseModel).count()==1
        db.rollback()
        repeated=stage_paired_retest(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})
        assert repeated['status']=='already_quarantined'
        row=db.query(TestCaseModel).one();row.prompt='changed';db.commit()
        with pytest.raises(ValueError,match='differs'):
            stage_paired_retest(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})


def test_quarantine_rolls_back_when_status_update_fails(fixture):
    from app.services.ac3_retest_staging import stage_paired_retest
    db,stage=fixture
    db.add(AuditRunModel(id='r',conversation_id='c',status='CREATED',target_configuration='strong',
        provider='rule_based',model='fixture',temperature=0,random_seed=0,test_budget=1,
        prompt_template_version='fixture',memory_strategy='strong_rule_based'))
    db.commit()
    stage['questions']=[{'history_id':'h','test_id':'q','dimension':'accuracy','question':'Which day?',
                         'expected_behavior':'Tuesday','supporting_memory_ids':['f1']}]
    frozen={'protocol':{'target':{'provider':'rule_based','model':'fixture',
                                  'strategy':'strong_rule_based','prompt_template_version':'fixture'}}}
    def fail_status(_conn,_cursor,statement,_params,_context,_many):
        if statement.lstrip().upper().startswith('UPDATE AUDIT_RUNS'):
            raise RuntimeError('synthetic interruption')
    engine=db.get_bind()
    event.listen(engine,'before_cursor_execute',fail_status)
    try:
        with patch('app.services.ac3_retest_staging.verify_database_binding'), \
             patch('app.services.ac3_retest_staging.compile_reference_stage',return_value=stage):
            with pytest.raises(RuntimeError,match='synthetic interruption'):
                stage_paired_retest(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})
    finally:
        event.remove(engine,'before_cursor_execute',fail_status)
    assert db.query(TestCaseModel).count()==0
    assert db.get(AuditRunModel,'r').status=='CREATED'


def test_paired_locked_preflight_rejects_changed_source_question_and_configuration(fixture):
    from app.services.ac3_retest_staging import stage_paired_retest
    from app.services.ac3_paired_locked_preflight import locked_paired_preflight
    from app.services.ac3_locked_preflight import ac3_sequence_locks
    db, stage = fixture
    db.add(AuditRunModel(id='r',conversation_id='c',status='CREATED',target_configuration='strong',
        provider='rule_based',model='fixture',temperature=0,random_seed=0,test_budget=1,
        prompt_template_version='fixture',memory_strategy='strong_rule_based'))
    db.commit()
    stage['questions']=[{'history_id':'h','test_id':'q','dimension':'accuracy','question':'Which day?',
                         'expected_behavior':'Tuesday','supporting_memory_ids':['f1']}]
    frozen={'protocol':{'target':{'provider':'rule_based','model':'fixture', 'strategy':'strong_rule_based',
        'prompt_template_version':'fixture', 'memory_configuration_sha256':'expected'}}}
    with patch('app.services.ac3_retest_staging.verify_database_binding'), \
         patch('app.services.ac3_retest_staging.compile_reference_stage',return_value=stage), \
         patch('app.services.ac3_retest_binding.compile_reference_stage',return_value=stage), \
         patch('app.services.ac3_paired_locked_preflight.compile_reference_stage',return_value=stage), \
         patch('app.services.ac3_paired_locked_preflight.target_settings_sha256',return_value='expected') as fingerprint:
        stage_paired_retest(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})
        def check():
            return locked_paired_preflight(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})
        with check() as result:
            assert result['question_count']==1 and not result['execution_supported']
        with ac3_sequence_locks(db, {'h':'r'}):
            with check() as result:
                assert result['history_count']==1
        fingerprint.return_value='changed'
        with pytest.raises(ValueError,match='configuration'):
            with check(): pass
        fingerprint.return_value='expected'
        message=db.get(MessageModel,'m');message.content='changed';db.commit()
        with pytest.raises(ValueError,match='source message differs'):
            with check(): pass
        message=db.get(MessageModel,'m');message.content='Tuesday';db.commit()
        question=db.query(TestCaseModel).one();question.prompt='changed';db.commit()
        with pytest.raises(ValueError,match='differs'):
            with check(): pass


def test_full_synthetic_freeze_maps_all_histories_and_questions():
    # All review declarations here are explicit fixtures from the existing
    # synthetic test helper, not statements about actual human reviewers.
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    helper=PairFreezeTests('test_end_to_end_isolated')
    helper.setUp()
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    try:
        frozen=helper.freeze()
        mapping={}
        with Session(engine) as db:
            for idx,case in enumerate(frozen['suite']['cases']):
                hid=case['history_id'];cid=f'fixture-{idx}';mapping[hid]=cid
                db.add(ConversationModel(id=cid,authorised=True,source_origin='synthetic'))
                for n,msg in enumerate(case['source_messages']):
                    db.add(MessageModel(id=f'msg-{idx}-{n}',conversation_id=cid,source_message_id=msg['message_id'],
                        sequence=n,role=msg['role'],content=msg['text'],timestamp=datetime.now(timezone.utc)))
                reference=frozen['reviewed_fact_plan']['histories'][hid]
                for fact in reference['facts']:
                    db.add(MemoryModel(id=fact['memory_id'],conversation_id=cid,status='confirmed',
                        canonical_value=fact['canonical_value'],source_message_ids=[fact['source_message_id']]))
                for n,edge in enumerate(reference['relationships']):
                    db.add(MemoryRelationshipModel(id=f'edge-{idx}-{n}',memory_id=edge['memory_id'],
                        target_memory_id=edge['target_memory_id'],relationship_type=edge['relationship_type'],
                        evidence_message_ids=edge['evidence_message_ids']))
            db.commit()
            outcome=verify_database_binding(db,frozen,helper.source,helper.plan,helper.reviews,helper.components,mapping)
            assert outcome['history_count']==30 and outcome['question_count']==120
            assert not outcome['execution_supported'] and not outcome['model_called']
    finally:
        engine.dispose()
        helper.doCleanups()


def test_source_import_is_idempotent_and_rejects_changed_records():
    from app.services.ac3_retest_source_import import import_paired_sources
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    try:
        frozen=helper.freeze()
        def run():return import_paired_sources(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components)
        first=run()
        assert first['status']=='imported' and first['history_count']==30 and not first['model_called']
        assert run()['status']=='already_imported'
        with Session(engine) as db:
            memory=db.query(MemoryModel).first();memory.canonical_value='tampered';db.commit()
        with pytest.raises(ValueError,match='Saved memory differs'):
            run()
    finally:
        engine.dispose();helper.doCleanups()


def test_complete_paired_preparation_is_quarantined():
    import hashlib
    from app.schemas import AuditRun
    from app.services.ac3_controlled_runner import _SETTINGS_FIELDS
    from app.services.ac3_retest_prepare import prepare_paired_retest
    from scripts.ac3_retest_paired_freeze import canonical
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    try:
        sample=AuditRun(run_id='r',conversation_id='c',status='CREATED',target_configuration='strong',
            provider='rule_based',model='fixture',temperature=0,random_seed=1,test_budget=4,
            prompt_template_version='fixture',memory_strategy='strong_rule_based',
            target_memory_profile={'output_token_limit':20},target_memory_writer_version='fixture-writer',
            target_system_adapter_version='fixture-adapter',created_at=datetime.now(timezone.utc))
        setup=sample.model_dump(mode='json',include=_SETTINGS_FIELDS)
        helper.cfg['target'].update(provider='rule_based',model='fixture',strategy='strong_rule_based',
            prompt_template_version='fixture',memory_configuration_sha256=hashlib.sha256(canonical(setup)).hexdigest())
        frozen=helper.freeze()
        bad=dict(setup,model='changed')
        with pytest.raises(ValueError,match='fingerprint'):
            prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,bad)
        with Session(engine) as db:assert db.query(ConversationModel).count()==0
        result=prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,setup)
        assert result['history_count']==30 and result['test_count']==120
        assert not result['execution_supported'] and not result['model_called']
        repeated=prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,setup)
        assert repeated['source_status']=='already_imported' and repeated['staging_status']=='already_quarantined'
        with Session(engine) as db:
            assert db.query(TestCaseModel).count()==120
            assert all(r.status=='RESEARCH_STAGED' for r in db.query(AuditRunModel))
    finally:engine.dispose();helper.doCleanups()
