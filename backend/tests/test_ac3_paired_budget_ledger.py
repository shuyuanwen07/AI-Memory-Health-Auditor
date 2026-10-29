"""Synthetic ledger tests only; no provider or real human evidence."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.models import AuditRunModel, ConversationModel, TestCaseModel, TargetResponseModel
from app.models.entities import Base


def evidence(test_id,run_id='r'):
    return {'format':'ac3-private-request-evidence-v1','frozen_test_id':test_id,'run_id':run_id,
            'retrieval_id':'synthetic-retrieval','selected_memory_ids':['f1'],'target_memory_context':['synthetic fact']}


@pytest.fixture
def ledger():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sql=Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text()
    with engine.begin() as conn:
        for statement in sql.split(';'):
            if statement.strip():conn.execute(text(statement))
    instance=PairedBudgetLedger(engine,frozen_path='/tmp/fixture',frozen_sha256='a'*64,source=b'',plan=b'',reviews=[],components={},
                                budget_path='/tmp/budget',budget_sha256='b'*64,billing_path='/tmp/billing')
    target={'eligible_test_ids':['q1','q2'],'max_usd':'0.40','reservation_per_target_usd':'0.001'}
    with patch.object(instance,'_validated',return_value=(target,Decimal('.20'),Decimal('.001'))):
        yield instance
    engine.dispose()


def test_unknown_cost_blocks_further_requests_and_preserves_answer(ledger):
    ledger.register('scope')
    with pytest.raises(ValueError,match='retrieval evidence'):ledger.begin('scope','q1','target','req1','c'*64)
    ledger.begin('scope','q1','target','req1','c'*64,request_evidence=evidence('q1'))
    assert ledger.settle('scope','req1','c'*64,'answer','invalid cost')['status']=='cost_unknown'
    with pytest.raises(ValueError,match='unresolved'):ledger.begin('scope','q2','target','req2','d'*64,request_evidence=evidence('q2'))
    with pytest.raises(ValueError,match='atomic target settlement'):
        ledger.settle('scope','req1','c'*64,'answer','0.0005')
    with pytest.raises(ValueError,match='unresolved'):ledger.begin('scope','q1','target','req1','c'*64,request_evidence=evidence('q1'))
    with ledger.engine.connect() as conn:
        assert conn.execute(text("SELECT response_text FROM ac3_paired_budget_receipts WHERE request_key='req1'")).scalar_one()=='answer'


def test_scorer_binds_saved_answer_and_overrun_stops_scope(ledger):
    ledger.register('scope')
    with pytest.raises(ValueError,match='settled target'):ledger.begin('scope','q1','scorer','score','e'*64,target_answer_sha256='f'*64)
    ledger.begin('scope','q1','target','target','c'*64,request_evidence=evidence('q1'))
    with pytest.raises(ValueError,match='pending'):ledger.settle('scope','target','d'*64,'answer','0.0005')
    # Simulate a prior atomic target settlement to exercise the scorer-only ledger.
    with ledger.engine.begin() as conn:
        conn.execute(text("UPDATE ac3_paired_budget_receipts SET status='settled',response_text='answer',reported_cost_usd='0.0005' WHERE request_key='target'"))
        conn.execute(text("UPDATE ac3_paired_budget_scopes SET status='active',spent_usd='0.0005' WHERE scope_id='scope'"))
    sha=hashlib.sha256(b'answer').hexdigest()
    with pytest.raises(ValueError,match='saved system answer'):
        ledger.begin('scope','q1','scorer','score','e'*64,target_answer_sha256=sha)
    local_id='AC3'+hashlib.sha256(f"{'a'*64}|r|q1".encode()).hexdigest()[:32].upper()
    response_id='ACR'+hashlib.sha256(b'scope|target').hexdigest()[:32].upper()
    with ledger.engine.connect() as conn:
        evidence_sha=conn.execute(text("SELECT request_evidence_sha256 FROM ac3_paired_budget_receipts WHERE request_key='target'")).scalar_one()
    with Session(ledger.engine) as db:
        db.add(ConversationModel(id='c',authorised=True,source_origin='synthetic'))
        db.add(AuditRunModel(id='r',conversation_id='c',status='RESEARCH_STAGED',target_configuration='strong',provider='rule_based',
            model='fixture',temperature=0,random_seed=0,test_budget=1,prompt_template_version='fixture'))
        db.add(TestCaseModel(id=local_id,run_id='r',dimension='accuracy',prompt='q',expected_behavior='a',
            supporting_memory_ids=[],generator_version='fixture'))
        db.add(TargetResponseModel(id=response_id,test_id=local_id,run_id='r',response_text='answer',model='fixture',temperature=0,
            execution_metadata={'ac3_paired_request_evidence_sha256':evidence_sha}))
        db.commit()
    ledger.begin('scope','q1','scorer','score','e'*64,target_answer_sha256=sha)
    assert ledger.settle('scope','score','e'*64,'grade','0.002')['status']=='overrun'
    with pytest.raises(ValueError,match='unresolved'):ledger.begin('scope','q2','target','another','d'*64,request_evidence=evidence('q2'))


def test_changed_budget_cannot_be_used_for_settlement(ledger):
    ledger.register('scope');ledger.begin('scope','q1','target','target','c'*64,request_evidence=evidence('q1'))
    with ledger.engine.begin() as conn:
        conn.execute(text("UPDATE ac3_paired_budget_scopes SET max_usd='9.00' WHERE scope_id='scope'"))
    with pytest.raises(ValueError,match='frozen assumptions'):
        ledger.settle('scope','target','c'*64,'answer','0.0005')


def test_reviewed_budget_plan_binds_all_sources_and_billing(tmp_path):
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    engine=create_engine('sqlite://')
    try:
        helper.cfg['budget']['max_usd']=.4
        raw=json.dumps(helper.freeze()).encode();frozen=tmp_path/'frozen.json';frozen.write_bytes(raw)
        frozen_sha=hashlib.sha256(raw).hexdigest()
        billing=tmp_path/'billing.txt';billing.write_text('synthetic billing fixture')
        record={'format':'ac3-paired-combined-budget-v1','frozen_sha256':frozen_sha,
            'fixed_before_target_results':True,'billing_reviewed':True,
            'billing_sha256':hashlib.sha256(billing.read_bytes()).hexdigest(),
            'target_reservation_usd':'.001','scorer_reservation_usd':'.0005','prior_upper_usd':'.20'}
        budget=tmp_path/'budget.json';budget.write_text(json.dumps(record))
        instance=PairedBudgetLedger(engine,frozen_path=frozen,frozen_sha256=frozen_sha,
            source=helper.source,plan=helper.plan,reviews=helper.reviews,components=helper.components,
            budget_path=budget,budget_sha256=hashlib.sha256(budget.read_bytes()).hexdigest(),billing_path=billing)
        target,prior,scorer=instance._validated()
        assert target['question_count']==120 and prior==Decimal('.20') and scorer==Decimal('.0005')
        billing.write_text('changed')
        with pytest.raises(ValueError,match='provenance'):instance._validated()
    finally:engine.dispose();helper.doCleanups()


def test_tracking_only_does_not_claim_historical_billing_or_impose_a_cap(tmp_path):
    from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    engine=create_engine('sqlite://')
    try:
        helper.cfg['budget_mode']='tracking_only'
        helper.cfg['budget']['max_usd']=1
        raw=json.dumps(helper.freeze()).encode(); frozen=tmp_path/'frozen.json'; frozen.write_bytes(raw)
        frozen_sha=hashlib.sha256(raw).hexdigest()
        billing=tmp_path/'billing.txt'; billing.write_text('historical billing not reconciled')
        record={'format':'ac3-paired-tracking-only-v1','frozen_sha256':frozen_sha,
                'fixed_before_target_results':True,'historical_billing_status':'unreconciled',
                'billing_sha256':hashlib.sha256(billing.read_bytes()).hexdigest(),
                'target_reservation_usd':'.001','scorer_reservation_usd':'.0005'}
        budget=tmp_path/'budget.json'; budget.write_text(json.dumps(record))
        instance=PairedBudgetLedger(engine,frozen_path=frozen,frozen_sha256=frozen_sha,
            source=helper.source,plan=helper.plan,reviews=helper.reviews,components=helper.components,
            budget_path=budget,budget_sha256=hashlib.sha256(budget.read_bytes()).hexdigest(),billing_path=billing)
        target,prior,scorer=instance._validated()
        assert target['budget_mode']=='tracking_only' and prior==Decimal('0') and scorer==Decimal('.0005')
        assert target['question_count']==120
    finally:engine.dispose();helper.doCleanups()
