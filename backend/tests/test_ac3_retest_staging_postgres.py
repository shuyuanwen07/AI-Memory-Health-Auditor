"""Disposable named PostgreSQL only. No project database or provider calls."""
import json
import os
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import AuditRunModel, ConversationModel, MemoryModel, TestCaseModel
from app.services.ac3_retest_staging import stage_paired_retest
from app.services.ac3_retest_source_import import import_paired_sources
from app.services.stage_lock import stage_lock_key
from test_ac3_staging_postgres_isolated import isolated_db, URL

pytestmark=pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST')!='yes',reason='Disposable PostgreSQL only')


def inputs(prepared):
    engine,path,_digest,mapping,runs=prepared
    suite=json.loads(path.read_text())['suite']
    questions=[]; histories=[]
    for case in suite['cases']:
        hid=case['history_id'];n=hid[1:];source=case['source_messages'][0]['message_id']
        histories.append({'history_id':hid,'source_messages':case['source_messages'],
            'reviewed_facts':[{'memory_id':f'M{n}','source_message_id':source,'canonical_value':f'Fixture fact {n}'}],
            'reviewed_relationships':[]})
        questions.extend({'history_id':hid,**q,'supporting_memory_ids':[f'M{n}']} for q in case['tests'])
    stage={'histories':histories,'questions':questions}
    frozen={'protocol':{'target':{'provider':'rule_based','model':'fixture','strategy':'weak_first_hit','prompt_template_version':'fixture'}}}
    return engine,mapping,runs,stage,frozen


def stage(db,mapping,runs,prepared,frozen):
    with patch('app.services.ac3_retest_binding.compile_reference_stage',return_value=prepared), \
         patch('app.services.ac3_retest_staging.compile_reference_stage',return_value=prepared):
        return stage_paired_retest(db,frozen,b'',b'',[],{},mapping,runs)


def test_stage_is_atomic_on_postgres(isolated_db):
    engine,mapping,runs,prepared,frozen=inputs(isolated_db)
    def fail(_conn,_cursor,statement,_params,_context,_many):
        if statement.lstrip().upper().startswith('UPDATE AUDIT_RUNS'):
            raise RuntimeError('synthetic interruption')
    event.listen(engine,'before_cursor_execute',fail)
    try:
        with Session(engine) as db:
            with pytest.raises(RuntimeError,match='synthetic interruption'):stage(db,mapping,runs,prepared,frozen)
    finally:event.remove(engine,'before_cursor_execute',fail)
    with Session(engine) as db:
        assert not list(db.scalars(select(TestCaseModel)))
        assert all(row.status=='CREATED' for row in db.scalars(select(AuditRunModel)))
    with Session(engine) as db:
        assert stage(db,mapping,runs,prepared,frozen)['test_count']==32


def test_cross_connection_lock_prevents_partial_stage(isolated_db):
    engine,mapping,runs,prepared,frozen=inputs(isolated_db)
    external=create_engine(URL,isolation_level='AUTOCOMMIT')
    try:
        with external.connect() as locker:
            assert locker.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':stage_lock_key('suite:R3')})
            try:
                with Session(engine) as db:
                    with pytest.raises(HTTPException) as error:stage(db,mapping,runs,prepared,frozen)
                    assert error.value.status_code==409
                with Session(engine) as db:
                    assert not list(db.scalars(select(TestCaseModel)))
            finally:locker.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':stage_lock_key('suite:R3')})
    finally:external.dispose()


