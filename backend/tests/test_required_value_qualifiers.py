"""Development regressions: a shared object noun cannot satisfy a requirement."""
from datetime import datetime, timezone

import pytest

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Dimension, Memory, MemoryRelationship, MemoryStatus, RelationshipType, TargetResponse, TestCase


def evaluate(expected, answer, *, dimension=Dimension.APPROPRIATE_USE, memories=None):
    test = TestCase(test_id='T-qualifier', run_id='R-qualifier', dimension=dimension,
                    prompt='Which requirement applies to the current task?', expected_behavior=expected,
                    supporting_memory_ids=['M001', 'M002'], generator_version='development-fixture')
    response = TargetResponse(response_id='A-qualifier', test_id=test.test_id, run_id=test.run_id,
                              response_text=answer, model='development-fixture', temperature=0,
                              created_at=datetime.now(timezone.utc))
    return RuleBasedBehaviourEvaluator().evaluate(test, response, memories or [])


@pytest.mark.parametrize('required,incorrect,correct,short', [
    ('grayscale charts', 'Use colourful charts.', 'Use grayscale charts.', 'Grayscale.'),
    ('encrypted backups', 'Keep unencrypted backups.', 'Keep encrypted backups.', 'Encrypted.'),
    ('signed PDF documents', 'Submit unsigned PDF documents.', 'Submit signed PDF documents.', 'Signed PDF.'),
    ('landscape pages', 'Use portrait pages.', 'Use landscape pages.', 'Landscape.'),
])
def test_required_qualifier_is_not_replaced_by_the_shared_noun(required, incorrect, correct, short):
    expected = f'The current project submission requires {required}.'
    assert evaluate(expected, incorrect).passed is False
    assert evaluate(expected, correct).passed is True
    assert evaluate(expected, short).passed is True


@pytest.mark.parametrize('answer', [
    'Do not use grayscale charts; use colourful charts.',
    'Use colourful charts rather than grayscale charts.',
])
def test_mentioning_the_required_qualifier_under_negation_does_not_pass(answer):
    assert evaluate('The submission requires grayscale charts.', answer).passed is False


def test_observed_preference_override_failure_is_classified_from_linked_relationship():
    general = Memory(memory_id='M001', conversation_id='C', canonical_value='I generally prefer colourful charts in my working notes',
                     status=MemoryStatus.CONFIRMED, source_message_ids=['S1'])
    required = Memory(memory_id='M002', conversation_id='C', canonical_value='The current Pebble print submission requires grayscale charts',
                      status=MemoryStatus.CONFIRMED, source_message_ids=['S2'],
                      relationships=[MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE, target_memory_id='M001')])
    result = evaluate('Follow the contextual requirement: The current Pebble print submission requires grayscale charts.',
                      'Based on the retrieved record, I generally prefer colourful charts in my working notes',
                      memories=[general, required])
    assert result.passed is False
    assert result.failure_type == Dimension.APPROPRIATE_USE
    assert result.failure_classification.status == 'classified'


def test_missing_qualifier_without_override_evidence_does_not_invent_a_failure_category():
    result = evaluate('The submission requires grayscale charts.', 'Use colourful charts.')
    assert result.passed is False
    assert result.failure_type is None
    assert result.failure_classification.status == 'unclassified'


def test_describing_the_general_preference_then_applying_the_task_requirement_passes():
    assert evaluate('The submission requires grayscale charts.',
                    'The usual preference is colourful charts, but use grayscale for this submission.').passed is True
