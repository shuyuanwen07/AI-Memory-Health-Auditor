"""Opt-in source coverage is an ingestion policy with durable eviction traces."""
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel, ConversationModel, TargetAgentMemoryModel, TargetAgentMemoryEventModel
from app.schemas.target_profile import TargetMemoryProfile


def setup(policy="source_coverage", capacity=2):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(ConversationModel(id="C", authorised=True)); db.flush()
    db.add(AuditRunModel(id="R", conversation_id="C", target_configuration="strong",
        provider="rule_based", model="rules", temperature=0, random_seed=42,
        test_budget=1, prompt_template_version="synthetic")); db.flush()
    store = SqlTargetMemoryStore(db, capacity=capacity, profile=TargetMemoryProfile(retention_policy=policy))
    return engine, db, store


def add(db, name, source, order, text, state="ACTIVE", scope="episodic"):
    row = TargetAgentMemoryModel(id=name, run_id="R", source_conversation_id="C", canonical_value=text,
        scope=scope, lifecycle_state=state, source_message_ids=[source],
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), write_order=order)
    db.add(row); db.flush()
    return row


def test_optin_diversifies_observations_and_records_every_eviction():
    engine, db, store = setup()
    try:
        early = add(db, "A", "EARLY", 1, "I attended a glassblowing demonstration.")
        for i in range(2, 5):
            add(db, str(i), "LATE", i, f"I recorded a later observation number {i}.")
        store._apply_capacity_limit("R"); db.flush()
        rows = store._records("R")
        assert early.lifecycle_state == "ACTIVE"
        assert sum(r.lifecycle_state == "ACTIVE" for r in rows) == 2
        assert store._evicted_memory_ids("R") == {r.id for r in rows if r.lifecycle_state == "EVICTED"}
        events = db.scalars(select(TargetAgentMemoryEventModel)).all()
        receipt = next(e.details for e in events if e.details.get("maintenance_action") == "capacity_source_coverage_selection")
        assert receipt["retention_policy"] == "source_coverage"
        assert receipt["retained_record_count"] == receipt["max_active_records"] == 2
        assert len(receipt["decisions"]) == 4
    finally:
        db.close(); engine.dispose()


def test_legacy_scope_recency_does_not_enable_coverage():
    engine, db, store = setup("scope_recency")
    try:
        early = add(db, "A", "EARLY", 1, "I attended an early lecture.")
        for i in range(2, 5):
            add(db, str(i), "LATE", i, f"I attended lecture number {i}.")
        store._apply_capacity_limit("R")
        assert early.lifecycle_state == "EVICTED"
        assert not any(e.details.get("maintenance_action") == "capacity_source_coverage_selection"
            for e in db.scalars(select(TargetAgentMemoryEventModel)))
    finally:
        db.close(); engine.dispose()


def test_previously_unavailable_records_are_never_revived():
    engine, db, store = setup()
    try:
        lost = add(db, "OLD", "OLD", 0, "I kept the earlier location in my notes.", "EVICTED")
        for i in range(1, 4):
            add(db, str(i), str(i), i, f"I logged a different observation number {i}.")
        store._apply_capacity_limit("R")
        assert lost.lifecycle_state == "EVICTED"
        receipt = next(e.details for e in db.scalars(select(TargetAgentMemoryEventModel))
            if e.details.get("maintenance_action") == "capacity_source_coverage_selection")
        assert "OLD" not in {r["memory_id"] for r in receipt["decisions"]}
    finally:
        db.close(); engine.dispose()


def test_conflict_soft_limit_remains_explicit():
    engine, db, store = setup(capacity=1)
    try:
        a = add(db, "A", "A", 1, "The direction is east.", "CONFLICTED")
        b = add(db, "B", "B", 2, "The direction is west.", "CONFLICTED")
        store._apply_capacity_limit("R")
        assert a.lifecycle_state == b.lifecycle_state == "CONFLICTED"
        assert any(e.details.get("maintenance_action") == "capacity_soft_limit_preserved_conflict"
            for e in db.scalars(select(TargetAgentMemoryEventModel)))
    finally:
        db.close(); engine.dispose()
