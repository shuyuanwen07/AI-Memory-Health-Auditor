"""Offline release09 wire controls, actual boundary capture and refusal binding."""
import copy
import json

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.extraction.llm import PipelineLLMClient, PipelineRequestError, resolve_pipeline_output_budget
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
from app.memory_agent.identity_failure import build_identity_failure_receipt, recorded_identity_failure_matches
from app.models import AgentExecutionModel
from app.schemas.domain import ExecutionMetadata
from app.schemas.target_profile import TargetMemoryProfile
from app.services.agent_trace import agent_execution_schema
from app.target_ai.openrouter import (CHAT_COMPLETIONS_URL, build_openrouter_target_payload,
                                      build_openrouter_json_payload, validate_reasoning_effort)
from app.target_ai.request_contracts import (build_openrouter_request_contract, observe_request_contracts,
    request_contract_sha256, send_with_request_contract)
from test_target_identity_integration import setup_target

LUNA = 'openai/gpt-6-luna'
ROUTING = {'require_parameters': True, 'allow_fallbacks': False}


def payload(effort=None, cap=8192):
    return build_openrouter_target_payload(model=LUNA, instructions='PRIVATE_SOURCE', prompt='PRIVATE_QUESTION',
        temperature=0, max_output_tokens=cap, reasoning_effort=effort, provider_options=ROUTING)


def reply(content='{}', finish='stop'):
    return httpx.Response(200, json={'model': LUNA, 'choices': [{'finish_reason': finish, 'message': {'content': content}}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 8192 if finish == 'length' else 20,
                  'total_tokens': 8202 if finish == 'length' else 30}})


def test_legacy_profile_and_execution_omit_new_null_fields():
    p = TargetMemoryProfile()
    assert 'reasoning_effort' not in p.model_dump(mode='json')
    assert 'identity_analysis_reasoning_effort' not in p.model_dump(mode='json')
    assert 'request_contract' not in ExecutionMetadata().model_dump(mode='json')
    assert 'reasoning' not in payload(None)
    assert payload('low')['reasoning'] == {'effort': 'low'}
    for key in ['identity_analysis_reasoning_effort']:
        with pytest.raises(ValueError):
            TargetMemoryProfile(**{key: 'medium'})


@pytest.mark.parametrize('provider,model,effort', [('openai', LUNA, 'low'), ('ollama', LUNA, 'low'),
    ('openrouter', 'other', 'low'), ('openrouter', LUNA, 'none'), ('openrouter', LUNA, False)])
def test_unsupported_reasoning_fails_before_request(provider, model, effort):
    with pytest.raises(ValueError):
        validate_reasoning_effort(provider, model, effort)


def test_builders_and_contract_preserve_omission_null_and_schema_hash():
    route = copy.deepcopy(ROUTING); schema = {'type': 'object'}
    p = build_openrouter_json_payload(model=LUNA, instructions='PRIVATE_SOURCE', prompt='PRIVATE_QUESTION',
        schema_name='benchmark_pilot_assessment', schema=schema, max_output_tokens=4096, provider_options=route)
    assert 'reasoning' not in p and p['max_tokens'] == 4096
    assert 'temperature' not in p and p['provider'] == ROUTING
    contract = build_openrouter_request_contract(url=CHAT_COMPLETIONS_URL, payload=p, role='benchmark_pilot_assessment')
    assert contract['reasoning'] == {'present': False}
    assert contract['response_format']['schema_sha256'] == request_contract_sha256(schema)
    changed = copy.deepcopy(p); changed['reasoning'] = None
    null = build_openrouter_request_contract(url=CHAT_COMPLETIONS_URL, payload=changed, role='benchmark_pilot_assessment')
    assert null['reasoning'] == {'present': True, 'value': None} and null['payload_sha256'] != contract['payload_sha256']
    schema['secret'] = 'AFTER'; route['only'] = ['AFTER']
    assert 'secret' not in p['response_format']['json_schema']['schema'] and 'only' not in p['provider']
    assert 'PRIVATE_' not in json.dumps(contract)


def test_budget_resolution_does_not_inherit_target_cap_into_grader():
    assert resolve_pipeline_output_budget(8192, 4096)['requested_output_token_limit'] == 4096
    assert resolve_pipeline_output_budget(8192, 8192)['requested_output_token_limit'] == 8192
    assert resolve_pipeline_output_budget(4096, 8192)['requested_output_token_limit'] == 4096


def test_before_send_detects_dropped_reasoning_without_attempt_or_network():
    p = payload('low'); p.pop('reasoning'); attempts = []; sent = []
    def verify(event):
        assert event['phase'] == 'before_send'
        if event['request_contract']['reasoning'] != {'present': True, 'value': {'effort': 'low'}}:
            raise ValueError('Frozen wire control mismatch')
    with observe_request_contracts(verify), pytest.raises(ValueError):
        send_with_request_contract(url=CHAT_COMPLETIONS_URL, payload=p, role='target_answer', attempt_index=1,
            collector=attempts, send=lambda: sent.append(True))
    assert attempts == [] and sent == []