def test_paired_preflight_checks_all_staged_questions_and_cross_connection_lock(isolated_db):
    from app.services.ac3_paired_locked_preflight import locked_paired_preflight
    from app.services.ac3_locked_preflight import ac3_sequence_locks
    engine,mapping,runs,prepared,frozen=inputs(isolated_db)
    frozen['protocol']['target']['memory_configuration_sha256']='fixture-settings'
    with Session(engine) as db:
        assert stage(db,mapping,runs,prepared,frozen)['test_count']==32
    def check(db):
        return locked_paired_preflight(db,frozen,b'',b'',[],{},mapping,runs)
    with patch('app.services.ac3_retest_binding.compile_reference_stage',return_value=prepared), \
         patch('app.services.ac3_paired_locked_preflight.compile_reference_stage',return_value=prepared), \
         patch('app.services.ac3_paired_locked_preflight.target_settings_sha256',return_value='fixture-settings'):
        with Session(engine) as db:
            with check(db) as result:
                assert result['history_count']==8 and result['question_count']==32
                assert not result['model_called'] and not result['execution_supported']
            with ac3_sequence_locks(db, runs):
                with check(db) as result:
                    assert result['question_count']==32
        external=create_engine(URL,isolation_level='AUTOCOMMIT')
        try:
            with external.connect() as locker:
                assert locker.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':stage_lock_key('suite:R3')})
                try:
                    with Session(engine) as db:
                        with pytest.raises(HTTPException) as error:
                            with check(db): pass
                        assert error.value.status_code==409
                finally:locker.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':stage_lock_key('suite:R3')})
        finally:external.dispose()


def test_reviewed_source_import_is_atomic_and_idempotent(isolated_db):
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    engine,*_=isolated_db
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    try:
        frozen=helper.freeze()
        def call():return import_paired_sources(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components)
        def fail_memory(_conn,_cursor,statement,_params,_context,_many):
            if statement.lstrip().upper().startswith('INSERT INTO MEMORIES'):
                raise RuntimeError('synthetic insert failure')
        event.listen(engine,'before_cursor_execute',fail_memory)
        try:
            with pytest.raises(RuntimeError,match='synthetic insert failure'):call()
        finally:event.remove(engine,'before_cursor_execute',fail_memory)
        with Session(engine) as db:
            assert len(list(db.scalars(select(ConversationModel))))==8
            assert len(list(db.scalars(select(MemoryModel))))==8
        result=call()
        assert result['status']=='imported' and result['history_count']==30 and not result['model_called']
        assert call()['status']=='already_imported'
        with Session(engine) as db:
            assert len(list(db.scalars(select(ConversationModel))))==38
    finally:helper.doCleanups()


def test_full_paired_preparation_in_postgres(isolated_db):
    import hashlib
    from app.schemas import AuditRun
    from app.services.ac3_controlled_runner import _SETTINGS_FIELDS
    from app.services.ac3_retest_prepare import prepare_paired_retest
    from scripts.ac3_retest_paired_freeze import canonical
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    engine,*_=isolated_db
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    try:
        example=AuditRun(run_id='fixture',conversation_id='fixture',status='CREATED',target_configuration='strong',
            provider='rule_based',model='fixture',temperature=0,random_seed=1,test_budget=4,prompt_template_version='fixture',
            memory_strategy='strong_rule_based',target_memory_profile={'output_token_limit':20},
            target_memory_writer_version='fixture-writer',target_system_adapter_version='fixture-adapter',created_at=datetime.now(timezone.utc))
        setup=example.model_dump(mode='json',include=_SETTINGS_FIELDS)
        helper.cfg['target'].update(provider='rule_based',model='fixture',strategy='strong_rule_based',
            prompt_template_version='fixture',memory_configuration_sha256=hashlib.sha256(canonical(setup)).hexdigest())
        frozen=helper.freeze()
        result=prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,setup)
        assert result['history_count']==30 and result['test_count']==120
        assert not result['execution_supported'] and not result['model_called']
        repeated=prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,setup)
        assert repeated['source_status']=='already_imported' and repeated['staging_status']=='already_quarantined'
        with Session(engine) as db:
            assert len(list(db.scalars(select(TestCaseModel))))==120
            audits=list(db.scalars(select(AuditRunModel)))
            assert sum(row.status=='RESEARCH_STAGED' for row in audits)==30
            assert sum(row.status=='CREATED' for row in audits)==8
    finally:helper.doCleanups()
