"""Synthetic transport-only request binding; no external request is sent."""
from unittest.mock import MagicMock,patch
import httpx
import pytest
from app.services.ac3_paired_request_binding import PairedTargetRequestBinding
from app.target_ai.providers import HttpTargetAIConnector,single_attempt_target_request
from app.target_ai.request_contracts import observe_request_contracts
from test_ac3_request_binding import inputs


def make():
    test,audit=inputs();test=test.model_copy(update={'expected_behavior':'','supporting_memory_ids':[], 'target_memory_context':['fixture memory']})
    ledger=MagicMock();ledger.frozen_sha256='a'*64
    evidence={'format':'ac3-private-request-evidence-v1','frozen_test_id':'T001','run_id':'RUN1',
              'retrieval_id':'retrieval','selected_memory_ids':['f1'],'target_memory_context':['fixture memory']}
    ledger.begin.return_value={'status':'reserved','provider_called':False}
    binding=PairedTargetRequestBinding(ledger,'scope','a'*64,'req',test,audit,
        frozen_test_id='T001',frozen_question={'test_id':'T001','question':test.prompt},request_evidence=evidence)
    return test,audit,ledger,binding


def test_request_binds_paired_ledger_before_mock_transport(monkeypatch):
    test,audit,ledger,binding=make();monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    fake=httpx.Response(200,json={'model':audit.model,'choices':[{'finish_reason':'stop','message':{'content':'fixture'}}],'usage':{'cost':0.001}})
    with patch('app.target_ai.providers.httpx.post',return_value=fake) as post:
        with single_attempt_target_request(),observe_request_contracts(binding):
            answer=HttpTargetAIConnector().execute(test,audit)
    assert answer.response_text=='fixture' and post.call_count==1
    assert ledger.begin.call_args.args[:4]==('scope','T001','target','req')
    assert 'Evaluator private expectation.' not in str(post.call_args.kwargs['json'])


def test_wrong_question_or_unverified_reservation_blocks_transport(monkeypatch):
    test,audit,ledger,binding=make();monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-secret')
    with pytest.raises(ValueError,match='frozen question'):
        PairedTargetRequestBinding(ledger,'scope','a'*64,'req',test,audit,
            frozen_test_id='T001',frozen_question={'test_id':'T001','question':'changed'},request_evidence={})
    with pytest.raises(ValueError,match='retrieval evidence'):
        PairedTargetRequestBinding(ledger,'scope','a'*64,'req',test,audit,
            frozen_test_id='T001',frozen_question={'test_id':'T001','question':test.prompt},
            request_evidence={'frozen_test_id':'T001','run_id':'RUN1','target_memory_context':['different']})
    ledger.begin.return_value={'status':'unresolved','provider_called':False}
    with patch('app.target_ai.providers.httpx.post') as post:
        with single_attempt_target_request(),observe_request_contracts(binding):
            with pytest.raises(ValueError,match='reservation failed'):
                HttpTargetAIConnector().execute(test,audit)
        post.assert_not_called()
