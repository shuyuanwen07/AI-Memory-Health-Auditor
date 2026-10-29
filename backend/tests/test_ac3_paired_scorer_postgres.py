"""Synthetic scorer reservation against a settled target; mocked HTTP only."""
import hashlib
import os
from unittest.mock import patch
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models import TestCaseModel,TargetResponseModel
from app.services.ac3_paired_scorer_transport import post_once
from app.target_ai.request_contracts import build_openrouter_request_contract
from test_ac3_paired_budget_postgres import ledger as ledger
from test_ac3_paired_budget_ledger import evidence
from test_ac3_staging_postgres_isolated import isolated_db as isolated_db

pytestmark=pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST')!='yes',reason='Disposable PostgreSQL only')


@pytest.mark.parametrize('cost_known',[True,False])
def test_scorer_binds_saved_answer_and_blocks_duplicate(ledger,cost_known):
    scope='scope';answer='synthetic answer';target_key='target-request'
    ledger.begin(scope,'q1','target',target_key,'c'*64,request_evidence=evidence('q1','R0'))
    with ledger.engine.begin() as conn:
        conn.execute(text("UPDATE ac3_paired_budget_receipts SET status='settled',response_text=:answer,reported_cost_usd='0.0005' WHERE request_key=:key"),{'answer':answer,'key':target_key})
        conn.execute(text("UPDATE ac3_paired_budget_scopes SET status='active',spent_usd='0.0005' WHERE scope_id=:scope"),{'scope':scope})
        evidence_sha=conn.execute(text('SELECT request_evidence_sha256 FROM ac3_paired_budget_receipts WHERE request_key=:key'),{'key':target_key}).scalar_one()
    local_id='AC3'+hashlib.sha256(f"{ledger.frozen_sha256}|R0|q1".encode()).hexdigest()[:32].upper()
    response_id='ACR'+hashlib.sha256(f'{scope}|{target_key}'.encode()).hexdigest()[:32].upper()
    with Session(ledger.engine) as db:
        db.add(TestCaseModel(id=local_id,run_id='R0',dimension='accuracy',prompt='question',expected_behavior='reference',
                             supporting_memory_ids=[],generator_version='fixture'))
        db.flush()
        db.add(TargetResponseModel(id=response_id,test_id=local_id,run_id='R0',response_text=answer,model='fixture',temperature=0,
                                   execution_metadata={'ac3_paired_request_evidence_sha256':evidence_sha}))
        db.commit()
    payload={'model':'openai/gpt-6-luna','max_tokens':20,'messages':[{'role':'user','content':'synthetic'}]}
    contract=build_openrouter_request_contract(url='https://openrouter.ai/api/v1/chat/completions',payload=payload,role='paired_scorer')
    usage={'cost':0.0001} if cost_known else {}
    response=httpx.Response(200,json={'choices':[{'message':{'content':'synthetic grade'}}],'usage':usage})
    args=dict(scope=scope,test_id='q1',request_key='scorer-request',
              target_answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),expected_contract=contract,
              payload=payload,headers={'Authorization':'Bearer synthetic'},output_token_limit=20)
    with patch('app.services.ac3_paired_scorer_transport.httpx.post',return_value=response) as post:
        result=post_once(ledger,**args)
        assert result['status']==('settled' if cost_known else 'cost_unknown')
        with pytest.raises(ValueError):post_once(ledger,**args)
        assert post.call_count==1
    with ledger.engine.connect() as conn:
        receipt=conn.execute(text("SELECT status,response_text,target_answer_sha256 FROM ac3_paired_budget_receipts WHERE request_key='scorer-request'")).mappings().one()
        assert receipt['status']==('settled' if cost_known else 'pending')
        assert receipt['target_answer_sha256']==args['target_answer_sha256'] and 'synthetic grade' in receipt['response_text']
        assert conn.execute(text("SELECT status FROM ac3_paired_budget_scopes WHERE scope_id='scope'")).scalar_one()==('active' if cost_known else 'unknown')