def test_after_send_observer_failure_keeps_original_transport_error():
    original = httpx.ConnectError('PRIVATE_TRANSPORT_ERROR'); attempts = []
    def observe(event):
        if event['phase'] == 'after_send':
            raise OSError('PRIVATE_WRITE_ERROR')
    def fail():
        raise original
    with observe_request_contracts(observe), pytest.raises(httpx.ConnectError) as got:
        send_with_request_contract(url=CHAT_COMPLETIONS_URL, payload=payload('low'), role='target_answer',
                                   attempt_index=1, collector=attempts, send=fail)
    assert got.value is original and attempts[0]['observer_error_type'] == 'OSError'
    assert 'PRIVATE_' not in json.dumps(attempts)


def test_pipeline_each_actual_retry_is_recorded_and_grader_reasoning_omitted(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PRIVATE_FAKE_KEY')
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS', '8192')
    monkeypatch.setattr('app.extraction.llm.time.sleep', lambda _: None)
    sent = []
    def post(*args, **kwargs):
        sent.append(copy.deepcopy(kwargs['json']))
        return httpx.Response(429) if len(sent) == 1 else reply()
    monkeypatch.setattr(httpx, 'post', post)
    client = PipelineLLMClient('openrouter', LUNA); events = []
    with observe_request_contracts(events.append):
        assert client.complete_json(instructions='PRIVATE_SOURCE', prompt='PRIVATE_PROMPT', schema_name='grader',
            schema={'type': 'object'}, max_output_tokens=4096, agent_role='benchmark_pilot_assessment') == {}
    attempts = client.last_execution['request_contract_attempts']
    assert len(attempts) == 2 and [r['attempt_index'] for r in attempts] == [1, 2]
    assert [r['http_status'] for r in attempts] == [429, 200]
    assert len(events) == 4 and all(r['request_contract']['reasoning'] == {'present': False} for r in attempts)
    assert all(p['max_tokens'] == 4096 and 'reasoning' not in p for p in sent)
    assert 'PRIVATE_' not in json.dumps(attempts)


@pytest.mark.parametrize('kind', ['contract', 'length'])
def test_actual_low_aux_failure_v2_persists_and_continues_single_low_final(monkeypatch, kind):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PRIVATE_FAKE_KEY')
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS', '8192')
    monkeypatch.delenv('OPENROUTER_PROVIDER', raising=False)
    calls = []
    def post(*args, **kwargs):
        p = kwargs['json']; calls.append(copy.deepcopy(p))
        if 'response_format' in p:
            if kind == 'length':
                return reply('', 'length')
            return reply(json.dumps({'quotes': [{'quote_id': 'Q1', 'candidate_id': 'C999999'}],
                                     'mentions': [], 'relations': [], 'limitations': 'Invalid exact quote.'}))
        return reply('Qualified answer.')
    monkeypatch.setattr(httpx, 'post', post)
    db, audit, case, adapter = setup_target()
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        'output_token_limit': 8192, 'reasoning_effort': 'low', 'identity_analysis_output_token_limit': 8192,
        'identity_analysis_reasoning_effort': 'low', 'identity_analysis_failure_policy': 'continue_without_advisory'})
    try:
        response = adapter.answer(case, audit)
        assert len(calls) == 2 and all(p['max_tokens'] == 8192 and p['reasoning'] == {'effort': 'low'} for p in calls)
        assert all('BAD_QUOTE' not in str(p['messages']) for p in calls[1:])
        meta = response.execution_metadata.model_dump(mode='json')
        assert meta['request_contract']['role'] == 'target_answer'
        assert meta['requested_reasoning_effort'] == 'low'
        assert meta['identity_analysis']['status'] == 'degraded_without_advisory'
        refused = meta['identity_analysis']['failure_receipt']
        assert refused['version'] == 'target-identity-failure-receipt-v2'
        assert meta['memory_input']['identity_failure_receipt_sha256'] and meta['memory_input']['identity_advisory_sha256'] is None
        stage = db.scalars(select(AgentExecutionModel)).first()
        persisted = agent_execution_schema(stage)
        assert persisted['status'] == 'failed' and recorded_identity_failure_matches(refused, persisted)
        bad = copy.deepcopy(persisted); bad['error_diagnostics'].pop('request_contract_sha256')
        assert not recorded_identity_failure_matches(refused, bad)
        assert 'PRIVATE_' not in json.dumps(persisted, default=str)
    finally:
        db.close()


