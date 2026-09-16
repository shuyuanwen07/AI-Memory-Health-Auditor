"""Metrics for validating the Auditor against independently annotated labels.

Memory Health describes the *target agent*.  This module instead measures
whether the Auditor's PASS/FAIL decisions agree with a human annotation set.
It is deliberately dependency-free so a frozen CSV/JSON label set can be
analysed in a notebook, a future API endpoint, or the formal evaluation suite.
"""

from dataclasses import dataclass

from app.schemas import EvaluationResult


@dataclass(frozen=True)
class AuditorValidityReport:
    """Agreement of automated and human PASS/FAIL labels.

    A failed response is the positive class because the principal research
    question is whether the Auditor detects actual memory failures.
    Percentages are expressed as 0--100. ``None`` means the denominator does
    not exist in the labelled sample, rather than implying a zero result.
    """

    labelled_cases: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    accuracy: float | None
    failure_precision: float | None
    failure_recall: float | None
    false_positive_rate: float | None
    cohens_kappa: float | None


class AuditorValidityService:
    """Compare persisted evaluator decisions with independently made labels."""

    def calculate(
        self,
        evaluations: list[EvaluationResult],
        human_passed_by_test_id: dict[str, bool],
    ) -> AuditorValidityReport:
        """Calculate validity only over the intersection with human labels.

        As with ``MetricsService``, duplicate evaluator records do not inflate
        the sample: the first result for a test ID is retained. Human labels
        are represented as ``True`` for PASS and ``False`` for FAIL.
        """
        automated: dict[str, bool] = {}
        for evaluation in evaluations:
            if evaluation.test_id not in automated:
                automated[evaluation.test_id] = evaluation.passed

        tp = fp = tn = fn = 0
        for test_id, human_passed in human_passed_by_test_id.items():
            if test_id not in automated:
                continue
            # Failure is positive: false means the response/evaluation failed.
            human_failed = not human_passed
            auditor_failed = not automated[test_id]
            if human_failed and auditor_failed:
                tp += 1
            elif not human_failed and auditor_failed:
                fp += 1
            elif not human_failed and not auditor_failed:
                tn += 1
            else:
                fn += 1

        total = tp + fp + tn + fn
        accuracy = self._percent(tp + tn, total)
        precision = self._percent(tp, tp + fp)
        recall = self._percent(tp, tp + fn)
        false_positive_rate = self._percent(fp, fp + tn)
        kappa = self._kappa(tp, fp, tn, fn)
        return AuditorValidityReport(
            labelled_cases=total,
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            accuracy=accuracy,
            failure_precision=precision,
            failure_recall=recall,
            false_positive_rate=false_positive_rate,
            cohens_kappa=kappa,
        )

    @staticmethod
    def _percent(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator * 100, 1) if denominator else None

    @staticmethod
    def _kappa(tp: int, fp: int, tn: int, fn: int) -> float | None:
        total = tp + fp + tn + fn
        if not total:
            return None
        observed = (tp + tn) / total
        # Rows are human labels; columns are Auditor labels, failure positive.
        human_failure_rate = (tp + fn) / total
        auditor_failure_rate = (tp + fp) / total
        expected = (
            human_failure_rate * auditor_failure_rate
            + (1 - human_failure_rate) * (1 - auditor_failure_rate)
        )
        if expected == 1:
            # When both systems use only one category, agreement is either
            # complete but uninformative (undefined kappa) or cannot arise.
            return None
        return round((observed - expected) / (1 - expected), 3)
