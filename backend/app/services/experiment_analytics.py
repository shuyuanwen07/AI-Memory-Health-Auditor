"""Read-only analytics for reproducible experiment groups.

The canonical suite's test IDs are retained on cloned test rows through
``suite_test_id``.  This service uses that link rather than prompt text, so a
pairwise result is only reported when two runs really answered the same frozen
test.  It deliberately does not read target-agent memory or retrieval tables.
"""

from __future__ import annotations

from collections import defaultdict, Counter
from itertools import combinations
from math import comb, sqrt
from random import Random
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditRunModel, EvaluationResultModel, TestCaseModel, TargetResponseModel
from app.services.audit_comparison import assessment_signature
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
    retrieval_mode = getattr(run, "retrieval_mode", "fixed")
    retrieval_mode = getattr(retrieval_mode, "value", retrieval_mode)
    strategy = "AI retrieval Agent" if retrieval_mode == "agent" else run.memory_strategy.replace("_", " ").title()
    if retrieval_mode == "agent" and getattr(run, "retrieval_model", None):
        strategy += f" ({run.retrieval_provider} · {run.retrieval_model})"
    metadata = getattr(run, "reproducibility_metadata", None)
    profile = metadata.get("target_memory_profile", {}) if metadata else run.target_memory_profile.model_dump()
    label = profile.get("label", "Original configuration")
    provenance = metadata or run.reproducibility.model_dump()
    if provenance.get("auditor_comparison_id"):
        method = {"rules": "Rule tests + rule review", "model_generation": "Model tests + rule review", "hybrid": "Model tests + hybrid review"}.get(provenance.get("auditor_method"), "Custom audit")
        return f"{provider} · {run.model} · {strategy} · {method} · {label}"
    return f"{provider} · {run.model} · {strategy} · {label}"


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
    positives = sum(value > 0 for value in differences)
    negatives = sum(value < 0 for value in differences)
    discordant = positives + negatives
    if not discordant:
        p_value = 1.0
    else:
        smaller = min(positives, negatives)
        p_value = min(1.0, 2 * sum(comb(discordant, index) for index in range(smaller + 1)) / (2 ** discordant))
    if count < 2:
        # One observed question cannot estimate resampling variation.
        return None, None, round(p_value, 6)
    rng = Random(seed)
    samples = sorted(
        (sum(differences[rng.randrange(count)] for _ in range(count)) * 100 / count)
        for _ in range(2000)
    )
    low = samples[int((len(samples) - 1) * 0.025)]
    high = samples[int((len(samples) - 1) * 0.975)]
    return round(low, 3), round(high, 3), round(p_value, 6)


