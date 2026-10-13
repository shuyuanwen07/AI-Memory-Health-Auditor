from datetime import datetime, timezone, timedelta

import pytest

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import Conversation, ConversationMessage, MemoryStatus, RelationshipType


def extract(*messages):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return RuleBasedMemoryExtractor().extract(Conversation(
        conversation_id='C', authorised=True, created_at=base,
        messages=[ConversationMessage(message_id=f'S{i}', role='user', content=text,
                                      timestamp=base + timedelta(minutes=i))
                  for i, text in enumerate(messages)],
    ))


@pytest.mark.parametrize('same_message', [True, False])
def test_explicit_withdrawal_keeps_replacement_scope_and_original_provenance(same_message):
    old = 'The Maple review meeting must use Zoom only.'
    correction = 'Correction: the Zoom requirement is withdrawn; use Teams instead.'
    memories = extract(old + ' ' + correction) if same_message else extract(old, correction)
    assert len(memories) == 2
    current = memories[-1]
    assert 'Maple review meeting' in current.canonical_value
    assert 'requires Teams' in current.canonical_value
    assert [(r.type, r.target_memory_id) for r in current.relationships] == [(RelationshipType.UPDATE, memories[0].memory_id)]
    assert current.source_message_ids == (['S0'] if same_message else ['S0', 'S1'])


def test_ambiguous_project_withdrawal_does_not_choose_a_project_arbitrarily():
    memories = extract('The Maple review meeting must use Zoom only.',
                       'The Birch review meeting must use Zoom only.',
                       'Correction: the Zoom requirement is withdrawn; use Teams instead.')
    assert 'Teams' in memories[-1].canonical_value
    assert not memories[-1].relationships


def test_named_withdrawal_retires_only_the_named_projects_old_requirement():
    memories = extract('The Maple review meeting must use Zoom only.',
                       'The Birch review meeting must use Zoom only.',
                       'For the Maple project, the Zoom requirement is withdrawn; use Teams instead.')
    current = memories[-1]
    assert current.source_message_ids == ['S0', 'S2']
    assert [(r.type, r.target_memory_id) for r in current.relationships] == [(RelationshipType.UPDATE, memories[0].memory_id)]


@pytest.mark.parametrize('correction', [
    'The Zoom requirement is not withdrawn; use Teams instead.',
    'If the Zoom requirement is withdrawn; use Teams instead.',
    'The Zoom requirement may be withdrawn; use Teams instead.',
])
def test_conditional_or_denied_withdrawal_is_not_a_confirmed_replacement(correction):
    memories = extract('The Maple review meeting must use Zoom only.', correction)
    assert not any(r.type == RelationshipType.UPDATE for m in memories for r in m.relationships)


def test_explicit_replacement_generates_resolved_update_questions_not_clarification_probes():
    from app.schemas import AuditRun, AuditStatus, TargetConfiguration, TargetProvider, TestQualityStatus
    from app.test_generator.rule_based import RuleBasedTestGenerator
    from app.test_generator.quality import RuleBasedTestQualityValidator
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    memories = extract('The Maple review meeting must use Zoom only.',
                       'Correction: the Zoom requirement is withdrawn; use Teams instead.')
    for memory in memories:
        memory.status = MemoryStatus.CONFIRMED
    run = AuditRun(run_id='R', conversation_id='C', status=AuditStatus.CREATED,
                   target_configuration=TargetConfiguration.STRONG, provider=TargetProvider.RULE_BASED,
                   model='fixture', temperature=0, random_seed=42, test_budget=4,
                   prompt_template_version='fixture', created_at=datetime.now(timezone.utc))
    tests = RuleBasedTestGenerator().generate(memories, run)
    assert len(tests) == 3
    for test in tests:
        assert 'Maple' in test.prompt
        assert 'Zoom' not in test.prompt and 'Teams' not in test.prompt
        assert 'unresolved conflict' not in test.prompt
        assert RuleBasedTestQualityValidator().validate(test, memories).quality_status == TestQualityStatus.ACCEPTED
        assert RuleBasedBehaviourEvaluator._required_terms(RuleBasedBehaviourEvaluator._expected_statement(test.expected_behavior)) == ['teams']


@pytest.mark.parametrize('answer,passed', [
    ('Teams.', True),
    ('Use Zoom now. Teams is mentioned in the source.', False),
    ('The Maple review should use Zoom. Teams is the replacement.', False),
    ('Use Teams instead of the previously required Zoom.', True),
    ('Do not use Zoom. Use Teams.', True),
    ('The historical source requires Zoom, but the Maple review now requires Teams.', True),
    ('The Birch review must use Zoom. The Maple review must use Teams.', True),
])
def test_current_platform_recommendation_is_not_verified_by_an_incidental_keyword(answer, passed):
    from app.schemas import TestCase as Case, TargetResponse
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    memories = extract('The Maple review meeting must use Zoom only.',
                       'Correction: the Zoom requirement is withdrawn; use Teams instead.')
    for memory in memories:
        memory.status = MemoryStatus.CONFIRMED
    case = Case(test_id='T', run_id='R', dimension='freshness',
                prompt='Which meeting platform for the Maple project applies now?',
                expected_behavior='Use the current value: ' + memories[-1].canonical_value,
                supporting_memory_ids=[m.memory_id for m in memories], generator_version='fixture')
    response = TargetResponse(response_id='A', run_id='R', test_id='T', response_text=answer,
                              model='fixture', temperature=0, created_at=datetime.now(timezone.utc))
    assert RuleBasedBehaviourEvaluator().evaluate(case, response, memories).passed is passed


@pytest.mark.parametrize('value,terms', [('Microsoft Teams', ['teams']), ('Google Meet', ['google', 'meet'])])
def test_multiword_platform_replacements_keep_the_actual_required_value(value, terms):
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    memories = extract('The Maple review meeting must use Zoom only.',
                       f'Correction: the Zoom requirement is withdrawn; use {value} instead.')
    assert 'requires ' + value in memories[-1].canonical_value
    assert RuleBasedBehaviourEvaluator._required_terms(memories[-1].canonical_value) == terms
