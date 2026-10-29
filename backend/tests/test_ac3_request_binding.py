"""Contract binding tests use synthetic requests and no network or database."""
from unittest.mock import MagicMock, patch
import httpx
import pytest
from app.schemas import Dimension, TargetProvider, TestCase as DomainTestCase
from app.services.ac3_request_binding import AC3RequestBinding
from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
from app.target_ai.request_contracts import observe_request_contracts
from scripts.ac3_fixed_suite_adapter import sha
from test_target_providers import run


def inputs():
    local_id = 'AC3' + sha(f"{'a' * 64}|RUN1|T001".encode())[:32].upper()
    test = DomainTestCase(test_id=local_id, run_id='RUN1', dimension=Dimension.ACCURACY,
        prompt='Fixture question?', expected_behavior='Evaluator private expectation.', supporting_memory_ids=['M001'], generator_version='fixture')
    audit = run(TargetProvider.OPENROUTER, 'openai/gpt-6-luna')
    return test, audit


def test_actual_connector_binds_exact_test_before_fake_transport(monkeypatch):
    test, audit = inputs()
    ledger = MagicMock(); ledger.begin.return_value = {'state': 'dispatched', 'duplicate': False}
    binder = AC3RequestBinding(ledger, 'fixture', 'a' * 64, 'request-1', test, audit, frozen_test_id='T001')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-secret')
    fake = httpx.Response(200, json={'model': audit.model, 'choices': [{'finish_reason': 'stop', 'message': {'content': 'fixture'}}], 'usage': {'cost': 0.001}})
    with patch('app.target_ai.providers.httpx.post', return_value=fake) as post:
        with single_attempt_target_request(), observe_request_contracts(binder):
            answer = HttpTargetAIConnector().execute(test, audit)
    assert answer.response_text == 'fixture' and post.call_count == 1
    assert ledger.begin.call_count == 1 and ledger.begin.call_args.args[-1] == 'T001'
    assert 'Evaluator private expectation.' not in str(post.call_args.kwargs['json'])


def test_changed_question_is_blocked_before_transport(monkeypatch):
    test, audit = inputs()
    ledger = MagicMock(); ledger.begin.return_value = {'state': 'dispatched', 'duplicate': False}
    binder = AC3RequestBinding(ledger, 'fixture', 'a' * 64, 'request-1', test, audit, frozen_test_id='T001')
    tampered = test.model_copy(update={'prompt': 'Changed question'})
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-secret')
    with patch('app.target_ai.providers.httpx.post') as post:
        with single_attempt_target_request(), observe_request_contracts(binder):
            with pytest.raises(ValueError, match='differs'):
                HttpTargetAIConnector().execute(tampered, audit)
        post.assert_not_called(); ledger.begin.assert_not_called()


def test_a_settled_duplicate_never_reaches_transport(monkeypatch):
    test, audit = inputs()
    ledger = MagicMock(); ledger.begin.return_value = {'state': 'settled', 'duplicate': True}
    binder = AC3RequestBinding(ledger, 'fixture', 'a' * 64, 'request-1', test, audit, frozen_test_id='T001')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-secret')
    with patch('app.target_ai.providers.httpx.post') as post:
        with single_attempt_target_request(), observe_request_contracts(binder):
            with pytest.raises(ValueError, match='already recorded'):
                HttpTargetAIConnector().execute(test, audit)
        post.assert_not_called()


def test_wrong_frozen_identity_never_binds():
    test, audit = inputs()
    with pytest.raises(ValueError, match='frozen question'):
        AC3RequestBinding(MagicMock(), 'fixture', 'a' * 64, 'request-1', test, audit, frozen_test_id='T002')
