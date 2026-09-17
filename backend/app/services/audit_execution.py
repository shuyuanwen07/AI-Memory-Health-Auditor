"""Recoverable audit-stage semantics for one audit run.

The pure service is used directly by worker-capable callers and its retry-plan
derivation is also used by the synchronous API route after it loads durable
artifacts. This keeps browser recovery and future worker orchestration aligned
without coupling provider calls to SQLAlchemy persistence.

The service has no database or HTTP dependency.  Its collaborators are the
existing replaceable generator, target connector, and evaluator interfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Iterable

from app.schemas import (
    AuditRun,
    AuditStatus,
    EvaluationResult,
    Memory,
    TargetResponse,
    TestCase,
)
from app.services.interfaces import BehaviourEvaluator, TargetAIConnector, TestGenerator


class AuditStage(str, Enum):
    """The three idempotent work stages of a run, plus its terminal state."""

    GENERATE_TESTS = "generate_tests"
    EXECUTE_TESTS = "execute_tests"
    EVALUATE_RESPONSES = "evaluate_responses"
    COMPLETE = "complete"


class EventKind(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class AuditStatusEvent:
    """A persistable, presentation-safe state transition event."""

    stage: AuditStage
    kind: EventKind
    at: datetime
    detail: str = ""


@dataclass
class RunArtifacts:
    """Artifacts already durably saved for a run.

    Keying by test id makes execution and evaluation retry-safe: a completed
    response or evaluation is never submitted to a provider a second time.
    """

    tests: dict[str, TestCase] = field(default_factory=dict)
    responses: dict[str, TargetResponse] = field(default_factory=dict)
    evaluations: dict[str, EvaluationResult] = field(default_factory=dict)

    @classmethod
    def from_lists(
        cls,
        tests: Iterable[TestCase] = (),
        responses: Iterable[TargetResponse] = (),
        evaluations: Iterable[EvaluationResult] = (),
    ) -> "RunArtifacts":
        return cls(
            tests={item.test_id: item for item in tests},
            responses={item.test_id: item for item in responses},
            evaluations={item.test_id: item for item in evaluations},
        )


@dataclass
class AuditExecutionSnapshot:
    """All data the service needs for one audit run.

    ``completed_stages`` and ``events`` can be persisted by a future event-log
    table.  They are optional today because existing durable test/response/
    evaluation artifacts are sufficient to infer safe retries for non-empty
    test suites.
    """

    audit: AuditRun
    # Retry planning is useful even when routes deliberately load only
    # durable artifacts. Full orchestration still receives confirmed memories.
    memories: list[Memory] = field(default_factory=list)
    artifacts: RunArtifacts = field(default_factory=RunArtifacts)
    completed_stages: set[AuditStage] = field(default_factory=set)
    events: list[AuditStatusEvent] = field(default_factory=list)


@dataclass(frozen=True)
class RetryPlan:
    run_id: str
    next_stage: AuditStage | None
    pending_test_ids: tuple[str, ...]
    completed_stages: tuple[AuditStage, ...]
    retryable: bool
    reason: str


@dataclass
class AuditExecutionResult:
    snapshot: AuditExecutionSnapshot
    retry_plan: RetryPlan
    error: str | None = None


Clock = Callable[[], datetime]


class AuditExecutionService:
    """Advance one run through generate -> execute -> evaluate safely.

    A failed run returns a result rather than throwing.  Callers can therefore
    execute a whole experiment matrix and retain a result for every model /
    memory-strategy combination even if one remote provider is unavailable.
    """

    def __init__(
        self,
        generator: TestGenerator,
        connector: TargetAIConnector,
        evaluator: BehaviourEvaluator,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.generator = generator
        self.connector = connector
        self.evaluator = evaluator
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def retry_plan(self, snapshot: AuditExecutionSnapshot) -> RetryPlan:
        return self.plan_for(snapshot)

    @classmethod
    def plan_for(cls, snapshot: AuditExecutionSnapshot) -> RetryPlan:
        """Derive the durable retry plan without invoking any collaborator.

        API routes use this same method after loading persisted artifacts, so
        browser-visible recovery and in-process orchestration cannot diverge.
        """
        if snapshot.audit.status == AuditStatus.CANCELLED:
            return cls._plan(snapshot, None, (), set(), "This audit was cancelled and is terminal.")
        if snapshot.audit.status == AuditStatus.COMPLETED:
            return cls._plan(snapshot, None, (), {
                AuditStage.GENERATE_TESTS, AuditStage.EXECUTE_TESTS, AuditStage.EVALUATE_RESPONSES,
            }, "This audit is already complete.")
        completed = cls._completed_stages(snapshot)
        test_ids = tuple(snapshot.artifacts.tests)
        if AuditStage.GENERATE_TESTS not in completed:
            return cls._plan(snapshot, AuditStage.GENERATE_TESTS, (), completed, "Tests have not been generated.")

        pending_responses = tuple(
            test_id for test_id in test_ids if test_id not in snapshot.artifacts.responses
        )
        if pending_responses:
            return cls._plan(snapshot, AuditStage.EXECUTE_TESTS, pending_responses, completed, "Some target responses are missing.")

        pending_evaluations = tuple(
            test_id for test_id in test_ids if test_id not in snapshot.artifacts.evaluations
        )
        if pending_evaluations:
            return cls._plan(snapshot, AuditStage.EVALUATE_RESPONSES, pending_evaluations, completed, "Some target responses have not been evaluated.")

        return cls._plan(snapshot, None, (), completed | {AuditStage.COMPLETE}, "All audit stages are complete.")

    def resume(self, snapshot: AuditExecutionSnapshot) -> AuditExecutionResult:
        """Resume from the first missing artifact without repeating prior work."""
        while True:
            plan = self.retry_plan(snapshot)
            if plan.next_stage is None:
                self._mark_completed(snapshot)
                return AuditExecutionResult(snapshot=snapshot, retry_plan=self.retry_plan(snapshot))

            stage = plan.next_stage
            self._event(snapshot, stage, EventKind.STARTED)
            try:
                if stage == AuditStage.GENERATE_TESTS:
                    self._generate(snapshot)
                elif stage == AuditStage.EXECUTE_TESTS:
                    self._execute(snapshot, plan.pending_test_ids)
                elif stage == AuditStage.EVALUATE_RESPONSES:
                    self._evaluate(snapshot, plan.pending_test_ids)
                else:  # pragma: no cover - Enum guards this branch.
                    raise RuntimeError(f"Unsupported audit stage: {stage}")
            except Exception as exc:  # Provider and validation failures are per-run outcomes.
                snapshot.audit = snapshot.audit.model_copy(update={"status": AuditStatus.FAILED, "completed_at": None})
                self._event(snapshot, stage, EventKind.FAILED, self._safe_error(exc))
                return AuditExecutionResult(snapshot=snapshot, retry_plan=self.retry_plan(snapshot), error=self._safe_error(exc))

            snapshot.completed_stages.add(stage)
            self._event(snapshot, stage, EventKind.COMPLETED)

    def resume_matrix(self, snapshots: Iterable[AuditExecutionSnapshot]) -> list[AuditExecutionResult]:
        """Run independent matrix rows; an individual failure never stops peers."""
        results: list[AuditExecutionResult] = []
        for snapshot in snapshots:
            try:
                results.append(self.resume(snapshot))
            except Exception as exc:  # Defensive boundary for malformed input.
                snapshot.audit = snapshot.audit.model_copy(update={"status": AuditStatus.FAILED, "completed_at": None})
                self._event(snapshot, AuditStage.COMPLETE, EventKind.FAILED, self._safe_error(exc))
                results.append(AuditExecutionResult(snapshot, self.retry_plan(snapshot), self._safe_error(exc)))
        return results

    def _generate(self, snapshot: AuditExecutionSnapshot) -> None:
        generated = self.generator.generate(snapshot.memories, snapshot.audit)
        tests = {test.test_id: test for test in generated}
        if len(tests) != len(generated):
            raise ValueError("The test generator returned duplicate test IDs.")
        snapshot.artifacts.tests.update(tests)
        snapshot.audit = snapshot.audit.model_copy(update={"status": AuditStatus.TESTS_GENERATED, "completed_at": None})

    def _execute(self, snapshot: AuditExecutionSnapshot, pending_test_ids: tuple[str, ...]) -> None:
        # Add each output immediately to the returned snapshot.  The route can
        # persist completed ones even when a later cloud call fails.
        for test_id in pending_test_ids:
            response = self.connector.execute(snapshot.artifacts.tests[test_id], snapshot.audit)
            if response.test_id != test_id:
                raise ValueError(f"Target connector returned a response for {response.test_id}, expected {test_id}.")
            snapshot.artifacts.responses[test_id] = response
        snapshot.audit = snapshot.audit.model_copy(update={"status": AuditStatus.TESTS_EXECUTED, "completed_at": None})

    def _evaluate(self, snapshot: AuditExecutionSnapshot, pending_test_ids: tuple[str, ...]) -> None:
        for test_id in pending_test_ids:
            evaluation = self.evaluator.evaluate(
                snapshot.artifacts.tests[test_id], snapshot.artifacts.responses[test_id], snapshot.memories
            )
            if evaluation.test_id != test_id:
                raise ValueError(f"Evaluator returned an evaluation for {evaluation.test_id}, expected {test_id}.")
            snapshot.artifacts.evaluations[test_id] = evaluation
        # Keep the durable lifecycle at TESTS_EXECUTED until `_mark_completed`
        # performs the single public transition to COMPLETED.  This mirrors
        # the API route and avoids an unpersisted EVALUATED state.

    def _mark_completed(self, snapshot: AuditExecutionSnapshot) -> None:
        if snapshot.audit.status != AuditStatus.COMPLETED:
            snapshot.audit = snapshot.audit.model_copy(
                update={"status": AuditStatus.COMPLETED, "completed_at": snapshot.audit.completed_at or self.clock()}
            )
            self._event(snapshot, AuditStage.COMPLETE, EventKind.COMPLETED)

    @staticmethod
    def _completed_stages(snapshot: AuditExecutionSnapshot) -> set[AuditStage]:
        completed = set(snapshot.completed_stages)
        status = snapshot.audit.status
        # Status is useful for an empty generated suite.  Durable artifacts are
        # the authority after FAILED, where status alone lost the prior stage.
        if status in {AuditStatus.TESTS_GENERATED, AuditStatus.TESTS_EXECUTED, AuditStatus.COMPLETED}:
            completed.add(AuditStage.GENERATE_TESTS)
        if status in {AuditStatus.TESTS_EXECUTED, AuditStatus.COMPLETED}:
            completed.add(AuditStage.EXECUTE_TESTS)
        if status == AuditStatus.COMPLETED:
            completed.add(AuditStage.EVALUATE_RESPONSES)
        if snapshot.artifacts.tests:
            completed.add(AuditStage.GENERATE_TESTS)
        if snapshot.artifacts.tests and all(key in snapshot.artifacts.responses for key in snapshot.artifacts.tests):
            completed.add(AuditStage.EXECUTE_TESTS)
        if snapshot.artifacts.tests and all(key in snapshot.artifacts.evaluations for key in snapshot.artifacts.tests):
            completed.add(AuditStage.EVALUATE_RESPONSES)
        return completed

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        # Do not accidentally return response bodies or credentials through an
        # event stream.  Provider adapters already issue user-safe messages.
        message = str(exc).replace("\n", " ").strip()
        return message[:500] or exc.__class__.__name__

    @staticmethod
    def _plan(
        snapshot: AuditExecutionSnapshot,
        next_stage: AuditStage | None,
        pending_test_ids: tuple[str, ...],
        completed: set[AuditStage],
        reason: str,
    ) -> RetryPlan:
        ordered = tuple(stage for stage in (AuditStage.GENERATE_TESTS, AuditStage.EXECUTE_TESTS, AuditStage.EVALUATE_RESPONSES) if stage in completed)
        return RetryPlan(
            run_id=snapshot.audit.run_id,
            next_stage=next_stage,
            pending_test_ids=pending_test_ids,
            completed_stages=ordered,
            retryable=next_stage is not None,
            reason=reason,
        )

    def _event(self, snapshot: AuditExecutionSnapshot, stage: AuditStage, kind: EventKind, detail: str = "") -> None:
        snapshot.events.append(AuditStatusEvent(stage=stage, kind=kind, at=self.clock(), detail=detail))
