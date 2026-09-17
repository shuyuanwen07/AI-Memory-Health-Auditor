from datetime import datetime, timedelta, timezone

from app.memory_agent import build_target_memory_context
from app.schemas import Dimension, Memory, MemoryRelationship, MemoryStatus, MemoryStrategy, RelationshipType, TestCase


def _memory(memory_id: str, value: str, moment: datetime, relationships=None):
    return Memory(memory_id=memory_id, conversation_id="C1", canonical_value=value, status=MemoryStatus.CONFIRMED, source_message_ids=["MSG001"], timestamp=moment, relationships=relationships or [])


def test_weak_first_hit_keeps_only_the_oldest_supporting_memory():
    now = datetime.now(timezone.utc)
    old = _memory("M001", "The backend previously used MySQL.", now)
    current = _memory("M002", "The backend now uses PostgreSQL.", now + timedelta(hours=1), [MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="M001")])
    test = TestCase(test_id="T001", run_id="RUN1", dimension=Dimension.FRESHNESS, prompt="Which database should be used now?", expected_behavior="Use PostgreSQL.", supporting_memory_ids=["M001", "M002"], generator_version="test")
    assert build_target_memory_context(test, [old, current], MemoryStrategy.WEAK_FIRST_HIT) == [old.canonical_value]


def test_strong_rule_policy_places_update_and_contextual_override_last():
    now = datetime.now(timezone.utc)
    old = _memory("M001", "The backend previously used MySQL.", now)
    current = _memory("M002", "The backend now uses PostgreSQL.", now + timedelta(hours=1), [MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id="M001")])
    preference = _memory("M003", "The user generally prefers Python.", now)
    requirement = _memory("M004", "This assignment currently requires Java.", now + timedelta(hours=2), [MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE, target_memory_id="M003")])
    test = TestCase(test_id="T002", run_id="RUN1", dimension=Dimension.APPROPRIATE_USE, prompt="What language should this assignment use?", expected_behavior="Use Java.", supporting_memory_ids=["M003", "M004"], generator_version="test")
    assert build_target_memory_context(test, [old, current, preference, requirement], MemoryStrategy.STRONG_RULE_BASED)[-1] == requirement.canonical_value
    update_test = test.model_copy(update={"test_id": "T003", "dimension": Dimension.FRESHNESS, "supporting_memory_ids": ["M001", "M002"]})
    assert build_target_memory_context(update_test, [old, current, preference, requirement], MemoryStrategy.STRONG_RULE_BASED)[-1] == current.canonical_value


def test_score_policy_is_traceable_and_prefers_contextual_requirement():
    now = datetime.now(timezone.utc)
    preference = _memory("M001", "The user generally prefers Python.", now)
    requirement = _memory("M002", "This assignment currently requires Java.", now + timedelta(hours=1), [MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE, target_memory_id="M001")])
    test = TestCase(test_id="T001", run_id="RUN1", dimension=Dimension.APPROPRIATE_USE, prompt="Which language is required for the current assignment?", expected_behavior="Use Java.", supporting_memory_ids=["M001", "M002"], generator_version="test")
    assert build_target_memory_context(test, [preference, requirement], MemoryStrategy.STRONG_SCORE_BASED)[-1] == requirement.canonical_value


def test_reference_ablations_are_explicit():
    now = datetime.now(timezone.utc)
    old = _memory("M001", "The backend previously used MySQL.", now)
    current = _memory("M002", "The backend now uses PostgreSQL.", now + timedelta(hours=1))
    test = TestCase(test_id="T001", run_id="RUN1", dimension=Dimension.FRESHNESS, prompt="Which database should be used now?", expected_behavior="Use PostgreSQL.", supporting_memory_ids=["M001", "M002"], generator_version="test")

    assert build_target_memory_context(test, [old, current], MemoryStrategy.NO_MEMORY) == []
    assert build_target_memory_context(test, [old, current], MemoryStrategy.FULL_CONTEXT) == [old.canonical_value, current.canonical_value]
