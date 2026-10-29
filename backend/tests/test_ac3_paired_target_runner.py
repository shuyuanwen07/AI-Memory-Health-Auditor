"""Orchestration tests with a synthetic connector; no network or paid calls."""
import hashlib
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.services.ac3_paired_target_runner import run_paired_target_step
from scripts.ac3_retest_paired_freeze import canonical


@pytest.mark.parametrize('reported_cost', [0.0005, None])
def test_one_answer_is_preserved_before_settlement_or_unknown_cost_return(reported_cost):
    engine=MagicMock();engine.url.get_backend_name.return_value='postgresql'
    frozen={'protocol':{'target':{'provider':'openrouter','retry_limit':0}}}
    source=b'source';plan=b'plan';reviews=[b'one',b'two'];components={'target_runtime':b'fixture'}
    ledger=MagicMock(engine=engine,source=source,plan=plan,reviews=reviews,components=components,
                     frozen_sha256=hashlib.sha256(canonical(frozen)).hexdigest())
    question={'test_id':'q','history_id':'h','question':'A question'}
    db=MagicMock();audit_row=object();test_row=SimpleNamespace(run_id='r');conversation_row=object()
    db.get.side_effect=[audit_row,test_row,conversation_row]
    session=MagicMock();session.__enter__.return_value=db
    audit=SimpleNamespace(conversation_id='c',target_configuration='strong')
    metadata=SimpleNamespace(memory_input=None,reported_cost_usd=reported_cost,
        model_dump=lambda **kwargs:{'request_contract_sha256':'a'*64,'reported_cost_usd':reported_cost})
    response=SimpleNamespace(execution_metadata=metadata,response_text='saved answer')
    adapter=MagicMock();connector=MagicMock();connector.execute.return_value=response
    patches=[
        patch('app.services.ac3_paired_target_runner.compile_isolated',return_value={'items':[question]}),
        patch('app.services.ac3_paired_target_runner.formal_signature',return_value={'app_source_sha256':'same'}),
        patch('app.services.ac3_paired_target_runner.formal_runtime_signature',return_value={'source_sha256':'same'}),
        patch('app.services.ac3_paired_target_runner.Session',return_value=session),
        patch('app.services.ac3_paired_target_runner.ac3_sequence_locks',return_value=nullcontext()),
        patch('app.services.ac3_paired_target_runner.locked_paired_preflight',return_value=nullcontext()),
        patch('app.api.routes.audit_schema',return_value=audit),
        patch('app.api.routes.test_schema',return_value=object()),
        patch('app.api.routes.conversation_schema',return_value=object()),
        patch('app.services.ac3_paired_target_runner.ControlledTargetSystemAdapter',return_value=adapter),
        patch('app.services.ac3_paired_target_runner.prepare_ac3_input',return_value=(object(),{})),
        patch('app.services.ac3_paired_target_runner.PairedTargetRequestBinding'),
        patch('app.services.ac3_paired_target_runner.single_attempt_target_request',return_value=nullcontext()),
        patch('app.services.ac3_paired_target_runner.observe_request_contracts',return_value=nullcontext()),
        patch('app.services.ac3_paired_target_runner.HttpTargetAIConnector',return_value=connector),
        patch('app.services.ac3_paired_target_runner.settle_target',return_value={'status':'settled'}),
    ]
    from contextlib import ExitStack
    with ExitStack() as stack:
        mocks=[stack.enter_context(p) for p in patches]
        result=run_paired_target_step(engine,ledger=ledger,frozen=frozen,source=source,plan=plan,
            reviews=reviews,components=components,history_conversations={'h':'c'},history_runs={'h':'r'},
            scope='scope',test_id='q',request_key='key')
    ledger.settle.assert_called_once_with('scope','key','a'*64,'saved answer',None,
        response_metadata={'request_contract_sha256':'a'*64,'reported_cost_usd':reported_cost})
    connector.execute.assert_called_once()
    assert not result['automatic_retry_allowed'] and result['target_response_preserved']
    assert result['status']==('cost_unknown' if reported_cost is None else 'settled')
    assert mocks[-1].called == (reported_cost is not None)
