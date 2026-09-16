"""Read-only analytics for reproducible experiment groups.

The canonical suite's test IDs are retained on cloned test rows through
``suite_test_id``.  This service uses that link rather than prompt text, so a
pairwise result is only reported when two runs really answered the same frozen
test.  It deliberately does not read target-agent memory or retrieval tables.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from math import comb, sqrt
from random import Random
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditRunModel, EvaluationResultModel, TestCaseModel
from app.schemas import (
    AuditResult,
    AuditRun,
    Dimension,
    ExperimentConditionSummary,
    ExperimentDimensionSummary,
    PairedComparison,
)


def condition_label(run: AuditRun | AuditRunModel) -> str:
    """Keep labels stable and readable across the history UI and CSV export."""
    provider = run.provider.replace("_", " ").title()
    strategy = run.memory_strategy.replace("_", " ").title()
    return f"{provider} · {run.model} · {strategy}"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return round(sqrt(sum((value - mean) ** 2 for value in values) / len(values)), 3)


def _paired_statistics(differences: list[int], seed: str) -> tuple[float | None, float | None, float | None]:
    """Return a deterministic percentile bootstrap interval and exact sign p-value.

    A test's value is +1 if only the candidate passes, -1 if only the
    reference passes and 0 otherwise.  The interval is over the mean change in
    pass rate (percentage points).  The sign test intentionally ignores ties.
    It is transparent and dependency-free, suitable for the small pilot groups
    this university system produces; it is not presented as a replacement for a
    preregistered large-sample analysis.
    """
    if not differences:
        return None, None, None
    count = len(differences)
    rng = Random(seed)
    samples = sorted(
        (sum(differences[rng.randrange(count)] for _ in range(count)) * 100 / count)
        for _ in range(2000)
    )
    low = samples[int((len(samples) - 1) * 0.025)]
    high = samples[int((len(samples) - 1) * 0.975)]
    positives = sum(value > 0 for value in differences)
    negatives = sum(value < 0 for value in differences)
    discordant = positives + negatives
    if not discordant:
        p_value = 1.0
    else:
        smaller = min(positives, negatives)
        p_value = min(1.0, 2 * sum(comb(discordant, index) for index in range(smaller + 1)) / (2 ** discordant))
    return round(low, 3), round(high, 3), round(p_value, 6)


class ExperimentAnalyticsService:
    """Build condition/repeat summaries and exact pairwise pass/fail signals."""

    def condition_summaries(
        self,
        runs: Iterable[AuditRun],
        results_by_run: dict[str, AuditResult],
    ) -> list[ExperimentConditionSummary]:
        grouped: dict[tuple[str, str, str], list[AuditRun]] = defaultdict(list)
        for run in runs:
            grouped[(run.provider.value, run.model, run.memory_strategy.value)].append(run)

        summaries: list[ExperimentConditionSummary] = []
        for (provider, model, strategy), grouped_runs in grouped.items():
            completed = [run for run in grouped_runs if run.run_id in results_by_run]
            result_rows = [results_by_run[run.run_id] for run in completed]
            dimensions: list[ExperimentDimensionSummary] = []
            for dimension in Dimension:
                values = []
                passed = total = 0
                for result in result_rows:
                    score = next((item for item in result.dimensions if item.dimension == dimension), None)
                    if score is None or score.percentage is None:
                        continue
                    values.append(score.percentage)
                    passed += score.passed
                    total += score.total
                dimensions.append(ExperimentDimensionSummary(
                    dimension=dimension,
                    mean_percentage=_mean(values),
                    standard_deviation=_standard_deviation(values),
                    passed=passed,
                    total=total,
                    measured_runs=len(values),
                ))
            scores = [result.overall_score for result in result_rows if result.overall_score is not None]
            exemplar = grouped_runs[0]
            summaries.append(ExperimentConditionSummary(
                condition_id="::".join((provider, model, strategy)),
                label=condition_label(exemplar),
                provider=exemplar.provider,
                model=model,
                memory_strategy=exemplar.memory_strategy,
                planned_runs=len(grouped_runs),
                completed_runs=len(completed),
                failed_runs=sum(run.status.value == "FAILED" for run in grouped_runs),
                run_ids=[run.run_id for run in grouped_runs],
                overall_mean=_mean(scores),
                overall_standard_deviation=_standard_deviation(scores),
                tests_passed=sum(result.tests_passed for result in result_rows),
                tests_total=sum(result.tests_total for result in result_rows),
                failure_count=sum(len(result.failures) for result in result_rows),
                dimensions=dimensions,
            ))
        return sorted(summaries, key=lambda item: item.label)

    def paired_comparisons(self, db: Session, runs: Iterable[AuditRun]) -> list[PairedComparison]:
        completed = [run for run in runs if run.status.value == "COMPLETED"]
        if len(completed) < 2:
            return []
        run_ids = [run.run_id for run in completed]
        rows = db.execute(
            select(
                TestCaseModel.run_id,
                TestCaseModel.id,
                TestCaseModel.suite_test_id,
                EvaluationResultModel.passed,
            )
            .join(EvaluationResultModel, EvaluationResultModel.test_id == TestCaseModel.id)
            .where(TestCaseModel.run_id.in_(run_ids))
        ).all()
        outcomes: dict[str, dict[str, bool]] = defaultdict(dict)
        for run_id, test_id, suite_test_id, passed in rows:
            # The source test is its own canonical key.  A peer uses the source
            # link established during shared-suite cloning.
            outcomes[run_id][suite_test_id or test_id] = bool(passed)

        comparisons: list[PairedComparison] = []
        for reference, candidate in combinations(completed, 2):
            reference_outcomes = outcomes.get(reference.run_id, {})
            candidate_outcomes = outcomes.get(candidate.run_id, {})
            shared = sorted(set(reference_outcomes) & set(candidate_outcomes))
            both_passed = both_failed = reference_only = candidate_only = 0
            differences: list[int] = []
            for test_id in shared:
                left, right = reference_outcomes[test_id], candidate_outcomes[test_id]
                if left and right:
                    both_passed += 1
                elif not left and not right:
                    both_failed += 1
                elif left:
                    reference_only += 1
                    differences.append(-1)
                else:
                    candidate_only += 1
                    differences.append(1)
                if left == right:
                    differences.append(0)
            delta = None if not shared else round((candidate_only - reference_only) * 100 / len(shared), 3)
            interval_low, interval_high, p_value = _paired_statistics(
                differences, f"{reference.run_id}:{candidate.run_id}",
            )
            comparisons.append(PairedComparison(
                reference_run_id=reference.run_id,
                reference_label=condition_label(reference),
                candidate_run_id=candidate.run_id,
                candidate_label=condition_label(candidate),
                shared_tests=len(shared),
                both_passed=both_passed,
                both_failed=both_failed,
                reference_only_passed=reference_only,
                candidate_only_passed=candidate_only,
                candidate_delta_percentage_points=delta,
                candidate_delta_confidence_interval_low=interval_low,
                candidate_delta_confidence_interval_high=interval_high,
                two_sided_sign_test_p_value=p_value,
            ))
        return comparisons
