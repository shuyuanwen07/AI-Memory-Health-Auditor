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


def test_single_question_has_no_bootstrap_interval_but_keeps_exact_sign_result():
    from app.services.experiment_analytics import _paired_statistics
    for change in (-1, 0, 1):
        assert _paired_statistics([change], "one-question") == (None, None, 1.0)
    assert _paired_statistics([], "empty") == (None, None, None)


def test_paired_interval_is_reproducible_and_sign_test_counts_only_changed_outcomes():
    from app.services.experiment_analytics import _paired_statistics
    result = _paired_statistics([1, 1, 1, 1, 0, 0], "fixed-source")
    assert result == _paired_statistics([1, 1, 1, 1, 0, 0], "fixed-source")
    assert result[2] == 0.125
    assert result[0] <= 100 * 4 / 6 <= result[1]


def test_unknown_configuration_records_are_not_claimed_as_repeated_conditions():
    runs = [_run("LEGACY-ONE"), _run("LEGACY-TWO")]
    summaries = ExperimentAnalyticsService().condition_summaries(runs, {run.run_id:_result(run.run_id) for run in runs})
    assert len(summaries) == 2
    assert all(summary.completed_runs == summary.planned_runs == 1 for summary in summaries)
    assert all(summary.overall_standard_deviation is None for summary in summaries)


def test_recorded_common_configuration_can_still_group_actual_repetitions():
    runs = [_run("FROZEN-ONE"), _run("FROZEN-TWO")]
    for run in runs:
        run.reproducibility.configuration_fingerprint = "a" * 64
    summaries = ExperimentAnalyticsService().condition_summaries(runs, {run.run_id:_result(run.run_id) for run in runs})
    assert len(summaries) == 1
    assert summaries[0].completed_runs == summaries[0].planned_runs == 2
    assert summaries[0].overall_standard_deviation == 0


def test_condition_dimension_preserves_pending_and_unavailable_evidence_across_repeats():
    runs = [_run('ONE'), _run('TWO')]
    for run in runs:
        run.reproducibility.configuration_fingerprint = 'b' * 64
    rows = {
        'ONE': _result('ONE').model_copy(update={'dimensions': [DimensionScores(dimension=Dimension.ACCURACY, percentage=100, passed=1, total=1, expected_tests=3, uncertain_count=1, excluded_evidence_count=1)]}),
        'TWO': _result('TWO').model_copy(update={'dimensions': [DimensionScores(dimension=Dimension.ACCURACY, percentage=None, passed=0, total=0, expected_tests=2, uncertain_count=1, excluded_evidence_count=1)]}),
    }
    summary = ExperimentAnalyticsService().condition_summaries(runs, rows)[0]
    accuracy = next(score for score in summary.dimensions if score.dimension == Dimension.ACCURACY)
    assert (accuracy.mean_percentage, accuracy.passed, accuracy.total, accuracy.measured_runs) == (100, 1, 1, 1)
    assert (accuracy.uncertain_count, accuracy.excluded_evidence_count, accuracy.expected_tests) == (2, 2, 5)


def test_legacy_dimension_without_a_valid_saved_question_count_keeps_expected_count_unknown():
    summary = ExperimentAnalyticsService().condition_summaries([_run('LEGACY')], {'LEGACY': _result('LEGACY')})[0]
    assert all(score.expected_tests is None for score in summary.dimensions)
