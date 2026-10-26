"""Anonymous instruction scope contracts, not temporal truth or model quality tests."""
import copy

import pytest
from app.schemas import Dimension, TargetConfiguration, TestCase as Case
from app.target_ai.rule_based import private_context_instruction, selected_memory_context


def sample(question, context):
    return Case(test_id='ANONYMOUS', run_id='OFFLINE', dimension=Dimension.ACCURACY,
                prompt=question, expected_behavior='PRIVATE_ORACLE',
                supporting_memory_ids=['PRIVATE_EXPECTED_ID'], generator_version='synthetic',
                target_memory_context=context)


@pytest.mark.parametrize('configuration', list(TargetConfiguration))
def test_confidence_consistency_is_per_claim_not_blanket(configuration):
    text = private_context_instruction(sample('What do the records say?', ['An explicitly dated fact.']), configuration)
    assert 'for each individual claim, the lead, ledger and explanation must use the same confidence level' in text
    assert 'Confirmed facts and separately labelled candidate placements may have different confidence' in text
    assert 'label each cross-source same-event link explicit, likely or possible beside that link' in text
    assert 'Explicit requires a direct source assertion of the link or unambiguous same-occurrence coreference' in text


@pytest.mark.parametrize('context', [
    ['I attended a recital on its stated date.', 'I just returned from a separate exhibition.'],
    ['I recalled an old recital today.', 'I plan to attend an exhibition.'],
    ['I returned from a long trip today; the recital was near its beginning.', 'The other visit has no date.'],
])
def test_candidate_interleaving_is_optional_and_locally_conditioned_with_no_forced_complete_order(context):
    test = sample('Which happened earlier?', context)
    before = copy.deepcopy(test.model_dump())
    text = private_context_instruction(test, TargetConfiguration.STRONG)
    assert 'supported placement means supplied positive event-time evidence plus a stated recency or proximity assumption' in text
    assert 'not necessarily a proven pairwise order' in text
    assert 'If several interleavings are equally supported, show alternatives rather than assert a unique likely order' in text
    assert 'keep events without such anchors unplaced or in a partial order' in text
    assert 'give the firm partial order separately from any optional candidate interleaving' in text
    assert 'Do not present candidate placements as confirmed dates' in text
    assert 'followed by at most one short sentence of reasoning' not in text
    assert 'A return can follow a long trip; an explicit earlier event date takes precedence' in text
    assert 'A plan, bare mention or recollection alone supplies no event-time anchor' in text
    assert 'Check disjoint candidate_ranges separately' in text
    assert 'Missing event clauses cannot be supplied by a source ID' in text
    assert selected_memory_context(test, TargetConfiguration.STRONG) == context
    assert test.model_dump() == before
    assert 'PRIVATE_ORACLE' not in text and 'PRIVATE_EXPECTED_ID' not in text


def test_nonchronology_and_counting_formats_keep_their_own_scope():
    plain = private_context_instruction(sample('Where is the workshop?', ['The workshop is in a hall.']), TargetConfiguration.STRONG)
    count = private_context_instruction(sample('How many events did I attend this year?', ['I attended one event.']), TargetConfiguration.STRONG)
    assert 'followed by at most one short sentence of reasoning' in plain
    assert 'optional candidate interleaving' not in plain
    assert 'use the compact ledger and supported subtotal format' in count
    assert 'For a chronology request' not in count
    assert 'A confirmed subtotal requires every member' in count
    assert 'A chain containing a possible link cannot establish a confirmed or likely group' in count
    assert 'Plans and wishes do not establish completed actions' in count
    assert 'Keep initial and later states separate' in count