def test_low_missing_wire_cannot_use_legacy_failure_receipt(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PRIVATE_FAKE_KEY')
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS', '8192')
    # Deliberately bypass wire transport: a kwargs/meter-only trace cannot prove low was sent.
    def fake(self, **kwargs):
        from app.extraction.llm import _PIPELINE_METER
        _PIPELINE_METER.get().update(last_http_status=200, reported_model=LUNA, request_attempts=1,
            failed_http_attempts=0, reported_finish_reason='length', response_choice_count=1)
        raise PipelineRequestError('Synthetic truncation')
    monkeypatch.setattr(PipelineLLMClient, '_complete_json', fake)
    analyzer = TargetIdentityEvidenceAnalyzer('openrouter', LUNA)
    with pytest.raises(PipelineRequestError):
        analyzer.analyze(question='Compare accounts', context=['PRIVATE_SOURCE'], max_output_tokens=8192, reasoning_effort='low')
    assert build_identity_failure_receipt(observation=analyzer.last_observation, provider='openrouter', model=LUNA,
        max_output_tokens=8192, reasoning_effort='low') is None


def test_low_final_length_failure_retains_actual_contract(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PRIVATE_FAKE_KEY')
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs['json'])
        return reply('', 'length')
    monkeypatch.setattr(httpx, 'post', post)
    db, audit, case, adapter = setup_target(mode='off')
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        'output_token_limit': 8192, 'reasoning_effort': 'low'})
    try:
        with pytest.raises(HTTPException) as got:
            adapter.answer(case, audit)
        failure = got.value.target_execution
        assert failure['finish_reason'] == 'length' and failure['requested_output_token_limit'] == 8192
        assert failure['requested_reasoning_effort'] == 'low'
        assert failure['request_contract']['reasoning'] == {'present': True, 'value': {'effort': 'low'}}
        assert len(failure['request_contract_attempts']) == len(calls) == 1
        assert 'PRIVATE_' not in json.dumps(failure)
    finally:
        db.close()


def test_new_wire_default_remains_fail_closed(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PRIVATE_FAKE_KEY')
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS', '8192')
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return reply('', 'length')
    monkeypatch.setattr(httpx, 'post', post)
    db, audit, case, adapter = setup_target()
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        'output_token_limit': 8192, 'reasoning_effort': 'low', 'identity_analysis_output_token_limit': 8192,
        'identity_analysis_reasoning_effort': 'low'})
    try:
        with pytest.raises(PipelineRequestError):
            adapter.answer(case, audit)
        assert len(sent) == 1 and 'response_format' in sent[0]
        persisted = agent_execution_schema(db.scalars(select(AgentExecutionModel)).first())
        assert persisted['status'] == 'failed' and persisted['error_diagnostics']['request_contract_sha256']
    finally:
        db.close()


def test_nested_observers_restore_and_no_observer_error_on_success():
    outer = []; inner = []; receipts = []
    def send(): return reply('Answer')
    with observe_request_contracts(outer.append):
        with observe_request_contracts(inner.append):
            send_with_request_contract(url=CHAT_COMPLETIONS_URL, payload=payload('low'), role='target_answer',
                                       attempt_index=1, collector=receipts, send=send)
        send_with_request_contract(url=CHAT_COMPLETIONS_URL, payload=payload(None), role='target_answer',
                                   attempt_index=2, collector=receipts, send=send)
    assert len(outer) == len(inner) == 2
    assert inner[0]['request_contract']['reasoning']['present'] is True
    assert outer[0]['request_contract']['reasoning']['present'] is False
    assert all('observer_error_type' not in r for r in receipts)


@pytest.mark.parametrize('weak', [False, True])
def test_both_arms_use_same_explicit_final_controls(monkeypatch, weak):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'PRIVATE_FAKE_KEY')
    observed = []
    def post(*args, **kwargs):
        observed.append(kwargs['json'])
        return reply('Answer.')
    monkeypatch.setattr(httpx, 'post', post)
    db, audit, case, adapter = setup_target(mode='off', weak=weak)
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        'output_token_limit': 8192, 'reasoning_effort': 'low'})
    try:
        result = adapter.answer(case, audit)
        assert len(observed) == 1 and observed[0]['reasoning'] == {'effort': 'low'}
        assert observed[0]['max_tokens'] == result.execution_metadata.requested_output_token_limit == 8192
    finally:
        db.close()


def test_unsupported_profile_blocked_before_auxiliary_dispatch(monkeypatch):
    from app.schemas import TargetProvider
    calls = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: calls.append(True))
    db, audit, case, adapter = setup_target()
    audit.provider = TargetProvider.OPENAI
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={'reasoning_effort': 'low'})
    try:
        with pytest.raises(HTTPException) as rejected:
            adapter.answer(case, audit)
        assert rejected.value.status_code == 422 and calls == []
    finally:
        db.close()


def test_contract_rejects_unexpected_nested_request_secrets():
    p = payload('low'); p['reasoning']['api_key'] = 'PRIVATE_SECRET'
    with pytest.raises(ValueError, match='Unsupported reasoning'):
        build_openrouter_request_contract(url=CHAT_COMPLETIONS_URL, payload=p, role='target_answer')
