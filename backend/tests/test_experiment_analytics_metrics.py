from datetime import datetime, timezone

from app.schemas import AuditResult, AuditRun, AuditStatus, Dimension, DimensionScores, MemoryStrategy, TargetConfiguration, TargetProvider
from app.services.experiment_analytics import ExperimentAnalyticsService


def _run(run_id: str) -> AuditRun:
    return AuditRun(
        run_id=run_id,
        conversation_id="C1",
        status=AuditStatus.COMPLETED,
        target_configuration=TargetConfiguration.STRONG,
        provider=TargetProvider.OLLAMA,
        model="qwen3:1.7b",
        temperature=0,
        random_seed=42,
        test_budget=4,
        prompt_template_version="test-v1",
        memory_strategy=MemoryStrategy.STRONG_RULE_BASED,
        created_at=datetime.now(timezone.utc),
    )


def _result(run_id: str) -> AuditResult:
    return AuditResult(
        run_id=run_id,
        overall_score=75,
        tests_passed=3,
        tests_total=4,
        dimensions=[DimensionScores(dimension=dimension, percentage=75, passed=3, total=4) for dimension in Dimension],
        failures=[],
    )


def test_condition_summary_aggregates_recorded_runtime_metadata():
    service = ExperimentAnalyticsService()
    summary = service.condition_summaries(
        [_run("RUN1")],
        {"RUN1": _result("RUN1")},
        {"RUN1": [
            {"latency_ms": 10.0, "input_tokens": 4, "output_tokens": 6, "total_tokens": 10},
            {"latency_ms": 30.0, "input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        ]},
    )[0]

    assert summary.mean_latency_ms == 20.0
    assert summary.total_input_tokens == 9
    assert summary.total_output_tokens == 13
    assert summary.total_tokens == 22


def test_condition_summary_does_not_present_partial_token_counts_as_totals():
    service = ExperimentAnalyticsService()
    summary = service.condition_summaries(
        [_run("RUN1")],
        {"RUN1": _result("RUN1")},
        {"RUN1": [{"latency_ms": 10.0, "input_tokens": None, "output_tokens": 6, "total_tokens": None}]},
    )[0]

    assert summary.mean_latency_ms == 10.0
    assert summary.total_input_tokens is None
    assert summary.total_output_tokens == 6
    assert summary.total_tokens is None
