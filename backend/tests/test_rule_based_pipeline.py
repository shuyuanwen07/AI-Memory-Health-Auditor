from datetime import datetime, timezone
from app.schemas import AuditRun, AuditStatus, Conversation, ConversationMessage, Dimension, RelationshipType, TargetConfiguration, TargetProvider
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.target_ai.rule_based import RuleBasedTargetAIConnector
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
def test_rule_based_pipeline_has_pass_and_fail_cases():
    c=Conversation(conversation_id='C1',created_at=datetime.now(timezone.utc),authorised=True,messages=[ConversationMessage(message_id='MSG001',role='user',content='I used MySQL before. The backend now uses PostgreSQL. I generally prefer Python. This current assignment requires Java. I am based in Sydney.',timestamp=datetime.now(timezone.utc))])
    memories=RuleBasedMemoryExtractor().extract(c)
    run=AuditRun(run_id='RUN1',conversation_id='C1',status=AuditStatus.CREATED,target_configuration=TargetConfiguration.WEAK,provider=TargetProvider.RULE_BASED,model='rule-based-target-ai',temperature=0,random_seed=42,test_budget=8,prompt_template_version='rule-based-v1',created_at=datetime.now(timezone.utc))
    tests=RuleBasedTestGenerator().generate(memories,run); connector=RuleBasedTargetAIConnector(); judge=RuleBasedBehaviourEvaluator()
    verdicts=[judge.evaluate(t,connector.execute(t,run),memories) for t in tests]
    assert any(v.passed for v in verdicts) and any(not v.passed for v in verdicts)


def test_extractor_preserves_message_order_and_detects_all_relationships():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        conversation_id="C2",
        created_at=base,
        authorised=True,
        # Deliberately submit these out of order to exercise chronological sorting.
        messages=[
            ConversationMessage(message_id="MSG003", role="user", content="This assignment currently requires Rust.", timestamp=base.replace(hour=3)),
            ConversationMessage(message_id="MSG001", role="user", content="I used a relational database before. I generally prefer scripting languages.", timestamp=base.replace(hour=1)),
            ConversationMessage(message_id="MSG002", role="user", content="The backend now uses a document database.", timestamp=base.replace(hour=2)),
            ConversationMessage(message_id="MSG004", role="user", content="The assignment must not use Rust because its requirements conflict.", timestamp=base.replace(hour=4)),
        ],
    )

    memories = RuleBasedMemoryExtractor().extract(conversation)

    assert [memory.source_message_ids[0] for memory in memories] == ["MSG001", "MSG001", "MSG002", "MSG003", "MSG004"]
    update = next(memory for memory in memories if "now uses" in memory.canonical_value)
    assert (RelationshipType.UPDATE, "M001") in {(relation.type, relation.target_memory_id) for relation in update.relationships}
    contextual = next(memory for memory in memories if "currently requires" in memory.canonical_value)
    assert any(relation.type == RelationshipType.CONTEXTUAL_OVERRIDE for relation in contextual.relationships)
    conflict = next(memory for memory in memories if "must not use" in memory.canonical_value)
    assert any(relation.type == RelationshipType.CONFLICT for relation in conflict.relationships)


def test_generator_creates_traceable_dimension_balanced_tests():
    timestamp = datetime.now(timezone.utc)
    conversation = Conversation(
        conversation_id="C3", created_at=timestamp, authorised=True,
        messages=[ConversationMessage(message_id="MSG001", role="user", content=(
            "I used an older tool before. The service now uses a newer tool. "
            "I generally prefer concise output. This assignment currently requires detailed output. "
            "The assignment must not use detailed output because its requirements conflict. "
            "I work from home."
        ), timestamp=timestamp)],
    )
    run = AuditRun(run_id="RUN3", conversation_id="C3", status=AuditStatus.CREATED, target_configuration=TargetConfiguration.WEAK,
                   provider=TargetProvider.RULE_BASED, model="rule-based-target-ai", temperature=0.0, random_seed=7,
                   test_budget=20, prompt_template_version="rule-based-v1", created_at=timestamp)

    memories = RuleBasedMemoryExtractor().extract(conversation)
    tests = RuleBasedTestGenerator().generate(memories, run)

    assert {test.dimension for test in tests} == set(Dimension)
    assert all(test.generator_version == "rule-based-v2" for test in tests)
    assert all(test.supporting_memory_ids for test in tests)
    assert all(memory_id in {memory.memory_id for memory in memories} for test in tests for memory_id in test.supporting_memory_ids)
    assert len({(test.dimension, tuple(test.supporting_memory_ids)) for test in tests}) == len(tests)


def test_extractor_handles_natural_transitions_and_ignores_assistant_text():
    timestamp = datetime.now(timezone.utc)
    conversation = Conversation(
        conversation_id="C4", created_at=timestamp, authorised=True,
        messages=[
            ConversationMessage(message_id="MSG001", role="assistant", content="The user lives in Paris.", timestamp=timestamp),
            ConversationMessage(message_id="MSG002", role="user", content=(
                "I migrated from MySQL to PostgreSQL. Although I prefer Python, "
                "this assignment currently requires Java. I work remotely."
            ), timestamp=timestamp),
            ConversationMessage(message_id="MSG003", role="user", content="I work remotely.", timestamp=timestamp),
        ],
    )
    memories = RuleBasedMemoryExtractor().extract(conversation)
    values = [memory.canonical_value for memory in memories]

    assert all("Paris" not in value for value in values)
    assert any("previously used MySQL" in value for value in values)
    current = next(memory for memory in memories if "now uses PostgreSQL" in memory.canonical_value)
    assert any(relationship.type == RelationshipType.UPDATE for relationship in current.relationships)
    contextual = next(memory for memory in memories if "requires Java" in memory.canonical_value)
    assert any(relationship.type == RelationshipType.CONTEXTUAL_OVERRIDE for relationship in contextual.relationships)
    remote = next(memory for memory in memories if "work remotely" in memory.canonical_value)
    assert remote.source_message_ids == ["MSG002", "MSG003"]


def test_generator_hides_answers_and_balances_a_small_budget():
    timestamp = datetime.now(timezone.utc)
    conversation = Conversation(
        conversation_id="C5", created_at=timestamp, authorised=True,
        messages=[ConversationMessage(message_id="MSG001", role="user", content=(
            "I used MySQL before. The backend now uses PostgreSQL. "
            "I generally prefer Python. This assignment currently requires Java. "
            "The assignment must not use Java because its requirements conflict. I am based in Sydney."
        ), timestamp=timestamp)],
    )
    run = AuditRun(run_id="RUN5", conversation_id="C5", status=AuditStatus.CREATED,
                   target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED,
                   model="rule-based-target-ai", temperature=0.0, random_seed=7, test_budget=4,
                   prompt_template_version="rule-based-v1", created_at=timestamp)
    memories = RuleBasedMemoryExtractor().extract(conversation)
    tests = RuleBasedTestGenerator().generate(memories, run)

    assert len(tests) == 4
    assert len({test.dimension for test in tests}) == 4
    assert len({(test.dimension, tuple(test.supporting_memory_ids)) for test in tests}) == len(tests)
    for test in tests:
        for memory_id in test.supporting_memory_ids:
            value = next(memory.canonical_value for memory in memories if memory.memory_id == memory_id)
            assert value.lower() not in test.prompt.lower()
