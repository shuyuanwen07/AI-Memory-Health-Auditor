"""Run a complete synthetic target step using disposable PostgreSQL and mocked HTTP."""
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models import AuditRunModel, TargetResponseModel
from app.schemas import AuditRun
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS
from app.services.ac3_paired_budget_ledger import PairedBudgetLedger
from app.services.ac3_paired_target_runner import run_paired_target_step
from app.services.ac3_paired_target_settlement import settle_target
from app.services.ac3_paired_scorer_runner import run_paired_scorer_step
from app.services.ac3_retest_prepare import prepare_paired_retest
from scripts.ac3_retest_paired_freeze import canonical
from scripts.tests.test_ac3_retest_paired_freeze import PairFreezeTests
from test_ac3_staging_postgres_isolated import isolated_db as isolated_db, URL

pytestmark=pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST')!='yes',reason='Disposable PostgreSQL only')


@pytest.mark.parametrize('mode', ['success', 'transport_failure', 'cost_unknown'])
def test_synthetic_live_path_persists_or_blocks_unknown_and_prevents_repeat(isolated_db,mode):
    # Dedicated 4-connection pool: stage advisory lock, input transaction and
    # independent ledger receipt must be able to coexist.
    engine=create_engine(URL,isolation_level='SERIALIZABLE',pool_size=4,max_overflow=0,pool_timeout=3)
    helper=PairFreezeTests('test_end_to_end_isolated');helper.setUp()
    try:
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_receipts'))
            conn.execute(text('DROP TABLE IF EXISTS ac3_paired_budget_scopes'))
            for sql in Path('/app/research_migrations/ac3_paired_budget_draft.sql').read_text().split(';'):
                if sql.strip():conn.execute(text(sql))
        sample=AuditRun(run_id='sample',conversation_id='sample',status='CREATED',target_configuration='strong',
            provider='openrouter',model='openai/gpt-6-luna',temperature=0,random_seed=1,test_budget=4,
            prompt_template_version='fixture',memory_strategy='strong_rule_based',
            target_memory_profile={'output_token_limit':20},target_memory_writer_version='fixture-writer',
            target_system_adapter_version='fixture-adapter',created_at=datetime.now(timezone.utc))
        setup=sample.model_dump(mode='json',include=_SETTINGS_FIELDS)
        helper.cfg['target'].update(provider='openrouter',model='openai/gpt-6-luna',strategy='strong_rule_based',
            prompt_template_version='fixture',temperature=None,random_seed=None,output_token_limit=20,retry_limit=0,
            memory_configuration_sha256=hashlib.sha256(canonical(setup)).hexdigest())
        helper.cfg['scorer']={'provider':'openrouter','model':'openai/gpt-6-luna','output_token_limit':20,
                              'prompt_version':'fixture-structured-v2','retry_limit':0,'variant':'hybrid'}
        frozen=helper.freeze();sha=hashlib.sha256(canonical(frozen)).hexdigest()
        prepare_paired_retest(engine,frozen,helper.source,helper.plan,helper.reviews,helper.components,setup)
        with Session(engine) as db:
            audits=[r for r in db.scalars(select(AuditRunModel)) if r.status=='RESEARCH_STAGED']
            runs={r.reproducibility_metadata['ac3_paired_retest']['history_id']:r.id for r in audits}
            conversations={r.reproducibility_metadata['ac3_paired_retest']['history_id']:r.conversation_id for r in audits}
        test_id=frozen['suite']['cases'][0]['tests'][0]['test_id']
        ledger=PairedBudgetLedger(engine,frozen_path='/tmp/synthetic',frozen_sha256=sha,source=helper.source,
            plan=helper.plan,reviews=helper.reviews,components=helper.components,budget_path='/tmp/synthetic-budget',
            budget_sha256='b'*64,billing_path='/tmp/synthetic-billing')
        budget={'eligible_test_ids':[test_id],'max_usd':'0.40','reservation_per_target_usd':'0.001'}
        usage={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}
        if mode!='cost_unknown':usage['cost']=0.0001
        fake=httpx.Response(200,json={'id':'synthetic','model':'openai/gpt-6-luna',
            'choices':[{'message':{'content':'Synthetic answer'},'finish_reason':'stop'}],
            'usage':usage})
        with patch.object(ledger,'_validated',return_value=(budget,Decimal('0.20'),Decimal('0.001'))), \
             patch('app.services.ac3_paired_target_runner.formal_signature',return_value={'app_source_sha256':'synthetic'}), \
             patch('app.services.ac3_paired_target_runner.formal_runtime_signature',return_value={'source_sha256':'synthetic'}), \
             patch('app.target_ai.providers.HttpTargetAIConnector._credential_for',return_value='synthetic'), \
             patch('app.target_ai.providers.httpx.post',return_value=fake,
                   side_effect=httpx.ConnectError('synthetic transport failure') if mode=='transport_failure' else None) as post:
            args=dict(ledger=ledger,frozen=frozen,source=helper.source,plan=helper.plan,reviews=helper.reviews,
                components=helper.components,history_conversations=conversations,history_runs=runs,
                scope='synthetic',test_id=test_id,request_key='request-1')
            if mode=='transport_failure':
                with pytest.raises(HTTPException):run_paired_target_step(engine,**args)
            else:
                result=run_paired_target_step(engine,**args)
                assert result['status']==('cost_unknown' if mode=='cost_unknown' else 'settled')
                assert result['target_response_preserved']
            with pytest.raises(ValueError):run_paired_target_step(engine,**args)
            assert post.call_count==1
            if mode=='success':
                class BlindJudge:
                    VERSION_PREFIX='fixture'
                    def _judge_prompt(self,test,answer,memories):return test.prompt+' | '+answer.response_text+' | '+memories[0].canonical_value
                    def _system_instruction(self):return 'Judge synthetic evidence.'
                    def _openai_schema(self,ids):return {'type':'json_schema','name':'fixture','schema':{'type':'object'}}
                scorer_args=dict(ledger=ledger,frozen=frozen,source=helper.source,plan=helper.plan,reviews=helper.reviews,
                    components=helper.components,history_conversations=conversations,history_runs=runs,scope='synthetic',
                    test_id=test_id,request_key='scorer-1',judge=BlindJudge(),headers={'Authorization':'Bearer synthetic'})
                grade=httpx.Response(200,json={'choices':[{'message':{'content':'synthetic grade'}}],'usage':{'cost':0.0001}})
                with patch('app.services.ac3_paired_scorer_step.verify_scorer_snapshot'), \
                     patch('app.services.ac3_paired_scorer_transport.httpx.post',return_value=grade) as score_post:
                    scored=run_paired_scorer_step(engine,**scorer_args)
                    assert scored['status']=='settled' and scored['scorer_output_preserved']
                    with pytest.raises(ValueError):run_paired_scorer_step(engine,**scorer_args)
                    assert score_post.call_count==1
        with Session(engine) as db:
            saved=list(db.scalars(select(TargetResponseModel)))
            if mode=='transport_failure':
                assert saved==[]
                assert db.execute(text("SELECT status FROM ac3_paired_budget_receipts WHERE request_key='request-1'")).scalar_one()=='dispatched'
                assert db.execute(text("SELECT status FROM ac3_paired_budget_scopes WHERE scope_id='synthetic'")).scalar_one()=='unknown'
            elif mode=='cost_unknown':
                assert saved==[]
                receipt=db.execute(text("SELECT status,response_text,response_metadata_json FROM ac3_paired_budget_receipts WHERE request_key='request-1'")).mappings().one()
                assert receipt['status']=='pending' and receipt['response_text']=='Synthetic answer'
                assert receipt['response_metadata_json'] and 'request_contract_sha256' in receipt['response_metadata_json']
                pending_metadata=json.loads(receipt['response_metadata_json'])
                assert db.execute(text("SELECT status FROM ac3_paired_budget_scopes WHERE scope_id='synthetic'")).scalar_one()=='unknown'
            else:
                assert len(saved)==1 and saved[0].response_text=='Synthetic answer'
                assert db.execute(text("SELECT status FROM ac3_paired_budget_receipts WHERE request_key='request-1'")).scalar_one()=='settled'
        if mode=='cost_unknown':
            pending_metadata['reported_cost_usd']='0.0001'  # synthetic later billing evidence
            history=frozen['suite']['cases'][0]['history_id']
            with patch.object(ledger,'_validated',return_value=(budget,Decimal('0.20'),Decimal('0.001'))):
                recovered=settle_target(ledger,frozen=frozen,scope='synthetic',test_id=test_id,run_id=runs[history],
                    request_key='request-1',contract_sha256=pending_metadata['request_contract_sha256'],
                    response='Synthetic answer',reported_cost_usd='0.0001',execution_metadata=pending_metadata)
            assert recovered['status']=='settled'
            with Session(engine) as db:
                assert len(list(db.scalars(select(TargetResponseModel))))==1
    finally:
        helper.doCleanups();engine.dispose()
