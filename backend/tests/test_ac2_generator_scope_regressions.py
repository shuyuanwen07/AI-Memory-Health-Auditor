"""Adversarial checks on the delivered generator, not independent validity evidence."""
from app.schemas import Memory
from app.test_generator.rule_based import RuleBasedTestGenerator as Generator


def memory(ident, text):
    return Memory(memory_id=ident, conversation_id='scope-fixture', canonical_value=text,
                  status='confirmed', source_message_ids=['source'])


def test_event_anchor_does_not_leak_answer():
    item = memory('a', 'For the Aurora event the venue is Aurora.')
    assert 'aurora' not in Generator._accuracy(item)[1].lower()


def test_conflict_scope_requires_both_sources_and_must_not_be_an_answer():
    first = memory('a', 'For the Cedar event an active site plan says the venue is the greenhouse.')
    unrelated = memory('b', 'An unrelated site plan says the venue is the courtyard.')
    matching = memory('c', 'For the Cedar event a signed booking says the venue is the courtyard.')
    leaking = memory('d', 'For the Cedar event a signed booking says the venue is Cedar.')
    assert 'cedar' not in Generator._explicit_conflict_resolution(first, unrelated)[1].lower()
    assert 'cedar' in Generator._explicit_conflict_resolution(first, matching)[1].lower()
    assert 'cedar' not in Generator._explicit_conflict_resolution(first, leaking)[1].lower()


def test_subject_cue_does_not_include_restrictive_judgment():
    assert Generator._source_subject(memory('a', 'The only permitted colour is purple.')) is None
    assert Generator._source_subject(memory('b', 'The approved supplier is Orion.')) is None
    assert Generator._source_subject(memory('c', 'The reading room notice has a violet border.')) == 'The reading room notice'


def test_scenario_phrase_does_not_contain_answer():
    first = memory('a', 'In the orchard survey scenario: The plan says the final signal is orchard.')
    second = memory('b', 'In the orchard survey scenario: The report says the final signal is cyan.')
    assert 'orchard survey' not in Generator._explicit_conflict_resolution(first, second)[1].lower()
