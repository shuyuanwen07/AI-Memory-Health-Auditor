import pytest
from app.services.meeting_facts import exclusive_platform_value, is_meeting_platform_topic


@pytest.mark.parametrize(('text', 'expected'), [
    ('For the Laurel meeting, only Webex is allowed.', 'webex'),
    ('For the Laurel meeting, only Microsoft Teams is permitted.', 'teams'),
    ('For the Laurel meeting, only Google Meet will be allowed.', 'google meet'),
    ('Not only Zoom is allowed; Teams is allowed too.', None),
    ('If only Zoom is allowed, we will ask for clarification.', None),
    ('Perhaps only Teams is permitted.', None),
    ('Only Zoom is not allowed.', None),
    ('Which meeting platform is permitted?', None),
])
def test_positive_exclusive_platform_rules(text, expected):
    assert exclusive_platform_value(text) == expected


@pytest.mark.parametrize(('text', 'expected'), [
    ('For the Snowdrop meeting, only Google Meet is allowed.', True),
    ('Only Google Meet is allowed for the Snowdrop review.', True),
    ('Only Microsoft Teams is permitted for project calls.', True),
    ('Our conferences are held via Webex.', True),
    ('The review meeting is tomorrow. Kotlin is required for the project.', False),
    ('We use Google Meet. The project review is tomorrow.', False),
    ('Review Kotlin code before release.', False),
])
def test_meeting_topic_uses_bounded_clause_and_all_supported_names(text, expected):
    assert is_meeting_platform_topic(text) is expected

@pytest.mark.parametrize(('first', 'second', 'conflict'), [
    ('For the Clover review meeting, only Zoom is allowed.', 'Only Zoom is permitted for the Clover review meeting.', False),
    ('For the Clover review meeting, only Microsoft Teams is allowed.', 'For the Clover review meeting, only Teams is permitted.', False),
    ('For the Clover review meeting, only Google Meet is allowed.', 'Only Google Meet is allowed for the Clover review meeting.', False),
    ('For the Clover review meeting, only Zoom is allowed.', 'For the Clover review meeting, only Teams is allowed.', True),
])
def test_equivalent_requirements_do_not_invent_conflicts(first, second, conflict):
    from datetime import datetime, timedelta, timezone
    from app.schemas import AuditRun, AuditStatus, Conversation, ConversationMessage, RelationshipType, TargetConfiguration, TargetProvider
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.test_generator.rule_based import RuleBasedTestGenerator
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversation = Conversation(conversation_id='C-equivalent', authorised=True, created_at=now,
        messages=[ConversationMessage(message_id=f'S{i}', role='user', content=text,
            timestamp=now+timedelta(seconds=i)) for i, text in enumerate([first, second])])
    memories = RuleBasedMemoryExtractor().extract(conversation)
    assert len(memories) == 2
    conflicts = [relation for memory in memories for relation in memory.relationships if relation.type == RelationshipType.CONFLICT]
    assert bool(conflicts) is conflict
    run = AuditRun(run_id='RUN-equivalent', conversation_id=conversation.conversation_id, status=AuditStatus.GROUND_TRUTH_CONFIRMED, target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED, model='rule-based-target-ai', temperature=0, random_seed=42, test_budget=4, prompt_template_version='test', created_at=now)
    cases = [item for item in RuleBasedTestGenerator().generate(memories, run) if item.dimension.value == 'conflict_resolution']
    assert bool(cases) is conflict
    if not conflict:
        questions = RuleBasedTestGenerator().generate(memories, run)
        assert len(questions) == 1
        assert set(questions[0].supporting_memory_ids) == {m.memory_id for m in memories}
        assert set(questions[0].target_memory_context) == {m.canonical_value for m in memories}

@pytest.mark.parametrize(('left', 'right'), [
    ('For the Clover meeting, only Zoom is allowed.', 'For the Clover meeting, only Teams is allowed.'),
    ('For the Clover meeting, only Zoom is allowed.', 'For the Clover meeting, only Zoom will be allowed.'),
    ('For the Clover meeting, only Zoom is allowed.', 'For the Clover meeting, only Zoom is allowed with recording disabled.'),
    ('For the Clover meeting, only Zoom is allowed.', 'For the Primrose meeting, only Zoom is allowed.'),
    ('If only Zoom is allowed for the Clover meeting.', 'Only Zoom is allowed for the Clover meeting.'),
])
def test_equivalence_does_not_discard_changed_qualifiers_or_scope(left, right):
    from app.services.meeting_facts import equivalent_exclusive_platform_rules
    assert not equivalent_exclusive_platform_rules(left, right)


@pytest.mark.parametrize('expected', [
    'State the recorded fact: For the Clover meeting, only Microsoft Teams is allowed.',
    'State the recorded fact: Only Teams is permitted for the Clover meeting.',
])
def test_allowed_platform_review_checks_the_platform_instead_of_scope_words(expected):
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    assert RuleBasedBehaviourEvaluator._required_terms(expected) == ['teams']


def test_reviewed_language_preference_noun_does_not_score_the_background_word_tools():
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    expected = 'State the recorded fact: Preference for Rust for personal tools.'
    assert RuleBasedBehaviourEvaluator._required_terms(expected) == ['rust']
