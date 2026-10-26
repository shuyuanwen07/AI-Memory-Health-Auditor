"""Reader contract regressions; synthetic inputs, no model-quality claims."""
import pytest

from app.schemas import Dimension, TargetConfiguration, TestCase
from app.target_ai.rule_based import private_context_instruction


def instruction(question, configuration=TargetConfiguration.STRONG):
    case = TestCase(
        test_id='T10', run_id='RUN10', dimension=Dimension.ACCURACY,
        supporting_memory_ids=[], generator_version='synthetic-unit-test',
        prompt=question, target_memory_context=['I like quiet gardens'],
        expected_behavior='PRIVATE_REFERENCE_DO_NOT_SEND',
    )
    result = private_context_instruction(case, configuration)
    assert 'PRIVATE_REFERENCE_DO_NOT_SEND' not in result
    return result


@pytest.mark.parametrize('configuration', list(TargetConfiguration))
def test_recommendation_permission_is_not_a_personal_fact_or_verified_claim(configuration):
    result = instruction('Could you recommend a place for my next trip?', configuration)
    assert 'named candidate from general knowledge' in result
    assert 'exception for proposing a new option, not for answering personal facts' in result
    assert 'current features, price or availability are verified' in result
    assert 'clearly unverified recommendation candidates' in result


def test_numeric_comparison_checks_all_candidates_and_correct_measure():
    result = instruction('Which channel grew most last quarter?')
    assert 'current total from an increase' in result
    assert 'percentage from an absolute change' in result
    assert 'Check every supplied candidate' in result
    assert 'final name, number and short explanation must agree' in result
    assert 'missing baselines or incompatible periods explicit' in result


def test_temporal_comparison_binds_actor_to_date_without_inventing_year():
    result = instruction('Who started earlier?')
    assert "each actor with that actor's own date or interval" in result
    assert 'do not reverse the conclusion' in result
    assert 'common year is only inferred' in result


def test_metric_aggregation_keeps_conditional_identity_and_no_double_counting():
    result = instruction('How many points and bonuses did I earn?')
    assert 'distinguish metric aggregation from counting distinct events' in result
    assert 'identity assumption stated alongside it' in result
    assert 'Keep a possible-only link unresolved' in result
    assert 'duplicate cumulative reports, different periods or mismatched entities' in result
    assert 'A likely group must not silently determine an exact overall count' in result


def test_auxiliary_identity_instructions_apply_role_limit_to_every_field():
    from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
    assert 'every field, including limitations' in TargetIdentityEvidenceAnalyzer.INSTRUCTIONS
    assert 'Do not decide whether the final reader can answer' in TargetIdentityEvidenceAnalyzer.INSTRUCTIONS
