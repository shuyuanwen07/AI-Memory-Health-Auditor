"""Contract tests for the private, persistent controlled-target memory store."""
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.memory_agent import SqlTargetMemoryStore
from app.models import (
    AuditRunModel,
    ConversationModel,
    TargetAgentMemoryEventModel,
    TargetAgentMemoryModel,
    TargetAgentRetrievalModel,
)
from app.schemas import (
    Conversation,
    ConversationMessage,
    Dimension,
    Memory,
    MemoryRelationship,
    MemoryStatus,
    MemoryStrategy,
    RelationshipType,
    TargetMemoryEventType,
    TargetMemoryLifecycleState,
    TargetMemoryProfile,
    TargetConfiguration,
    TestCase,
)


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _conversation() -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        conversation_id="C-TARGET", authorised=True, created_at=now,
        messages=[ConversationMessage(
            message_id="MSG001", role="user", timestamp=now,
            content=("I used MySQL before. The backend now uses PostgreSQL. "
                     "I generally prefer Python. This assignment currently requires Java."),
        )],
    )


def _run(db, conversation_id="C-TARGET"):
    db.add(ConversationModel(id=conversation_id, authorised=True))
    db.add(AuditRunModel(
        id="RUN-TARGET", conversation_id=conversation_id, status="CREATED",
        target_configuration="strong", provider="rule_based", model="rule-based-target-ai",
        temperature=0.0, random_seed=42, test_budget=4,
        prompt_template_version="rule-based-v1", pipeline_provider="rule_based",
        pipeline_model="rule-based-v2", evaluator_provider="rule_based",
        evaluator_model="rule-based-v2", memory_strategy="strong_rule_based",
    ))
    db.commit()


def test_ingestion_writes_an_independent_store_and_is_idempotent():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db)

    first = store.ingest("RUN-TARGET", _conversation())
    db.commit()
    second = store.ingest("RUN-TARGET", _conversation())

    records = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == "RUN-TARGET")).all()
    events = db.scalars(select(TargetAgentMemoryEventModel).where(TargetAgentMemoryEventModel.run_id == "RUN-TARGET")).all()
    assert len(first.records) == len(second.records) == len(records) >= 4
    assert all(record.source_message_ids == ["MSG001"] for record in first.records)
    assert any(record.lifecycle_state == TargetMemoryLifecycleState.SUPERSEDED for record in first.records)
    assert TargetMemoryEventType.INGESTED.value in {event.event_type for event in events}
    assert TargetMemoryEventType.WRITTEN.value in {event.event_type for event in events}
    assert TargetMemoryEventType.UPDATED.value in {event.event_type for event in events}
    # Retry returns the original evidence: it does not write a second timeline.
    assert len(events) == len(second.write_evidence)


def test_retrieval_is_persistent_traceable_and_keeps_evaluator_secret_out_of_context():
    db = _db()
    _run(db)
    store = SqlTargetMemoryStore(db)
    test = TestCase(
        test_id="T-FRESH", run_id="RUN-TARGET", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used now?", supporting_memory_ids=["GROUND-TRUTH-ONLY"],
        expected_behavior="EVALUATOR_ONLY_SECRET: PostgreSQL", generator_version="test-v1",
    )

    weak = store.retrieve("RUN-TARGET", _conversation(), test, MemoryStrategy.WEAK_FIRST_HIT)
    strong = store.retrieve("RUN-TARGET", _conversation(), test, MemoryStrategy.STRONG_RULE_BASED)
    db.commit()

    assert "MySQL" in weak.context[0]
    assert "PostgreSQL" in strong.context[-1]
    assert all("EVALUATOR_ONLY_SECRET" not in value for value in weak.context + strong.context)
    assert all("GROUND-TRUTH-ONLY" not in value for value in weak.context + strong.context)
    traces = db.scalars(select(TargetAgentRetrievalModel).where(TargetAgentRetrievalModel.run_id == "RUN-TARGET")).all()
    assert len(traces) == 2
    assert weak.evidence.selected_memory_ids
    assert any(row["selected"] for row in strong.evidence.ranking_evidence)


class _ConflictExtractor:
    def extract(self, conversation: Conversation):
        moment = conversation.messages[0].timestamp
        return [
            Memory(memory_id="M1", conversation_id=conversation.conversation_id,
                   canonical_value="The deployment must use region A.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=moment),
            Memory(memory_id="M2", conversation_id=conversation.conversation_id,
                   canonical_value="The deployment must use region B.", status=MemoryStatus.CANDIDATE,
                   source_message_ids=["MSG001"], timestamp=moment + timedelta(seconds=1),
                   relationships=[MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id="M1")]),
        ]


class _AsymmetricConflictExtractor:
    def extract(self, conversation: Conversation):
        moment=conversation.messages[0].timestamp
        return [Memory(memory_id='M1',conversation_id=conversation.conversation_id,
                    canonical_value='The archive note says the destination is South.',status=MemoryStatus.CANDIDATE,
                    source_message_ids=['MSG001'],timestamp=moment),
                Memory(memory_id='M2',conversation_id=conversation.conversation_id,
                    canonical_value='The signed authorization requires deployment in the North region.',status=MemoryStatus.CANDIDATE,
                    source_message_ids=['MSG001'],timestamp=moment+timedelta(seconds=1),
                    relationships=[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id='M1')])]


