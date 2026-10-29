"""Synthetic atomic settlement; no real model or reviewer evidence."""
import hashlib
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import event, text
from app.models import AuditRunModel, TargetResponseModel
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_target_settlement import settle_target
from app.services.ac3_retest_staging import stage_paired_retest
from scripts.ac3_retest_paired_freeze import canonical
from test_ac3_retest_binding import fixture as fixture
from test_ac3_paired_budget_ledger import evidence


@pytest.fixture
def staged(fixture):
    db,stage=fixture
    db.add(AuditRunModel(id='r',conversation_id='c',status='CREATED',target_configuration='strong',provider='rule_based',
        model='fixture',temperature=0,random_seed=0,test_budget=1,prompt_template_version='fixture',memory_strategy='strong_rule_based'))
    db.commit()
    stage['questions']=[{'history_id':'h','test_id':'q','dimension':'accuracy','question':'Which day?',
                         'expected_behavior':'Tuesday','supporting_memory_ids':['f1']}]
    frozen={'protocol':{'target':{'provider':'rule_based','model':'fixture','strategy':'strong_rule_based','prompt_template_version':'fixture'}}}
    with patch('app.services.ac3_retest_staging.verify_database_binding'),patch('app.services.ac3_retest_staging.compile_reference_stage',return_value=stage):
        stage_paired_retest(db,frozen,b'',b'',[],{}, {'h':'c'},{'h':'r'})
    db.rollback();engine=db.get_bind()
    with engine.begin() as conn:
        for sql in Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text().split(';'):
            if sql.strip():conn.execute(text(sql))
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    ledger=PairedBudgetLedger(engine,frozen_path='/tmp/synthetic',frozen_sha256=sha,source=b'',plan=b'',reviews=[],components={},
                              budget_path='/tmp/budget',budget_sha256='b'*64,billing_path='/tmp/billing')
    target={'eligible_test_ids':['q'],'max_usd':'0.40','reservation_per_target_usd':'0.001'}
    with patch.object(ledger,'_validated',return_value=(target,Decimal('.20'),Decimal('.001'))), \
         patch('app.services.ac3_paired_target_settlement.compile_reference_stage',return_value=stage):
        ledger.register('scope');ledger.begin('scope','q','target','req','c'*64,request_evidence=evidence('q'))
        yield db,ledger,frozen


def call(staged,response='answer'):
    _,ledger,frozen=staged
    return settle_target(ledger,frozen=frozen,scope='scope',test_id='q',run_id='r',request_key='req',
        contract_sha256='c'*64,response=response,reported_cost_usd='0.0005',
        execution_metadata={'request_contract_sha256':'c'*64,'reported_cost_usd':'0.0005'})


def test_atomic_target_settlement_and_recovery(staged):
    db,_,_=staged
    assert call(staged)['status']=='settled'
    assert call(staged)['status']=='already_settled'
    with pytest.raises(ValueError,match='differs'):call(staged,'different')
    with pytest.raises(ValueError,match='differs'):
        settle_target(staged[1],frozen=staged[2],scope='scope',test_id='q',run_id='r',request_key='req',
            contract_sha256='c'*64,response='answer',reported_cost_usd='0.0005',
            execution_metadata={'request_contract_sha256':'c'*64,'reported_cost_usd':'0.0005','unexpected':'changed'})
    assert db.query(TargetResponseModel).count()==1


def test_failed_budget_write_rolls_back_response_and_receipt(staged):
    db,ledger,_=staged
    def fail(_conn,_cursor,statement,_params,_context,_many):
        if statement.lstrip().upper().startswith('UPDATE AC3_PAIRED_BUDGET_SCOPES SET SPENT_USD'):
            raise RuntimeError('synthetic interruption')
    event.listen(ledger.engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='synthetic interruption'):call(staged)
    finally:event.remove(ledger.engine,'before_cursor_execute',fail)
    db.expire_all()
    assert db.query(TargetResponseModel).count()==0
    assert db.execute(text("SELECT status FROM ac3_paired_budget_receipts WHERE request_key='req'")).scalar_one()=='dispatched'


def test_changed_retrieval_evidence_cannot_be_settled(staged):
    db,ledger,_=staged
    with ledger.engine.begin() as conn:
        conn.execute(text("UPDATE ac3_paired_budget_receipts SET request_evidence_json='{}' WHERE request_key='req'"))
    with pytest.raises(ValueError,match='retrieval evidence'):call(staged)
    db.expire_all();assert db.query(TargetResponseModel).count()==0
