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
    assert result.evaluator == "rule-based-v4"


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


def test_evaluator_accepts_a_concise_value_without_requiring_explanatory_words():
    test = DomainTestCase(
        test_id="T008", run_id="RUN1", dimension=Dimension.ACCURACY,
        prompt="What language does the user prefer?", expected_behavior="State the recorded fact: I generally prefer Python.",
        supporting_memory_ids=["M003"], generator_version="rule-based-v3",
    )
    result = RuleBasedBehaviourEvaluator().evaluate(
        test,
        TargetResponse(response_id="R008", test_id="T008", run_id="RUN1", response_text="Python", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M003", conversation_id="C1", canonical_value="I generally prefer Python", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed


def test_evaluator_extracts_the_required_value_from_contextual_requirement():
    test = DomainTestCase(
        test_id="T009", run_id="RUN1", dimension=Dimension.APPROPRIATE_USE,
        prompt="Which language applies to this assignment?", expected_behavior="Follow the contextual requirement: For this assignment, Java is required.",
        supporting_memory_ids=["M004"], generator_version="rule-based-v3",
    )
    result = RuleBasedBehaviourEvaluator().evaluate(
        test,
        TargetResponse(response_id="R009", test_id="T009", run_id="RUN1", response_text="Java", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M004", conversation_id="C1", canonical_value="For this assignment, Java is required", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed


def test_evaluator_rejects_a_response_that_negates_the_expected_value():
    result = RuleBasedBehaviourEvaluator().evaluate(
        _test_case(),
        TargetResponse(response_id="R010", test_id="T007", run_id="RUN1", response_text="Do not use PostgreSQL; use MySQL instead.", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M001", conversation_id="C1", canonical_value="Old database: MySQL", status=MemoryStatus.CONFIRMED), Memory(memory_id="M002", conversation_id="C1", canonical_value="New database: PostgreSQL", status=MemoryStatus.CONFIRMED)],
    )
    assert not result.passed


def test_evaluator_uses_the_positive_value_in_a_rather_than_constraint():
    test = DomainTestCase(
        test_id="T011", run_id="RUN1", dimension=Dimension.ACCURACY,
        prompt="Which database should be used?", expected_behavior="State the recorded fact: The assignment must use PostgreSQL rather than SQLite.",
        supporting_memory_ids=["M005"], generator_version="rule-based-v4",
    )
    result = RuleBasedBehaviourEvaluator().evaluate(
        test,
        TargetResponse(response_id="R011", test_id="T011", run_id="RUN1", response_text="PostgreSQL", model="test", temperature=0, created_at=datetime.now(timezone.utc)),
        [Memory(memory_id="M005", conversation_id="C1", canonical_value="The assignment must use PostgreSQL rather than SQLite", status=MemoryStatus.CONFIRMED)],
    )
    assert result.passed