def test_conflicts_are_retained_as_two_records_with_lifecycle_evidence():
    db = _db()
    _run(db)
    result = SqlTargetMemoryStore(db, extractor=_ConflictExtractor()).ingest("RUN-TARGET", _conversation())

    assert {record.lifecycle_state for record in result.records} == {TargetMemoryLifecycleState.CONFLICTED}
    assert any(event.event_type == TargetMemoryEventType.CONFLICT_RECORDED for event in result.write_evidence)


def test_relationship_packet_keeps_conflict_pair_and_does_not_expose_evaluator_evidence():
    db=_db();_run(db)
    store=SqlTargetMemoryStore(db,extractor=_ConflictExtractor())
    question=TestCase(test_id='T-PACKET',run_id='RUN-TARGET',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt='What is the deployment region?',expected_behavior='SECRET-GOLD',
        supporting_memory_ids=['SECRET-ID'],generator_version='fixture')
    result=store.retrieve('RUN-TARGET',_conversation(),question,MemoryStrategy.RELATIONSHIP_PACKET)
    assert len(result.context)==1
    entries=json.loads(result.context[0])['memory_packet']
    assert len(entries)==2
    assert {e['memory_id'] for e in entries}==set(result.evidence.selected_memory_ids)
    assert {'The deployment must use region A.','The deployment must use region B.'}=={e['content'] for e in entries}
    assert 'SECRET-GOLD' not in result.context[0] and 'SECRET-ID' not in result.context[0]
    assert all(e['source_message_ids']==['MSG001'] for e in entries)


def test_relationship_packet_never_splits_conflicts_or_exceeds_budget():
    db=_db();_run(db)
    question=TestCase(test_id='T-BUDGET',run_id='RUN-TARGET',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt='What is the deployment region?',expected_behavior='EXTERNAL-REFERENCE',supporting_memory_ids=[],generator_version='fixture')
    record_limited=SqlTargetMemoryStore(db,extractor=_ConflictExtractor(),profile=TargetMemoryProfile(max_retrieved_records=1))
    result=record_limited.retrieve('RUN-TARGET',_conversation(),question,MemoryStrategy.RELATIONSHIP_PACKET)
    assert result.context==[] and result.evidence.selected_memory_ids==[]
    char_limited=SqlTargetMemoryStore(db,extractor=_ConflictExtractor(),profile=TargetMemoryProfile(context_character_budget=100))
    result=char_limited.retrieve('RUN-TARGET',_conversation(),question,MemoryStrategy.RELATIONSHIP_PACKET)
    assert result.context==[] and result.evidence.selected_memory_ids==[]


def test_packet_expands_private_conflict_neighbor_without_lexical_overlap():
    db=_db();_run(db);store=SqlTargetMemoryStore(db,extractor=_AsymmetricConflictExtractor())
    q=TestCase(test_id='T-NEIGHBOR',run_id='RUN-TARGET',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt='What is in the signed authorization?',expected_behavior='REFERENCE-SECRET',supporting_memory_ids=[],generator_version='fixture')
    result=store.retrieve('RUN-TARGET',_conversation(),q,MemoryStrategy.RELATIONSHIP_PACKET)
    entries=json.loads(result.context[0])['memory_packet']
    assert len(entries)==2 and any('South' in e['content'] for e in entries)


def test_packet_uses_unchanged_weak_reader_instruction():
    from app.target_ai.rule_based import private_context_instruction
    db=_db();_run(db)
    store=SqlTargetMemoryStore(db,extractor=_ConflictExtractor())
    q=TestCase(test_id='T-READER',run_id='RUN-TARGET',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt='What is the deployment region?',expected_behavior='SECRET',supporting_memory_ids=[],generator_version='fixture')
    bundle=store.retrieve('RUN-TARGET',_conversation(),q,MemoryStrategy.RELATIONSHIP_PACKET)
    baseline=store.retrieve('RUN-TARGET',_conversation(),q,MemoryStrategy.WEAK_FIRST_HIT)
    before=private_context_instruction(q.model_copy(update={'target_memory_context':baseline.context}),TargetConfiguration.WEAK)
    after=private_context_instruction(q.model_copy(update={'target_memory_context':bundle.context}),TargetConfiguration.WEAK)
    assert 'Use only the single retrieved record below. Do not reconcile records that were not retrieved.' in before
    assert 'Use only the single retrieved record below. Do not reconcile records that were not retrieved.' in after
    assert 'SECRET' not in after


def test_packet_adapter_records_constituent_ids_and_one_delivered_packet():
    from app.schemas import AuditRun
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    db=_db();_run(db)
    audit=AuditRun(run_id='RUN-TARGET',conversation_id='C-TARGET',status='CREATED',target_configuration='weak',
        provider='rule_based',model='rule-based-target-ai',temperature=0,random_seed=42,test_budget=4,
        prompt_template_version='rule-based-v4',memory_strategy=MemoryStrategy.RELATIONSHIP_PACKET,
        created_at=datetime.now(timezone.utc))
    adapter=ControlledTargetSystemAdapter(db,audit);adapter.store.extractor=_ConflictExtractor();adapter.ingest(_conversation())
    q=TestCase(test_id='T-RECEIPT',run_id='RUN-TARGET',dimension=Dimension.CONFLICT_RESOLUTION,
        prompt='What is the deployment region?',expected_behavior='SECRET',supporting_memory_ids=['SECRET-ID'],generator_version='fixture')
    response=adapter.answer(q,audit)
    receipt=response.execution_metadata.memory_input
    assert receipt.record_count==1
    assert len(receipt.sent_memory_ids)==2
    assert 'SECRET' not in response.response_text
