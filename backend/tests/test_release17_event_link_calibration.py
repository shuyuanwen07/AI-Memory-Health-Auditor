"""Static reader calibration and immutable anonymous sources; not model quality tests."""
import copy
import json

import pytest

from app.schemas import Dimension, TargetConfiguration, TestCase as Case
from app.target_ai.rule_based import private_context_instruction, selected_memory_context


def sample(question='Do these accounts describe the same occurrence?', advisory=None):
    return Case(test_id='ANONYMOUS', run_id='OFFLINE', dimension=Dimension.ACCURACY,
                prompt=question, expected_behavior='ORACLE_NOT_TARGET_INPUT',
                supporting_memory_ids=['PRIVATE_EXPECTED_ID'], generator_version='synthetic',
                target_memory_context=[
                    'A colleague described an exhibition at a converted station.',
                    'A later account described an exhibition at a converted station.'],
                target_identity_evidence=advisory)


@pytest.mark.parametrize('configuration', list(TargetConfiguration))
def test_event_link_rule_is_shared_and_relation_local(configuration):
    text = private_context_instruction(sample(), configuration)
    assert 'When historical event identity is asked or used' in text
    assert 'label each cross-source same-event link explicit, likely or possible beside that link' in text
    assert 'Explicit requires a direct source assertion of the link or unambiguous same-occurrence coreference' in text
    assert 'Matching person, title, medium, venue or date alone is inferential evidence' in text
    assert 'a disclaimer elsewhere does not qualify an unqualified same-event assertion' in text
    assert 'supported as the same event' in text
    assert 'These labels concern event links, not every ordinary fact' in text
    assert 'keep likely or possible beside an inferred link' in text


def test_auxiliary_explicit_remains_proposal_and_advisory_is_not_rewritten():
    advisory = {'relations': [{'level': 'explicit', 'cues': ['shared_venue_only']}],
                'limitations': 'Synthetic proposal, not a source assertion.'}
    test = sample(advisory=advisory)
    before = copy.deepcopy(test.model_dump())
    text = private_context_instruction(test, TargetConfiguration.STRONG)
    assert 'An auxiliary explicit label is only a proposal' in text
    assert 'unless the quoted source establishes the direct link or unambiguous same-occurrence coreference' in text
    assert json.dumps(advisory, ensure_ascii=False, sort_keys=True, separators=(',', ':')) in text
    assert test.model_dump() == before
    assert 'No memory has been merged by this analysis' in text


@pytest.mark.parametrize('question', ['Where was the event?', 'When did I attend?',
                                    'Which accounts likely refer to the same event?'])
def test_sources_and_question_are_immutable_and_existing_safety_limits_remain(question):
    test = sample(question)
    before = copy.deepcopy(test.model_dump())
    context = selected_memory_context(test, TargetConfiguration.STRONG)
    text = private_context_instruction(test, TargetConfiguration.STRONG)
    assert context == test.target_memory_context
    assert test.model_dump() == before
    assert 'ORACLE_NOT_TARGET_INPUT' not in text and 'PRIVATE_EXPECTED_ID' not in text
    assert 'Plans and wishes do not establish completed actions' in text
    assert 'Keep initial and later states separate' in text
    assert 'Qualitative recency can support a labelled rough time inference, not confirmed calendar membership' in text
    temporal_text = private_context_instruction(sample('Which happened earlier?'), TargetConfiguration.STRONG)
    assert 'Check disjoint candidate_ranges separately' in temporal_text
    assert 'Keep conditional assumptions beside the claim' in text
    assert 'an auxiliary' in text.lower()
