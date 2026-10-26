"""Generic source coverage regressions; no benchmark references or API calls."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.memory_agent.store import SqlTargetMemoryStore, infer_target_memory_scope
from app.memory_agent.writers import RuleBasedTargetMemoryWriter
from app.schemas import Conversation, ConversationMessage, Dimension, MemoryStrategy, TargetConfiguration, TargetMemoryScope, TestCase
from app.schemas.target_profile import TargetMemoryProfile
from app.target_ai.rule_based import private_context_instruction


NOW = datetime(2028, 2, 10, tzinfo=timezone.utc)


def history(text, role='user'):
    return Conversation(conversation_id='GENERIC09', authorised=True, created_at=NOW, messages=[
        ConversationMessage(message_id='SOURCE-1', role=role, content=text, timestamp=NOW)])


@pytest.mark.parametrize('text', [
    "I've completed six climbing sessions", "I’ve scored seven points this season",
    "I'm practising the cello twice a week", "We're keeping twelve notebooks",
    "We've completed four training sessions", "I haven't completed the training",
])
def test_private_contracted_declaration_keeps_original_text(text):
    records = RuleBasedTargetMemoryWriter().extract(history(text))
    assert any(record.canonical_value == text for record in records)
    assert all(record.source_message_ids == ['SOURCE-1'] for record in records)


def test_shared_auditor_extractor_unchanged_by_private_writer_detection():
    source = history("I've completed six climbing sessions")
    assert RuleBasedMemoryExtractor().extract(source) == []
    assert RuleBasedTargetMemoryWriter().extract(source)


@pytest.mark.parametrize('separator', [', and I was wondering whether you had a map?', ', could you suggest a route?'])
def test_private_declared_prefix_is_kept_separately_from_following_request(separator):
    prefix = "I'm thinking of visiting my brother Sam in Perth soon"
    records = RuleBasedTargetMemoryWriter().extract(history(prefix + separator))
    assert [record.canonical_value for record in records] == [prefix]
    assert 'thinking' in records[0].canonical_value
    assert records[0].relationships == []


@pytest.mark.parametrize('text', [
    'Could my brother Sam be in Perth?', 'Do you know whether I completed the training?',
    "I'm practising the cello?", 'Would my sister like this route?',
    'Did I complete the training, could you check?',
    'Is my brother in Perth, and I was wondering if you knew?',
    'If I completed the training, could you check the result?',
])
def test_questions_are_not_converted_into_declarations(text):
    assert RuleBasedTargetMemoryWriter().extract(history(text)) == []


@pytest.mark.parametrize('duration', ['Over two months of waiting was difficult.', 'A year of uncertainty was stressful.'])
def test_adjacent_duration_remains_unresolved_verbatim_source_context(duration):
    text = 'I received the licence after a long wait. ' + duration
    records = RuleBasedTargetMemoryWriter().extract(history(text))
    quote = [record for record in records if record.canonical_value.startswith(RuleBasedTargetMemoryWriter.CONTEXT_PREFIX)]
    assert len(quote) == 1
    assert quote[0].canonical_value == RuleBasedTargetMemoryWriter.CONTEXT_PREFIX + text
    assert quote[0].relationships == []


@pytest.mark.parametrize('text', [
    'I received the licence. Two years would be stressful.',
    'I received the licence. Two years of waiting was difficult if it happened.',
    'I received the licence.\nTwo years of waiting was difficult.',
    'Two years of waiting was difficult.',
])
def test_duration_context_does_not_bridge_hypotheticals_paragraphs_or_missing_anchor(text):
    records = RuleBasedTargetMemoryWriter().extract(history(text))
    assert not any(record.canonical_value.startswith(RuleBasedTargetMemoryWriter.CONTEXT_PREFIX) for record in records)


def candidate(index, text, role):
    return dict(record=SimpleNamespace(id=f'R{index}', canonical_value=text,
        observed_at=NOW + timedelta(minutes=index), source_message_ids=[f'S{index}'], write_order=index),
        source_roles={role}, reason='query', direct_relevance=1, relevance=1,
        policy_score=20, temporal_window_match=False, relationship_types=[])


@pytest.mark.parametrize('question,expected', [
    ('How many subscribers did I gain?', 'user'),
    ('What book did you recommend for my holiday?', 'assistant'),
    ('What were your recommendations for my holiday?', 'assistant'),
    ('What did you advise me about my study plan?', 'assistant'),
])
def test_role_priority_under_same_budget_respects_question_attribution(question, expected):
    user = candidate(0, 'I gained seventeen subscribers on my channel', 'user')
    assistant = candidate(1, 'Prior assistant conversation history: a long list of channel tips', 'assistant')
    store = SqlTargetMemoryStore(None, profile=TargetMemoryProfile(retrieve_message_context=True,
        max_retrieved_records=1, context_character_budget=400))
    selected = store._apply_profile([user, assistant], SimpleNamespace(prompt=question), MemoryStrategy.STRONG_RULE_BASED)
    assert len(selected) == 1 and selected[0]['source_roles'] == {expected}
    assert sum(len(store._render_context(item)) + 3 for item in selected) <= 400


@pytest.mark.parametrize('text', ['I like places with gardens', 'I also enjoy quiet libraries', 'I generally love mountain views'])
def test_present_user_likes_are_preferences(text):
    assert infer_target_memory_scope(text) == TargetMemoryScope.PREFERENCE


@pytest.mark.parametrize('text', [
    "I've been working professionally for eleven years",
    "I'm thinking of visiting my brother Sam in Perth soon",
    "We've been living near the harbour for several years",
])
def test_background_and_relationship_scope_retains_source_qualifiers(text):
    assert infer_target_memory_scope(text) == TargetMemoryScope.PROFILE
    record = RuleBasedTargetMemoryWriter().extract(history(text))[0]
    assert record.canonical_value == text


def test_recommendation_and_duration_rules_never_read_reference_answer():
    test = TestCase(test_id='T09', run_id='RUN09', dimension=Dimension.ACCURACY,
                    supporting_memory_ids=[], generator_version='synthetic-unit-test',
                    prompt='Can you suggest somewhere for my next trip?',
                    target_memory_context=['I like quiet gardens'], expected_behavior='PRIVATE NEVER SEND')
    instruction = private_context_instruction(test, TargetConfiguration.STRONG)
    assert "apply the user's supplied likes" in instruction
    assert 'PRIVATE NEVER SEND' not in instruction
    test.prompt = 'How long did I work before my current role?'
    instruction = private_context_instruction(test, TargetConfiguration.STRONG)
    assert 'Explicit durations can support arithmetic' in instruction
    assert 'PRIVATE NEVER SEND' not in instruction