class ExperimentAnalyticsService:
    """Build condition/repeat summaries and exact pairwise pass/fail signals."""

    VERSION = "experiment-analytics-v3"

    @classmethod
    def analysis_metadata(cls) -> dict:
        return {"version": cls.VERSION, "interval_method": "deterministic_percentile_bootstrap",
                "bootstrap_samples": 2000, "resampling_unit": "paired_decided_question",
                "single_question_interval": "not_estimable", "sign_test": "two_sided_exact_ignoring_ties",
                "variation": "population_standard_deviation_of_available_scores",
                "assessment_alignment": "matching_complete_saved_assessment_signature",
                "notice": "Descriptive results for the observed questions and scored runs. Missing and uncertain judgments are excluded and must be reported separately. Zero-width intervals do not prove certainty. Independent scenarios, human labels and repeated trials are still required; configuration-unknown runs are not established repetitions."}

    def condition_summaries(
        self,
        runs: Iterable[AuditRun],
        results_by_run: dict[str, AuditResult],
        response_metadata_by_run: dict[str, list[dict]] | None = None,
    ) -> list[ExperimentConditionSummary]:
        grouped: dict[tuple[str, str, str], list[AuditRun]] = defaultdict(list)
        for run in runs:
            fingerprint = run.reproducibility.configuration_fingerprint
            # Legacy unknown configurations cannot establish a repeated condition.
            condition_identity = fingerprint or f"unverified-run:{run.run_id}"
            grouped[(run.provider.value, run.model, run.memory_strategy.value + "::" + condition_identity)].append(run)

        summaries: list[ExperimentConditionSummary] = []
        for (provider, model, condition_key), grouped_runs in grouped.items():
            completed = [run for run in grouped_runs if run.run_id in results_by_run]
            result_rows = [results_by_run[run.run_id] for run in completed]
            dimensions: list[ExperimentDimensionSummary] = []
            for dimension in Dimension:
                values = []
                passed = total = 0
                dimension_rows = [score for result in result_rows
                                  if (score := next((item for item in result.dimensions if item.dimension == dimension), None)) is not None]
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
                    uncertain_count=sum(score.uncertain_count for score in dimension_rows),
                    excluded_evidence_count=sum(score.excluded_evidence_count for score in dimension_rows),
                    expected_tests=sum(score.expected_tests for score in dimension_rows)
                    if result_rows and len(dimension_rows) == len(result_rows) and all(
                        score.expected_tests >= score.total + score.uncertain_count + score.excluded_evidence_count for score in dimension_rows) else None,
                ))
            scores = [result.overall_score for result in result_rows if result.overall_score is not None]
            exemplar = grouped_runs[0]
            response_rows = [
                row
                for run in completed
                for row in (response_metadata_by_run or {}).get(run.run_id, [])
            ]
            latency_values = [
                float(row["latency_ms"])
                for row in response_rows
                if isinstance(row.get("latency_ms"), (int, float))
            ]
            def complete_token_sum(key: str) -> int | None:
                values = [row.get(key) for row in response_rows]
                if not values or any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                    return None
                return sum(values)
            summaries.append(ExperimentConditionSummary(
                condition_id="::".join((provider, model, condition_key)),
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
                mean_latency_ms=_mean(latency_values),
                total_input_tokens=complete_token_sum("input_tokens"),
                total_output_tokens=complete_token_sum("output_tokens"),
                total_tokens=complete_token_sum("total_tokens"),
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
                TestCaseModel.comparison_test_id,
                EvaluationResultModel,
                TargetResponseModel.test_id,
                TargetResponseModel.run_id,
            )
            .outerjoin(EvaluationResultModel, EvaluationResultModel.test_id == TestCaseModel.id)
            .outerjoin(TargetResponseModel, TargetResponseModel.id == EvaluationResultModel.response_id)
            .where(TestCaseModel.run_id.in_(run_ids))
        ).all()
        outcomes: dict[str, dict[str, bool | None]] = defaultdict(dict)
        signatures = defaultdict(dict)
        runs_by_id = {run.run_id: run for run in completed}
        test_counts = Counter((row[0], row[1]) for row in rows)
        key_counts = Counter((row[0], row[3] or row[2] or row[1]) for row in rows)
        eligible = defaultdict(set)
        for run_id, test_id, suite_test_id, comparison_test_id, evaluation, response_test_id, response_run_id in rows:
            # The source test is its own canonical key.  A peer uses the source
            # link established during shared-suite cloning.
            key = comparison_test_id or suite_test_id or test_id
            usable = (test_counts[(run_id, test_id)] == 1 and key_counts[(run_id, key)] == 1
                      and evaluation is not None and response_test_id == test_id and response_run_id == run_id)
            outcomes[run_id][key] = evaluation.passed if usable else None
            signatures[run_id][key] = assessment_signature(runs_by_id[run_id], evaluation) if usable else None
            if usable:
                eligible[run_id].add(key)

        comparisons: list[PairedComparison] = []
        for reference, candidate in combinations(completed, 2):
            reference_outcomes = outcomes.get(reference.run_id, {})
            candidate_outcomes = outcomes.get(candidate.run_id, {})
            all_shared = sorted(set(reference_outcomes) & set(candidate_outcomes))
            structurally_shared = [key for key in all_shared if key in eligible[reference.run_id] and key in eligible[candidate.run_id]]
            decided_shared = [key for key in structurally_shared if reference_outcomes[key] is not None
                              and candidate_outcomes[key] is not None]
            shared = [key for key in decided_shared if signatures[reference.run_id][key] is not None
                      and signatures[reference.run_id][key] == signatures[candidate.run_id][key]]
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
                shared_question_count=len(all_shared),
                excluded_uncertain_count=len(structurally_shared) - len(decided_shared),
                excluded_assessment_count=len(all_shared) - len(structurally_shared) + len(decided_shared) - len(shared),
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
