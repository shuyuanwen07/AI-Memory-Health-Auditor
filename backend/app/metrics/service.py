"""Deterministic, auditable Memory Health score calculation.

An unmeasured dimension is represented by ``None`` instead of zero. This
keeps benchmark summaries honest: an audit that did not test freshness cannot
be read as evidence of zero freshness performance.
"""

from app.schemas import Dimension, DimensionScores, EvaluationResult


class MetricsService:
    """Calculate scores without treating an untested dimension as zero.

    Only evaluations mapped to a known test are valid. At most one evaluation
    per test contributes to a score, which protects aggregates from accidental
    duplicate records while preserving the public API.
    """

    def calculate(
        self,
        evaluations: list[EvaluationResult],
        tests: dict[str, Dimension],
    ) -> tuple[float | None, list[DimensionScores]]:
        # Evaluation records should be unique per test. If an integration sends
        # a duplicate, retaining the first persisted evaluation prevents it
        # from inflating either the numerator or denominator.
        valid_by_test: dict[str, EvaluationResult] = {}
        for evaluation in evaluations:
            if evaluation.test_id in tests and evaluation.test_id not in valid_by_test:
                valid_by_test[evaluation.test_id] = evaluation

        scores: list[DimensionScores] = []
        for dimension in Dimension:
            scoped = [
                evaluation
                for test_id, evaluation in valid_by_test.items()
                if tests[test_id] == dimension
            ]
            total = len(scoped)
            passed = sum(evaluation.passed for evaluation in scoped)
            scores.append(DimensionScores(
                dimension=dimension,
                percentage=round((passed / total) * 100, 1) if total else None,
                passed=passed,
                total=total,
            ))

        # Macro-average only across dimensions with one or more valid tests.
        measured = [score.percentage for score in scores if score.percentage is not None]
        return (round(sum(measured) / len(measured), 1) if measured else None, scores)
