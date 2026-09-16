from datetime import datetime, timezone

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Dimension, Memory, MemoryStatus, TargetResponse, TestCase as DomainTestCase


def _test_case() -> DomainTestCase:
    return DomainTestCase(
        test_id="T007", run_id="RUN1", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used?", expected_behavior="Use the later record: PostgreSQL.",
        supporting_memory_ids=["M001", "M002"], generator_version="rule-based-v2",
    )


def test_evaluator_returns_traceable_pass_reason():
    result = RuleBasedBehaviourEvaluator().evaluate(
        _test_case(),
        TargetResponse(response_id="R007", test_id="T007", run_id="RUN1", response_text="Use PostgreSQL.", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED), Memory(memory_id="M002", conversation_id="C1", canonical_value="New database: PostgreSQL", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed
    assert result.failure_type is None
    assert result.evidence_memory_ids == ["M001", "M002"]
    assert "Passed freshness" in result.reason
    assert result.evaluator == "rule-based-v2"


def test_evaluator_explains_missing_ground_truth_terms():
    result = RuleBasedBehaviourEvaluator().evaluate(
        _test_case(),
        TargetResponse(response_id="R007", test_id="T007", run_id="RUN1", response_text="Use MySQL.", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED)],
    )
    assert not result.passed
    assert result.failure_type == Dimension.FRESHNESS
    assert "postgresql" in result.reason.lower()
    assert result.evidence_memory_ids == ["M001"]
