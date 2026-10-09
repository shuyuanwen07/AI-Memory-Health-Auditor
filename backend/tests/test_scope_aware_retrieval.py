"""Contracts for the scope-aware controlled retrieval condition."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel, ConversationModel
from app.schemas import (
    Conversation,
    ConversationMessage,
    Dimension,
    Memory,
    MemoryStatus,
    MemoryStrategy,
    AuditCreate,
    TargetConfiguration,
    TargetMemoryMaintenancePolicy,
    TestCase,
    MemoryRelationship,
    RelationshipType,
)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def test_scope_aware_does_not_supply_another_named_project_database():
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    db = _db()
    _run(db)
    conversation = _conversation()
    now = conversation.messages[0].timestamp
    conversation.messages = [ConversationMessage(message_id=f'MSG{i}', role='user', timestamp=now + timedelta(seconds=i), content=text)
        for i, text in enumerate(['The Orion backend previously used SQLite.',
                                 'The Orion backend has now migrated to PostgreSQL.',
                                 'The unrelated Vega backend now uses SQLite.'])]
    store = SqlTargetMemoryStore(db, extractor=RuleBasedMemoryExtractor())
    test = TestCase(test_id='T-PROJECT', run_id='RUN-SCOPE-RETRIEVAL', dimension='freshness',
        prompt='Which database does the Orion backend use now?', expected_behavior='EVALUATOR ONLY',
        supporting_memory_ids=[], generator_version='test')
    result = store.retrieve(test.run_id, conversation, test, MemoryStrategy.SCOPE_AWARE)
    assert result.context
    assert all('Vega' not in value for value in result.context)
    assert any('PostgreSQL' in value for value in result.context)
    test = test.model_copy(update={'test_id': 'T-UNKNOWN', 'prompt': 'Which database does the Unknown backend use now?'})
    assert not store.retrieve(test.run_id, conversation, test, MemoryStrategy.SCOPE_AWARE).context


def test_real_writer_keeps_both_unresolved_policies_and_retrieves_only_secret_topic():
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    db = _db()
    _run(db)
    conversation = _conversation()
    now = conversation.messages[0].timestamp
    statements = [
        "I am based in Sydney.",
        "The Atlas deployment policy requires secrets in environment variables.",
        "A conflicting Atlas deployment policy requires secrets in a configuration file; neither policy supersedes the other.",
        "The Atlas logs now remain in object storage.",
    ]
    conversation.messages = [ConversationMessage(message_id=f"MSG{i}", role="user",
        timestamp=now + timedelta(seconds=i), content=value) for i, value in enumerate(statements)]
    store = SqlTargetMemoryStore(db, extractor=RuleBasedMemoryExtractor())
    test = TestCase(test_id="T-POLICIES", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.CONFLICT_RESOLUTION,
        prompt="Where should Atlas deployment secrets be kept?", expected_behavior="EVALUATOR ONLY",
        supporting_memory_ids=[], generator_version="test")
    result = store.retrieve(test.run_id, conversation, test, MemoryStrategy.SCOPE_AWARE)
    assert len(result.context) == 2
    assert any("environment variables" in value for value in result.context)
    assert any("neither policy supersedes" in value for value in result.context)
    assert all("Sydney" not in value and "logs" not in value for value in result.context)
    assert any(row["lifecycle_state"] == "CONFLICTED" for row in result.evidence.ranking_evidence)


def _conversation() -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        conversation_id="C-SCOPE-RETRIEVAL", authorised=True, created_at=now,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content="The user generally prefers Python. This assignment currently requires Java.",
        )],
    )


def _run(db):
    db.add(ConversationModel(id="C-SCOPE-RETRIEVAL", authorised=True))
    db.add(AuditRunModel(
        id="RUN-SCOPE-RETRIEVAL", conversation_id="C-SCOPE-RETRIEVAL", status="CREATED",
        target_configuration="strong", provider="rule_based", model="rule-based-target-ai",
        temperature=0.0, random_seed=42, test_budget=4, prompt_template_version="rule-based-v1",
        pipeline_provider="rule_based", pipeline_model="rule-based-v2",
        evaluator_provider="rule_based", evaluator_model="rule-based-v2",
        memory_strategy="scope_aware",
    ))
    db.commit()


class _ScopedExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M-PREF", conversation_id=conversation.conversation_id,
                   canonical_value="The user generally prefers Python.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M-REQ", conversation_id=conversation.conversation_id,
                   canonical_value="This assignment currently requires Java.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now + timedelta(seconds=1)),
            Memory(memory_id="M-PROFILE", conversation_id=conversation.conversation_id,
                   canonical_value="The user is based in Sydney.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now + timedelta(seconds=2)),
        ]


def test_scope_aware_prefers_requirement_and_excludes_general_preference_for_current_task():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_ScopedExtractor())
    test = TestCase(
        test_id="T-SCOPE-REQ", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.APPROPRIATE_USE,
        prompt="Which language is required for this current assignment?",
        expected_behavior="Use Java.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", _conversation(), test, MemoryStrategy.SCOPE_AWARE)

    assert result.context[-1] == "This assignment currently requires Java."
    assert "The user generally prefers Python." not in result.context
    requirement = next(row for row in result.evidence.ranking_evidence if row["scope"] == "project_requirement")
    assert "intent=current_project_requirement" in requirement["reason"]
    assert "scope_bonus=80" in requirement["reason"]


def test_audit_contract_accepts_scope_aware_as_a_controlled_strategy():
    audit = AuditCreate.model_validate({
        "conversation_id": "C-SCOPE-RETRIEVAL",
        "target_configuration": TargetConfiguration.STRONG,
        "memory_strategy": "scope_aware",
    })
    assert audit.memory_strategy == MemoryStrategy.SCOPE_AWARE


def test_scope_aware_uses_preference_only_for_explicit_preference_question():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_ScopedExtractor())
    test = TestCase(
        test_id="T-SCOPE-PREF", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.ACCURACY,
        prompt="Which programming language does the user prefer?",
        expected_behavior="Python.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", _conversation(), test, MemoryStrategy.SCOPE_AWARE)

    assert result.context == ["The user generally prefers Python."]
    assert "intent=general_preference" in result.evidence.ranking_evidence[0]["reason"]


def test_scope_aware_uses_a_scope_intent_fallback_when_words_do_not_overlap():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_ScopedExtractor())
    test = TestCase(
        test_id="T-SCOPE-FALLBACK", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.APPROPRIATE_USE,
        prompt="For the current toolkit decision, which requirement applies now?",
        expected_behavior="Use Java.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", _conversation(), test, MemoryStrategy.SCOPE_AWARE)

    assert result.context == ["This assignment currently requires Java."]
    requirement = next(row for row in result.evidence.ranking_evidence if row["scope"] == "project_requirement")
    assert "scope_intent_fallback" in requirement["reason"]


def test_scope_aware_keeps_topic_matched_requirement_when_multiple_project_requirements_exist():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db, extractor=_ScopedExtractor())
    conversation = _conversation()
    # Add an unrelated database requirement to prove the language requirement
    # is selected by both scope and topic, not scope alone.
    class _TwoRequirementExtractor(_ScopedExtractor):
        def extract(self, source):
            items = super().extract(source)
            items.append(Memory(memory_id="M-DB-REQ", conversation_id=source.conversation_id,
                                canonical_value="This assignment must use PostgreSQL.", status=MemoryStatus.CANDIDATE,
                                source_message_ids=["MSG001"], timestamp=source.messages[0].timestamp))
            return items
    store = SqlTargetMemoryStore(db, extractor=_TwoRequirementExtractor())
    test = TestCase(
        test_id="T-SCOPE-TOPIC", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.APPROPRIATE_USE,
        prompt="For the current programming-language choice, which requirement applies now?",
        expected_behavior="Use Java.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", conversation, test, MemoryStrategy.SCOPE_AWARE)

    assert result.context == ["This assignment currently requires Java."]


def test_scope_aware_exposes_both_sides_of_an_update_for_resolution():
    db = _db()
    _run(db)
    now = _conversation().messages[0].timestamp
    class _UpdateExtractor:
        def extract(self, conversation):
            return [
                Memory(memory_id="M-OLD", conversation_id=conversation.conversation_id, canonical_value="The backend used MySQL.", status=MemoryStatus.CANDIDATE, source_message_ids=["MSG001"], timestamp=now),
                Memory(memory_id="M-NEW", conversation_id=conversation.conversation_id, canonical_value="The backend now uses PostgreSQL.", status=MemoryStatus.CANDIDATE, source_message_ids=["MSG001"], timestamp=now, relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="M-OLD")]),
            ]
    store = SqlTargetMemoryStore(db, extractor=_UpdateExtractor())
    test = TestCase(
        test_id="T-SCOPE-UPDATE", run_id="RUN-SCOPE-RETRIEVAL", dimension=Dimension.CONFLICT_RESOLUTION,
        prompt="Two time-ordered records about database technology differ. State the final value.",
        expected_behavior="Use PostgreSQL.", supporting_memory_ids=[], generator_version="test-v1",
    )

    result = store.retrieve("RUN-SCOPE-RETRIEVAL", _conversation(), test, MemoryStrategy.SCOPE_AWARE)

    assert result.context == ["The backend used MySQL.", "The backend now uses PostgreSQL."]
    old = next(row for row in result.evidence.ranking_evidence if row["memory_id"] in result.evidence.selected_memory_ids and "MySQL" in next(record.canonical_value for record in store._records("RUN-SCOPE-RETRIEVAL") if record.id == row["memory_id"]))
    assert "update_history_included_for_resolution" in old["reason"]


class _DuplicateExtractor:
    def extract(self, conversation: Conversation):
        now = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M1", conversation_id=conversation.conversation_id,
                   canonical_value="The user is based in Sydney.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=now),
            Memory(memory_id="M2", conversation_id=conversation.conversation_id,
                   canonical_value="the user is based in Sydney!", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG002"], timestamp=now + timedelta(seconds=1)),
        ]


def test_update_aware_maintenance_merges_only_exact_normalised_duplicates():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_DuplicateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION,
    ).ingest("RUN-SCOPE-RETRIEVAL", _conversation())

    assert len(result.records) == 1
    assert result.records[0].source_message_ids == ["MSG001", "MSG002"]
    merged = next(event for event in result.write_evidence if event.event_type.value == "MAINTENANCE_APPLIED")
    assert merged.details["maintenance_action"] == "merged_exact_duplicate"


def test_append_only_retains_same_text_as_two_independent_observations():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(
        db, extractor=_DuplicateExtractor(),
        maintenance_policy=TargetMemoryMaintenancePolicy.APPEND_ONLY,
    ).ingest("RUN-SCOPE-RETRIEVAL", _conversation())

    assert len(result.records) == 2


def test_target_profile_filters_before_first_hit_and_enforces_memory_budget():
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.schemas import TargetMemoryProfile
    db = _db()
    _run(db)
    conversation = _conversation()
    now = conversation.messages[0].timestamp
    conversation.messages = [ConversationMessage(message_id=f'P{i}', role='user', timestamp=now+timedelta(seconds=i), content=text)
        for i,text in enumerate(['Orion project used MySQL before.', 'Orion project now uses PostgreSQL.',
                                'Vega project uses SQLite.'])]
    profile = TargetMemoryProfile(isolate_project_scope=True, prefer_current_state=True,
        max_retrieved_records=1, context_character_budget=100)
    store = SqlTargetMemoryStore(db, extractor=RuleBasedMemoryExtractor(), profile=profile)
    test = TestCase(test_id='PROFILE', run_id='RUN-SCOPE-RETRIEVAL', dimension='freshness',
        prompt='Which database for the Orion project applies now?', expected_behavior='never read this',
        supporting_memory_ids=['never-read-this'], generator_version='test')
    result = store.retrieve(test.run_id, conversation, test, MemoryStrategy.WEAK_FIRST_HIT)
    assert len(result.context)==1
    assert 'PostgreSQL' in result.context[0]
    assert sum(len(value)+3 for value in result.context)<=profile.context_character_budget
    assert any('profile_excluded_other_project' in item['reason'] for item in result.evidence.ranking_evidence)


def test_real_writer_retrieves_new_city_and_ruby_go_constraint_without_reference_values():
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    db = _db()
    _run(db)
    conversation = _conversation()
    now = conversation.messages[0].timestamp
    conversation.messages = [ConversationMessage(message_id=f'MSG{i}', role='user', timestamp=now+timedelta(seconds=i), content=text)
        for i,text in enumerate(['I live in Ballarat.', 'I moved to Port Lincoln.', 'I prefer Ruby.', 'The Pine assignment requires Go.'])]
    store = SqlTargetMemoryStore(db, extractor=RuleBasedMemoryExtractor())
    for index, (prompt, dimension, required, excluded) in enumerate([
        ('Where is the user based now?', 'freshness', 'I moved to Port Lincoln', 'I live in Ballarat'),
        ('What programming language does the user generally prefer?', 'accuracy', 'I prefer Ruby', 'The Pine assignment requires Go'),
        ('For the current programming-language choice, which requirement applies now?', 'appropriate_use', 'The Pine assignment requires Go', 'I prefer Ruby'),
    ]):
        test=TestCase(test_id=f'NEW{index}',run_id='RUN-SCOPE-RETRIEVAL',dimension=dimension,prompt=prompt,
                      expected_behavior='REFERENCE MUST NOT BE USED',supporting_memory_ids=[],generator_version='test')
        result=store.retrieve(test.run_id,conversation,test,MemoryStrategy.SCOPE_AWARE)
        assert required in result.context
        assert excluded not in result.context


def test_state_replacement_is_not_inferred_as_a_personal_preference():
    from app.memory_agent.store import infer_target_memory_scope
    from app.schemas import TargetMemoryScope
    for statement in (
        'The Acacia backend now uses MySQL rather than PostgreSQL.',
        'I now use MySQL rather than PostgreSQL.',
        'The backend now uses MySQL rather than PostgreSQL.',
    ):
        assert infer_target_memory_scope(statement) != TargetMemoryScope.PREFERENCE
    for statement in ('I prefer MySQL rather than PostgreSQL.', 'I would rather use Kotlin than Java.'):
        assert infer_target_memory_scope(statement) == TargetMemoryScope.PREFERENCE
