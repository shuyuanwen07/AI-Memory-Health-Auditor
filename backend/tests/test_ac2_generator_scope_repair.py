"""Regression cases for source-backed question scope without answer leakage."""
from app.schemas import Memory
from app.test_generator.rule_based import RuleBasedTestGenerator as Generator


def memory(ident, text):
    return Memory(memory_id=ident, conversation_id='fixture', canonical_value=text,
                  status='confirmed', source_message_ids=['source'])


def test_conflict_scope_requires_both_endpoints_and_does_not_reveal_answer():
    first = memory('a', 'For the Cedar event an active site plan says the venue is the greenhouse.')
    other = memory('b', 'An unrelated site plan says the venue is the courtyard.')
    same = memory('c', 'For the Cedar event a signed booking says the venue is the courtyard.')
    answer_is_name = memory('d', 'For the Cedar event a signed booking says the venue is Cedar.')
    assert 'cedar' not in Generator._explicit_conflict_resolution(first, other)[1].lower()
    assert 'cedar' in Generator._explicit_conflict_resolution(first, same)[1].lower()
    assert 'cedar' not in Generator._explicit_conflict_resolution(first, answer_is_name)[1].lower()


def test_restrictive_subject_is_not_copied_into_question():
    assert Generator._source_subject(memory('a', 'The only permitted colour is purple.')) is None
    assert Generator._source_subject(memory('b', 'The approved supplier is Orion.')) is None
    assert Generator._source_subject(memory('c', 'The reading room notice has a violet border.')) == 'The reading room notice'
