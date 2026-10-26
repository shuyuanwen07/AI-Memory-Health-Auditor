"""Scope of static reader instructions; anonymous sources, no model-compliance claim."""
import copy

import pytest

from app.schemas import Dimension, TargetConfiguration, TestCase as Case
from app.target_ai.rule_based import private_context_instruction, selected_memory_context


def sample(context):
    return Case(test_id='ANONYMOUS', run_id='OFFLINE', dimension=Dimension.ACCURACY,
                prompt='Which happened earlier?', expected_behavior='EVALUATOR_PRIVATE',
                supporting_memory_ids=['PRIVATE_EXPECTATION'], generator_version='synthetic',
                target_memory_context=context)


@pytest.mark.parametrize('configuration', list(TargetConfiguration))
def test_same_occurrence_identity_and_distinct_event_chronology_have_separate_scope(configuration):
    text = private_context_instruction(sample(['I attended a recital.', 'I visited an exhibition.']), configuration)
    assert 'direct-coreference requirements govern whether descriptions refer to the same event' in text
    assert 'separately from ordering already distinct events' in text
    assert 'A placement needs a positive source anchor, not an explicit same-event link to another event' in text
    assert 'Do not apply that same-event identity test as a requirement for a qualified order of distinct events' in text
    assert 'label each cross-source same-event link explicit, likely or possible beside that link' in text
    assert 'Matching person, title, medium, venue or date alone is inferential evidence' in text


@pytest.mark.parametrize('context', [
    ['I attended a recital on the stated date.', 'I just returned from a different exhibition.'],
    ['I recalled an old exhibition today.', 'I just returned from a long trip; the recital was near its beginning.'],
    ['I plan to visit an exhibition.', 'I attended a recital, but gave no date.'],
])
def test_positive_recency_and_negative_recall_long_trip_limits_are_preserved(context):
    test = sample(context)
    before = copy.deepcopy(test.model_dump())
    text = private_context_instruction(test, TargetConfiguration.STRONG)
    assert 'separate confirmed dates from a proposed likely timeline' in text
    assert 'state each local recency assumption beside its placement' in text
    assert 'keep events without such anchors unplaced or in a partial order' in text
    assert 'leave unsupported placements unresolved rather than force a complete timeline' in text
    assert 'Positive recency about an experienced event' in text
    assert 'a qualified rough elapsed time or likely order around its own source observation' in text
    assert 'A return can follow a long trip; an explicit earlier event date takes precedence' in text
    assert 'A plan, bare mention or recollection alone supplies no event-time anchor' in text
    assert 'Missing event clauses cannot be supplied by a source ID' in text
    assert 'Exact dates need their own evidence' in text
    assert selected_memory_context(test, TargetConfiguration.STRONG) == context
    assert test.model_dump() == before
    assert 'EVALUATOR_PRIVATE' not in text and 'PRIVATE_EXPECTATION' not in text
