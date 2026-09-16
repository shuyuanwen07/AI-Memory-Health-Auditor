"""Unit coverage for recoverable audit orchestration without routes or a DB."""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import (
    AuditRun,
    AuditStatus,
    Dimension,
    EvaluationResult,
    Memory,
    MemoryStatus,
    TargetConfiguration,
    TargetProvider,
    TargetResponse,
    TestCase,
)
from app.services.audit_execution import (
    AuditExecutionService,
    AuditExecutionSnapshot,
    AuditStage,
    EventKind,
    RunArtifacts,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _audit(run_id: str = "RUN-1", status: AuditStatus = AuditStatus.CREATED) -> AuditRun:
    return AuditRun(
        run_id=run_id, conversation_id="C-1", status=status,
        target_configuration=TargetConfiguration.STRONG, provider=TargetProvider.RULE_BASED,
        model="local", temperature=0, random_seed=42, test_budget=2,
        prompt_template_version="v1", created_at=NOW,
    )


def _memory() -> Memory:
    return Memory(memory_id="M-1", conversation_id="C-1", canonical_value="User is in Sydney", status=MemoryStatus.CONFIRMED)


def _test(test_id: str) -> TestCase:
    return TestCase(
        test_id=test_id, run_id="RUN-1", dimension=Dimension.ACCURACY,
        prompt=f"Prompt for {test_id}", expected_behavior="Correct answer", supporting_memory_ids=["M-1"],
        generator_version="test-v1",
    )


class Generator:
    def __init__(self, tests: list[TestCase] | None = None) -> None:
        self.tests = tests or [_test("T-1"), _test("T-2")]
        self.calls = 0

    def generate(self, _memories, _audit):
        self.calls += 1
        return self.tests


class Connector:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    def execute(self, test, audit):
        self.calls.append(test.test_id)
        if test.test_id == self.fail_on:
            raise RuntimeError(f"provider unavailable for {test.test_id}")
        return TargetResponse(
            response_id=f"R-{test.test_id}", test_id=test.test_id, run_id=audit.run_id,
            response_text="answer", model=audit.model, temperature=0, created_at=NOW,
        )


class Evaluator:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    def evaluate(self, test, response, _memories):
        self.calls.append(test.test_id)
        if test.test_id == self.fail_on:
            raise RuntimeError(f"judge unavailable for {test.test_id}")
        return EvaluationResult(
            evaluation_id=f"E-{test.test_id}", test_id=test.test_id, response_id=response.response_id,
            passed=True, reason="matches", evidence_memory_ids=["M-1"], evaluator="unit",
        )


def _service(generator=None, connector=None, evaluator=None):
    return AuditExecutionService(generator or Generator(), connector or Connector(), evaluator or Evaluator(), clock=lambda: NOW)


def test_resume_runs_all_stages_and_emits_explicit_events():
    generator, connector, evaluator = Generator(), Connector(), Evaluator()
    result = _service(generator, connector, evaluator).resume(AuditExecutionSnapshot(_audit(), [_memory()]))

    assert result.error is None
    assert result.snapshot.audit.status == AuditStatus.COMPLETED
    assert result.snapshot.audit.completed_at == NOW
    assert set(result.snapshot.artifacts.responses) == {"T-1", "T-2"}
    assert set(result.snapshot.artifacts.evaluations) == {"T-1", "T-2"}
    assert generator.calls == 1
    assert connector.calls == ["T-1", "T-2"]
    assert evaluator.calls == ["T-1", "T-2"]
    events = [(event.stage, event.kind) for event in result.snapshot.events]
    assert (AuditStage.GENERATE_TESTS, EventKind.COMPLETED) in events
    assert (AuditStage.EXECUTE_TESTS, EventKind.COMPLETED) in events
    assert (AuditStage.EVALUATE_RESPONSES, EventKind.COMPLETED) in events
    assert (AuditStage.COMPLETE, EventKind.COMPLETED) in events
    assert result.retry_plan.retryable is False


def test_retry_after_partial_execution_does_not_repeat_completed_target_calls():
    connector = Connector(fail_on="T-2")
    snapshot = AuditExecutionSnapshot(_audit(), [_memory()])
    first = _service(connector=connector).resume(snapshot)

    assert first.snapshot.audit.status == AuditStatus.FAILED
    assert connector.calls == ["T-1", "T-2"]
    assert set(snapshot.artifacts.responses) == {"T-1"}
    assert first.retry_plan.next_stage == AuditStage.EXECUTE_TESTS
    assert first.retry_plan.pending_test_ids == ("T-2",)

    recovered_connector = Connector()
    recovered = _service(connector=recovered_connector).resume(snapshot)
    assert recovered.error is None
    assert recovered.snapshot.audit.status == AuditStatus.COMPLETED
    assert recovered_connector.calls == ["T-2"]
    # Generator never runs again: its first-start event is retained for audit
    # history, but retry did not append a second one.
    assert sum(event.stage == AuditStage.GENERATE_TESTS and event.kind == EventKind.STARTED for event in recovered.snapshot.events) == 1


def test_retry_after_partial_evaluation_reuses_target_responses():
    evaluator = Evaluator(fail_on="T-2")
    snapshot = AuditExecutionSnapshot(_audit(), [_memory()])
    failed = _service(evaluator=evaluator).resume(snapshot)

    assert failed.snapshot.audit.status == AuditStatus.FAILED
    assert set(snapshot.artifacts.responses) == {"T-1", "T-2"}
    assert set(snapshot.artifacts.evaluations) == {"T-1"}
    assert failed.retry_plan.next_stage == AuditStage.EVALUATE_RESPONSES
    assert failed.retry_plan.pending_test_ids == ("T-2",)

    connector = Connector()
    recovered_evaluator = Evaluator()
    recovered = _service(connector=connector, evaluator=recovered_evaluator).resume(snapshot)
    assert recovered.snapshot.audit.status == AuditStatus.COMPLETED
    assert connector.calls == []
    assert recovered_evaluator.calls == ["T-2"]


def test_matrix_continues_other_runs_when_one_provider_fails():
    # The connector failure applies only to the first run's first test.
    class PerRunConnector(Connector):
        def execute(self, test, audit):
            self.calls.append(f"{audit.run_id}:{test.test_id}")
            if audit.run_id == "RUN-BAD":
                raise RuntimeError("provider unavailable")
            return TargetResponse(response_id=f"R-{test.test_id}", test_id=test.test_id, run_id=audit.run_id, response_text="answer", model=audit.model, temperature=0, created_at=NOW)

    # The generated tests must carry each row's ID, just like a persisted suite.
    class PerRunGenerator(Generator):
        def generate(self, _memories, audit):
            return [_test(f"{audit.run_id}-T") .model_copy(update={"run_id": audit.run_id})]

    snapshots = [
        AuditExecutionSnapshot(_audit("RUN-BAD"), [_memory()]),
        AuditExecutionSnapshot(_audit("RUN-GOOD"), [_memory()]),
    ]
    results = _service(generator=PerRunGenerator(), connector=PerRunConnector()).resume_matrix(snapshots)

    assert [item.snapshot.audit.status for item in results] == [AuditStatus.FAILED, AuditStatus.COMPLETED]
    assert results[0].error == "provider unavailable"
    assert results[1].error is None


def test_completed_stage_is_inferred_for_an_empty_generated_suite():
    snapshot = AuditExecutionSnapshot(_audit(status=AuditStatus.TESTS_GENERATED), [_memory()])
    service = _service(generator=Generator(tests=[]))
    result = service.resume(snapshot)

    assert result.snapshot.audit.status == AuditStatus.COMPLETED
    assert result.retry_plan.retryable is False
