"""Synthetic profile validation; no HTTP or provider credentials."""
import pytest
from pydantic import ValidationError
from app.schemas import AuditCreate
from app.schemas.target_profile import TargetMemoryProfile


def create(**updates):
    return AuditCreate(conversation_id='SYN-PROFILE', target_configuration='strong', **updates)


def test_default_profile_preserves_historical_representation():
    profile = TargetMemoryProfile()
    assert profile.answer_validation == 'off'
    assert not any(key.startswith('answer_validation') for key in profile.model_dump(mode='json'))


def test_opt_in_round_trip_preserves_independent_budget_and_effort():
    profile = TargetMemoryProfile(answer_validation='source_grounding',
        answer_validation_output_token_limit=6144, answer_validation_reasoning_effort='low')
    saved = profile.model_dump(mode='json')
    assert saved['answer_validation'] == 'source_grounding'
    assert saved['answer_validation_output_token_limit'] == 6144
    assert saved['answer_validation_reasoning_effort'] == 'low'
    assert TargetMemoryProfile.model_validate(saved) == profile


@pytest.mark.parametrize('value', [0, 511, 8193, True, '8192'])
def test_output_budget_is_bounded_strict_integer(value):
    with pytest.raises(ValidationError):
        TargetMemoryProfile(answer_validation_output_token_limit=value)


@pytest.mark.parametrize('provider,model,adapter', [
    ('rule_based', 'rule-based-target-ai', 'controlled-memory'),
    ('openai', 'gpt-6-luna', 'controlled-memory'),
    ('openrouter', 'another-model', 'controlled-memory'),
    ('openrouter', 'openai/gpt-6-luna', 'external-http'),
])
def test_opt_in_rejects_unsupported_target(provider, model, adapter):
    with pytest.raises(ValidationError, match='Answer source validation requires'):
        create(provider=provider, model=model, target_system_adapter=adapter,
               target_memory_profile={'answer_validation': 'source_grounding'})


def test_explicit_supported_target_is_accepted():
    audit = create(provider='openrouter', model='openai/gpt-6-luna',
                   target_memory_profile={'answer_validation': 'source_grounding'})
    assert audit.target_memory_profile.answer_validation == 'source_grounding'


def test_comparison_description_discloses_recorded_check_without_relabelling_legacy():
    from app.services.audit_comparison import profile_description
    legacy = TargetMemoryProfile().model_dump(mode='json')
    assert 'answer source check' not in profile_description(legacy)
    checked = {**legacy, 'answer_validation': 'source_grounding',
               'answer_validation_output_token_limit': 6144,
               'answer_validation_reasoning_effort': 'medium'}
    description = profile_description(checked)
    assert 'answer source check source_grounding' in description
    assert 'answer check limit 6144 tokens' in description
    assert 'answer check reasoning medium' in description
