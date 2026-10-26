"""Explicit medium target control with unchanged low auxiliary/omitted grading; offline only."""
import copy
import json
from pathlib import Path
import sys

import httpx
import pytest

from app.schemas.domain import ExecutionMetadata
from app.schemas.request_contracts import wire_metadata
from app.schemas.target_profile import TargetMemoryProfile
from app.target_ai.openrouter import build_openrouter_target_payload, CHAT_COMPLETIONS_URL, validate_reasoning_effort
from app.target_ai.request_contracts import (request_contract_sha256,
    request_contract_metadata, send_with_request_contract)
from test_target_identity_integration import setup_target
from test_release09_request_contracts import reply

sys.path.insert(0, str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2] / 'scripts'))
from stability_configuration import role_settings
from stability_request_contracts import expected_contract, validate_contract

ROUTING = {'require_parameters': True, 'allow_fallbacks': False}
LUNA = 'openai/gpt-6-luna'


def protocol(arm='strong_rule_based', effort='medium'):
    return {'model': LUNA, 'strategies': [arm], 'output_token_limit': 8192,
        'grading_output_token_limit': 4096,
        'target_memory_profile': {'reasoning_effort': effort,
            'identity_analysis_output_token_limit': 8192, 'identity_analysis_reasoning_effort': 'low'}}


def test_profile_target_medium_aux_low_and_legacy_omission():
    assert TargetMemoryProfile(reasoning_effort='medium').reasoning_effort == 'medium'
    with pytest.raises(ValueError):
        TargetMemoryProfile(identity_analysis_reasoning_effort='medium')
    assert 'reasoning_effort' not in TargetMemoryProfile().model_dump(mode='json')
    assert 'requested_reasoning_effort' not in ExecutionMetadata().model_dump(mode='json')
    for invalid in ('high', 'none', '', False):
        with pytest.raises(ValueError):
            TargetMemoryProfile(reasoning_effort=invalid)
    for provider, model in [('openai', LUNA), ('openrouter', 'other')]:
        with pytest.raises(ValueError):
            validate_reasoning_effort(provider, model, 'medium')


@pytest.mark.parametrize('arm', ['weak_first_hit', 'strong_rule_based'])
def test_three_role_contracts_and_replay_exact_effort(arm):
    p = protocol(arm)
    for role, cap, effort in [('target_answer', 8192, 'medium'),
            ('target_identity_evidence', 8192, 'low'), ('benchmark_pilot_assessment', 4096, None)]:
        assert role_settings(p, role) == {'output_token_limit': cap, 'reasoning_effort': effort}
        kwargs = {} if role == 'target_answer' else {'schema_name': role, 'schema': {'type': 'object'}}
        c = expected_contract(p, role, instructions='source', prompt='question', provider_options=ROUTING, **kwargs)
        validate_contract(p, role, c)
        assert c == expected_contract(copy.deepcopy(p), role, instructions='source', prompt='question', provider_options=ROUTING, **kwargs)
        bad = copy.deepcopy(c)
        bad['reasoning'] = {'present': True, 'value': {'effort': 'low' if effort == 'medium' else 'medium'}}
        with pytest.raises(ValueError):
            validate_contract(p, role, bad)
    p['target_memory_profile']['identity_analysis_reasoning_effort'] = 'medium'
    with pytest.raises(ValueError):
        role_settings(p, 'target_identity_evidence')


def test_actual_attempt_medium_survives_typed_receipts_and_sanitizer():
    p = build_openrouter_target_payload(model=LUNA, instructions='source', prompt='question',
        temperature=0, max_output_tokens=8192, reasoning_effort='medium', provider_options=ROUTING)
    attempts = []
    send_with_request_contract(url=CHAT_COMPLETIONS_URL, payload=p, role='target_answer', attempt_index=1,
        collector=attempts, send=lambda: reply('Answer'))
    raw = request_contract_metadata(attempts)
    assert raw['requested_reasoning_effort'] == 'medium'
    safe = wire_metadata(raw)
    assert safe['requested_reasoning_effort'] == 'medium'
    typed = ExecutionMetadata(**safe).model_dump(mode='json')
    assert typed['requested_reasoning_effort'] == 'medium'
    assert typed['request_contract']['reasoning'] == {'present': True, 'value': {'effort': 'medium'}}
    assert typed['request_contract_sha256'] == request_contract_sha256(typed['request_contract'])


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_live_adapter_failure_keeps_low_aux_v2_and_medium_final(monkeypatch, finish):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'SYNTHETIC_NOT_A_REAL_KEY')
    monkeypatch.setenv('PIPELINE_MAX_OUTPUT_TOKENS', '8192')
    monkeypatch.delenv('OPENROUTER_PROVIDER', raising=False)
    calls = []
    def post(*args, **kwargs):
        p = kwargs['json']; calls.append(copy.deepcopy(p))
        if 'response_format' in p:
            if finish == 'length':
                return reply('', 'length')
            return reply(json.dumps({'quotes': [{'quote_id':'Q1','candidate_id':'C999999'}],
                'mentions': [], 'relations': [], 'limitations': 'invalid exact quote'}))
        return reply('Qualified answer.')
    monkeypatch.setattr(httpx, 'post', post)
    db, audit, case, adapter = setup_target()
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        'reasoning_effort':'medium','output_token_limit':8192,
        'identity_analysis_reasoning_effort':'low','identity_analysis_output_token_limit':8192,
        'identity_analysis_failure_policy':'continue_without_advisory'})
    try:
        response = adapter.answer(case, audit)
        assert [p['reasoning'] for p in calls] == [{'effort':'low'}, {'effort':'medium'}]
        assert all(p['max_tokens'] == 8192 for p in calls)
        meta = response.execution_metadata.model_dump(mode='json')
        assert meta['requested_reasoning_effort'] == 'medium'
        failure = meta['identity_analysis']['failure_receipt']
        assert failure['version'] == 'target-identity-failure-receipt-v2'
        assert failure['reasoning'] == {'present':True,'value':{'effort':'low'}}
        assert 'BAD_QUOTE' not in str(calls[-1]['messages'])
    finally:
        db.close()


def test_truncated_medium_final_failure_preserves_request(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv('OPENROUTER_API_KEY', 'SYNTHETIC_NOT_A_REAL_KEY')
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: reply('', 'length'))
    db, audit, case, adapter = setup_target(mode='off')
    audit.target_memory_profile = audit.target_memory_profile.model_copy(update={
        'output_token_limit':8192, 'reasoning_effort':'medium'})
    try:
        with pytest.raises(HTTPException) as got:
            adapter.answer(case, audit)
        failure = got.value.target_execution
        assert failure['requested_reasoning_effort'] == 'medium'
        assert failure['requested_output_token_limit'] == 8192
        assert failure['request_contract']['reasoning'] == {'present':True,'value':{'effort':'medium'}}
        assert len(failure['request_contract_attempts']) == 1
    finally:
        db.close()
