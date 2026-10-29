"""Synthetic budget concurrency tests in the named disposable database only."""
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.models import TestCaseModel, TargetResponseModel
from test_ac3_staging_postgres_isolated import isolated_db
from test_ac3_paired_budget_ledger import evidence

pytestmark=pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST')!='yes',reason='Disposable PostgreSQL only')


@pytest.fixture
def ledger(isolated_db):
    engine,*_=isolated_db
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_receipts'))
        conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_scopes'))
        for statement in Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text().split(';'):
            if statement.strip():conn.execute(text(statement))
    instance=PairedBudgetLedger(engine,frozen_path='/tmp/synthetic',frozen_sha256='a'*64,source=b'',plan=b'',reviews=[],components={},
        budget_path='/tmp/synthetic-budget',budget_sha256='b'*64,billing_path='/tmp/synthetic-billing')
    target={'eligible_test_ids':['q1','q2'],'max_usd':'0.40','reservation_per_target_usd':'0.001'}
    with patch.object(instance,'_validated',return_value=(target,Decimal('.20'),Decimal('.001'))):
        instance.register('scope')
        yield instance


def test_concurrent_reservations_allow_only_one_outstanding(ledger):
    def dispatch(n):
        try:
            return ledger.begin('scope',f'q{n}','target',f'req{n}',str(n)*64,request_evidence=evidence(f'q{n}'))['status']
        except Exception as exc:
            return getattr(getattr(exc,'orig',None),'sqlstate',type(exc).__name__)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(dispatch,[1,2]))
    assert results.count('reserved')==1
    assert all(x in ('reserved','40001','ValueError') for x in results)
    with ledger.engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM ac3_paired_budget_receipts')).scalar_one()==1
        assert conn.execute(text("SELECT status FROM ac3_paired_budget_scopes WHERE scope_id='scope'")).scalar_one()=='unknown'


def test_receipt_and_budget_settlement_roll_back_together(ledger):
    ledger.begin('scope','q1','target','req1','c'*64,request_evidence=evidence('q1','R0'))
    with ledger.engine.begin() as conn:
        conn.execute(text("UPDATE ac3_paired_budget_receipts SET status='settled',response_text='answer',reported_cost_usd='0.0005' WHERE request_key='req1'"))
        conn.execute(text("UPDATE ac3_paired_budget_scopes SET status='active',spent_usd='0.0005' WHERE scope_id='scope'"))
    import hashlib
    local_id='AC3'+hashlib.sha256(f"{'a'*64}|R0|q1".encode()).hexdigest()[:32].upper()
    response_id='ACR'+hashlib.sha256(b'scope|req1').hexdigest()[:32].upper()
    with ledger.engine.connect() as conn:
        evidence_sha=conn.execute(text("SELECT request_evidence_sha256 FROM ac3_paired_budget_receipts WHERE request_key='req1'")).scalar_one()
    with Session(ledger.engine) as db:
        db.add(TestCaseModel(id=local_id,run_id='R0',dimension='accuracy',prompt='q',expected_behavior='a',
            supporting_memory_ids=[],generator_version='fixture'))
        db.flush()
        db.add(TargetResponseModel(id=response_id,test_id=local_id,run_id='R0',response_text='answer',model='fixture',temperature=0,
            execution_metadata={'ac3_paired_request_evidence_sha256':evidence_sha}))
        db.commit()
    ledger.begin('scope','q1','scorer','score','d'*64,target_answer_sha256=hashlib.sha256(b'answer').hexdigest())
    def fail(_conn,_cursor,statement,_params,_context,_many):
        if statement.lstrip().upper().startswith('UPDATE AC3_PAIRED_BUDGET_SCOPES SET SPENT_USD'):
            raise RuntimeError('synthetic interruption')
    event.listen(ledger.engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='synthetic interruption'):
            ledger.settle('scope','score','d'*64,'synthetic grade','0.0005')
    finally:event.remove(ledger.engine,'before_cursor_execute',fail)
    with ledger.engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM ac3_paired_budget_receipts WHERE request_key='score'")).scalar_one()=='dispatched'
        assert conn.execute(text("SELECT status FROM ac3_paired_budget_scopes WHERE scope_id='scope'")).scalar_one()=='unknown'
    assert ledger.settle('scope','score','d'*64,'synthetic grade','0.0005')['status']=='settled'
