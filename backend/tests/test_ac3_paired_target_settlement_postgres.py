"""Synthetic target/receipt settlement in a disposable PostgreSQL container."""
import hashlib
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import event,select,text
from sqlalchemy.orm import Session
from app.models import TargetResponseModel
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_target_settlement import settle_target
from scripts.ac3_retest_paired_freeze import canonical
from test_ac3_retest_staging_postgres import inputs, isolated_db, stage
from test_ac3_paired_budget_ledger import evidence

pytestmark=pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST')!='yes',reason='Disposable PostgreSQL only')


@pytest.fixture
def ready(isolated_db):
    engine,mapping,runs,prepared,frozen=inputs(isolated_db)
    with Session(engine) as db:stage(db,mapping,runs,prepared,frozen)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_receipts'))
        conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_scopes'))
        for sql in Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text().split(';'):
            if sql.strip():conn.execute(text(sql))
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    ledger=PairedBudgetLedger(engine,frozen_path='/tmp/synthetic',frozen_sha256=sha,source=b'',plan=b'',reviews=[],components={},
                              budget_path='/tmp/budget',budget_sha256='b'*64,billing_path='/tmp/billing')
    target={'eligible_test_ids':[q['test_id'] for q in prepared['questions']],
            'max_usd':'0.40','reservation_per_target_usd':'0.001'}
    with patch.object(ledger,'_validated',return_value=(target,Decimal('.20'),Decimal('.001'))), \
         patch('app.services.ac3_paired_target_settlement.compile_reference_stage',return_value=prepared):
        ledger.register('scope');ledger.begin('scope','H0-Q0','target','req','c'*64,request_evidence=evidence('H0-Q0','R0'))
        yield ledger,frozen


def call(ready,response='synthetic answer'):
    ledger,frozen=ready
    return settle_target(ledger,frozen=frozen,scope='scope',test_id='H0-Q0',run_id='R0',request_key='req',
        contract_sha256='c'*64,response=response,reported_cost_usd='0.0005',
        execution_metadata={'request_contract_sha256':'c'*64,'reported_cost_usd':'0.0005'})


def test_target_response_and_cost_recover_without_duplication(ready):
    assert call(ready)['status']=='settled'
    assert call(ready)['status']=='already_settled'
    with pytest.raises(ValueError,match='differs'):call(ready,'changed')
    with Session(ready[0].engine) as db:assert len(list(db.scalars(select(TargetResponseModel))))==1


def test_target_and_cost_roll_back_together(ready):
    ledger,_=ready
    def fail(_conn,_cursor,statement,_params,_context,_many):
        if statement.lstrip().upper().startswith('UPDATE AC3_PAIRED_BUDGET_SCOPES SET SPENT_USD'):
            raise RuntimeError('synthetic interruption')
    event.listen(ledger.engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='synthetic interruption'):call(ready)
    finally:event.remove(ledger.engine,'before_cursor_execute',fail)
    with Session(ledger.engine) as db:
        assert not list(db.scalars(select(TargetResponseModel)))
        assert db.execute(text("SELECT status FROM ac3_paired_budget_receipts WHERE request_key='req'")).scalar_one()=='dispatched'
    assert call(ready)['status']=='settled'
