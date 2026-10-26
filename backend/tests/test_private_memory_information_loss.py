"""General numeric/relationship/retrieval regressions, without benchmark labels."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import Base
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel, ConversationModel
from app.schemas import Conversation, ConversationMessage, MemoryStrategy, TestCase as Case
from app.schemas import Memory, RelationshipType


def ingest(values, capacity=50):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(ConversationModel(id='C-LOSS', authorised=True))
    db.flush()
    db.add(AuditRunModel(id='R-LOSS', conversation_id='C-LOSS', target_configuration='strong',
                        provider='rule_based', model='rule-based-target-ai', temperature=0,
                        random_seed=42, test_budget=1, prompt_template_version='loss-regression'))
    db.flush()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversation = Conversation(conversation_id='C-LOSS', authorised=True, created_at=now,
        messages=[ConversationMessage(message_id=f'S{i}', role='user', content=value,
                    timestamp=now + timedelta(minutes=i)) for i, value in enumerate(values)])
    store = SqlTargetMemoryStore(db, capacity=capacity)
    return db, store, conversation, store.ingest('R-LOSS', conversation)


@pytest.mark.parametrize('values', [
    ['I logged 10 miles.', 'I logged 20 miles.'],
    ['I saved $10.', 'I saved €10.'],
    ['I saved -10 credits.', 'I saved 10 credits.'],
    ['I attended the seminar on March 2.', 'I attended the seminar on March 12.'],
    ['I allocated 10 tickets to Ada and 20 to Bob.', 'I allocated 20 tickets to Ada and 10 to Bob.'],
])
def test_distinct_quantities_dates_currencies_and_bindings_survive_dedup(values):
    db, _, _, result = ingest(values)
    try:
        assert len(result.records) == 2
        assert [r.source_message_ids for r in result.records] == [['S0'], ['S1']]
    finally:
        db.close()


def test_exact_numeric_duplicates_still_merge_and_keep_both_sources():
    db, _, _, result = ingest(['I logged 10 miles.', 'I logged 10 miles!'])
    try:
        assert len(result.records) == 1
        assert result.records[0].source_message_ids == ['S0', 'S1']
    finally:
        db.close()


@pytest.mark.parametrize('values', [
    ['I remember a pottery lesson.', "I don't remember the movie actors."],
    ['I need a guitar case.', 'I need a bus ticket.'],
    ['I prefer quiet gardens.', 'My current task requires a rental car.'],
    ['My delivery service is reliable.', 'My church service is not crowded.'],
])
def test_generic_shared_words_do_not_assert_conflict_update_or_override(values):
    db, _, conversation, result = ingest(values)
    try:
        candidates = RuleBasedMemoryExtractor().extract(conversation)
        assert all(not r.relationships for r in candidates)
        assert all(r.lifecycle_state.value == 'ACTIVE' for r in result.records)
    finally:
        db.close()


def test_unrelated_records_are_not_protected_as_conflicts_under_capacity_pressure():
    db, _, _, result = ingest(['I need a guitar case.', 'I need a bus ticket.',
                              'I recorded 12 bird sightings.'], capacity=1)
    try:
        assert sum(r.lifecycle_state.value == 'ACTIVE' for r in result.records) == 1
        assert all(r.lifecycle_state.value != 'CONFLICTED' for r in result.records)
        assert sum(r.lifecycle_state.value == 'EVICTED' for r in result.records) == 2
    finally:
        db.close()


@pytest.mark.parametrize('strategy', [MemoryStrategy.WEAK_FIRST_HIT, MemoryStrategy.STRONG_RULE_BASED])
def test_pronouns_and_question_date_do_not_retrieve_unrelated_personal_facts(strategy):
    db, store, conversation, _ = ingest(['I own a sailing boat.', 'I recorded 2026 bird sightings.'])
    try:
        result = store.retrieve('R-LOSS', conversation, Case(test_id='T-LOSS', run_id='R-LOSS',
            dimension='accuracy', prompt='How many violins have I collected?\nQuestion date: 2026-01-01',
            expected_behavior='Evaluator-only answer', supporting_memory_ids=[], generator_version='regression'), strategy)
        assert result.context == []
        assert all(r['relevance'] == 0 for r in result.evidence.ranking_evidence)
    finally:
        db.close()


def test_unknown_distractor_cannot_hide_same_field_update_or_scoped_preference():
    extractor = RuleBasedMemoryExtractor()

    def fact(mid, value):
        return Memory(memory_id=mid, conversation_id='C', status='candidate', canonical_value=value)

    prior = fact('M001', 'I use MySQL.')
    distractor = fact('M099', 'I keep weekly planning notes and shared archive.')
    current = fact('M100', 'I now use PostgreSQL for weekly planning notes and shared archive.')
    assert any(r.type == RelationshipType.UPDATE and r.target_memory_id == prior.memory_id
               for r in extractor._relationships(current, [prior, distractor]))
    preference = fact('M002', 'I generally prefer Python.')
    distractor = fact('M098', 'I prefer weekly planning notes and shared archive.')
    requirement = fact('M101', 'This assignment requires Java for weekly planning notes and shared archive.')
    assert any(r.type == RelationshipType.CONTEXTUAL_OVERRIDE and r.target_memory_id == preference.memory_id
               for r in extractor._relationships(requirement, [preference, distractor]))


@pytest.mark.parametrize('strategy,with_context', [
    (MemoryStrategy.STRONG_RULE_BASED, True), (MemoryStrategy.WEAK_FIRST_HIT, False),
])
def test_same_message_closure_keeps_contrast_detail_without_expanding_first_hit(strategy, with_context):
    from app.schemas.target_profile import TargetMemoryProfile
    db, store, conversation, _ = ingest([
        'I packed many jackets for the conference, but I ended up only wearing two - the blue and green ones.',
        'I packed five jackets for the conference.',
    ])
    store.profile = TargetMemoryProfile(retrieve_message_context=True)
    try:
        result = store.retrieve('R-LOSS', conversation, Case(test_id='T-CONTEXT', run_id='R-LOSS',
            dimension='accuracy', prompt='What percentage of packed jackets did I wear?',
            expected_behavior='private evaluator text', supporting_memory_ids=[], generator_version='regression'), strategy)
        assert any('only wearing two' in value for value in result.context) is with_context
        assert len(result.context) <= store.profile.max_retrieved_records
        assert sum(len(value) + 3 for value in result.context) <= store.profile.context_character_budget
    finally:
        db.close()


def test_same_message_closure_never_revives_unavailable_records():
    from types import SimpleNamespace
    candidates = [dict(record=SimpleNamespace(source_message_ids=['S']), eligible=True, relevance=4, reason='anchor'),
                  dict(record=SimpleNamespace(source_message_ids=['S']), eligible=False, relevance=0, reason='evicted')]
    SqlTargetMemoryStore._include_message_context(candidates)
    assert candidates[1] == dict(record=candidates[1]['record'], eligible=False, relevance=0, reason='evicted')


def test_context_delivery_preserves_dates_without_changing_stored_fact_text():
    from app.schemas.target_profile import TargetMemoryProfile
    import json
    db, store, conversation, result = ingest(['I ran the race in 37:12.', 'I ran the race in 35:50.'])
    store.profile = TargetMemoryProfile(retrieve_message_context=True)
    try:
        retrieved = store.retrieve('R-LOSS', conversation, Case(test_id='T-DATES', run_id='R-LOSS',
            dimension='accuracy', prompt='What was my race time?', expected_behavior='',
            supporting_memory_ids=[], generator_version='regression'), MemoryStrategy.STRONG_RULE_BASED)
        supplied = [json.loads(value) for value in retrieved.context]
        assert [v['source_message_ids'] for v in supplied] == [['S0'], ['S1']]
        assert supplied[0]['source_observed_at'] < supplied[1]['source_observed_at']
        assert supplied[-1]['content'] == result.records[-1].canonical_value
        assert 'source_observed_at' not in result.records[-1].canonical_value
    finally:
        db.close()


def test_dense_relevant_fact_survives_verbose_records_under_same_budget():
    from types import SimpleNamespace
    from app.schemas.target_profile import TargetMemoryProfile
    db, store, _, _ = ingest(['I paid 730 credits.'])
    store.profile = TargetMemoryProfile(retrieve_message_context=True, context_character_budget=1000)
    try:
        def item(ident, value, relevance):
            return dict(record=SimpleNamespace(id=ident, canonical_value=value,
                        observed_at=None, source_message_ids=['S0'], write_order=1),
                        policy_score=20, relevance=relevance, reason='test')
        concise = item('A', 'I paid 730 credits for the ticket.', 2)
        verbose = item('B', 'Ticket payment advice: ' + 'generic verbose advice ' * 30, 3)
        selected = store._apply_profile(store._select([concise, verbose], MemoryStrategy.STRONG_RULE_BASED),
                                        None, MemoryStrategy.STRONG_RULE_BASED)
        assert concise in selected
        assert sum(len(store._render_context(v)) + 3 for v in selected) <= 1000
    finally:
        db.close()


def test_plural_normalisation_is_retrieval_only_and_opt_in():
    from app.memory_agent.store import _retrieval_tokens, _canonical_fingerprint
    assert _retrieval_tokens('What pottery hobbies and paintings?', normalise_inflections=True) & _retrieval_tokens(
        'My pottery hobby involves painting', normalise_inflections=True) == {'pottery', 'hobby', 'painting'}
    assert 'paintings' in _retrieval_tokens('My paintings')
    assert _canonical_fingerprint('I own 2 paintings') != _canonical_fingerprint('I own 2 painting')
