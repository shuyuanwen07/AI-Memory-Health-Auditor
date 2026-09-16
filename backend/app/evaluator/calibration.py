"""Human-review calibration for the automated behaviour evaluator.

This module is deliberately request/data-set scoped.  It compares an
automated verdict with an independently assigned human verdict and does not
persist research labels, source conversation text, prompts, or provider
credentials.  A route, notebook, or CLI can import these contracts without
changing operational audit tables.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from pydantic import BaseModel, Field, model_validator

from app.schemas.domain import Dimension


class EvaluatorHumanReviewCase(BaseModel):
    """One independently reviewed evaluator decision.

    ``dimension`` is the dimension exercised by the test, rather than an
    inferred failure type.  Failure-type labels are optional because a human
    reviewer may establish PASS/FAIL before classifying the precise failure.
    """

    case_id: str = Field(min_length=1)
    dimension: Dimension
    evaluator_passed: bool
    human_passed: bool
    evaluator_failure_type: Dimension | None = None
    human_failure_type: Dimension | None = None

    @model_validator(mode="after")
    def failure_types_match_verdicts(self) -> "EvaluatorHumanReviewCase":
        if self.evaluator_passed and self.evaluator_failure_type is not None:
            raise ValueError("A passing evaluator verdict cannot have an evaluator_failure_type.")
        if self.human_passed and self.human_failure_type is not None:
            raise ValueError("A passing human verdict cannot have a human_failure_type.")
        return self


class EvaluatorCalibrationRequest(BaseModel):
    """A versioned, de-identified batch of human-review decisions."""

    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    review_set_id: str = Field(min_length=1)
    cases: list[EvaluatorHumanReviewCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> "EvaluatorCalibrationRequest":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("A calibration request cannot contain duplicate case_id values.")
        return self


class FailureDetectionMetrics(BaseModel):
    """Binary agreement metrics where a memory failure is the positive class."""

    labelled_cases: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    agreement_count: int
    disagreement_count: int
    percent_agreement: float | None
    accuracy: float | None
    failure_precision: float | None
    failure_recall: float | None
    failure_f1: float | None
    specificity: float | None
    false_positive_rate: float | None
    cohens_kappa: float | None


class FailureTypeConfusionCell(BaseModel):
    """A single non-zero cell in a human-row/evaluator-column confusion table."""

    human_failure_type: Dimension
    evaluator_failure_type: Dimension
    count: int = Field(ge=1)


class FailureTypeAgreementMetrics(BaseModel):
    """Failure-type agreement, conditional on both parties detecting failure."""

    human_failure_cases: int
    evaluator_failure_cases: int
    paired_typed_failure_cases: int
    exact_type_agreement_count: int
    exact_type_agreement_percent: float | None
    human_type_coverage_percent: float | None
    evaluator_type_coverage_percent: float | None
    confusion_cells: list[FailureTypeConfusionCell] = Field(default_factory=list)


class DimensionCalibrationMetrics(BaseModel):
    """Calibration result for the dimension that a test was designed to exercise."""

    dimension: Dimension
    failure_detection: FailureDetectionMetrics
    failure_type_agreement: FailureTypeAgreementMetrics


class EvaluatorCalibrationReport(BaseModel):
    """Portable report for a frozen human-review release."""

    dataset_id: str
    dataset_version: str
    review_set_id: str
    fingerprint_sha256: str
    retention: str = "request_scoped_not_persisted"
    overall_failure_detection: FailureDetectionMetrics
    overall_failure_type_agreement: FailureTypeAgreementMetrics
    by_dimension: list[DimensionCalibrationMetrics]


class EvaluatorCalibrationService:
    """Calculate reproducible evaluator-versus-human calibration statistics."""

    def analyse(self, request: EvaluatorCalibrationRequest) -> EvaluatorCalibrationReport:
        return EvaluatorCalibrationReport(
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            review_set_id=request.review_set_id,
            fingerprint_sha256=calibration_fingerprint(request),
            overall_failure_detection=self._failure_detection(request.cases),
            overall_failure_type_agreement=self._failure_type_agreement(request.cases),
            by_dimension=[
                DimensionCalibrationMetrics(
                    dimension=dimension,
                    failure_detection=self._failure_detection(cases),
                    failure_type_agreement=self._failure_type_agreement(cases),
                )
                for dimension in Dimension
                if (cases := [case for case in request.cases if case.dimension == dimension])
            ],
        )

    @classmethod
    def _failure_detection(cls, cases: list[EvaluatorHumanReviewCase]) -> FailureDetectionMetrics:
        # The target outcome is a real memory failure: a false ``passed`` label.
        tp = fp = tn = fn = 0
        for case in cases:
            human_failed = not case.human_passed
            evaluator_failed = not case.evaluator_passed
            if human_failed and evaluator_failed:
                tp += 1
            elif evaluator_failed:
                fp += 1
            elif human_failed:
                fn += 1
            else:
                tn += 1

        total = tp + fp + tn + fn
        return FailureDetectionMetrics(
            labelled_cases=total,
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
            agreement_count=tp + tn,
            disagreement_count=fp + fn,
            percent_agreement=cls._percent(tp + tn, total),
            accuracy=cls._percent(tp + tn, total),
            failure_precision=cls._percent(tp, tp + fp),
            failure_recall=cls._percent(tp, tp + fn),
            failure_f1=cls._f1(tp, fp, fn),
            specificity=cls._percent(tn, tn + fp),
            false_positive_rate=cls._percent(fp, fp + tn),
            cohens_kappa=cls._kappa(tp, fp, tn, fn),
        )

    @classmethod
    def _failure_type_agreement(cls, cases: list[EvaluatorHumanReviewCase]) -> FailureTypeAgreementMetrics:
        human_failure_cases = sum(not case.human_passed for case in cases)
        evaluator_failure_cases = sum(not case.evaluator_passed for case in cases)
        human_typed = sum(case.human_failure_type is not None for case in cases if not case.human_passed)
        evaluator_typed = sum(case.evaluator_failure_type is not None for case in cases if not case.evaluator_passed)
        paired = [
            case
            for case in cases
            if not case.human_passed
            and not case.evaluator_passed
            and case.human_failure_type is not None
            and case.evaluator_failure_type is not None
        ]
        counts = Counter((case.human_failure_type, case.evaluator_failure_type) for case in paired)
        exact = sum(count for (human, evaluator), count in counts.items() if human == evaluator)
        cells = [
            FailureTypeConfusionCell(human_failure_type=human, evaluator_failure_type=evaluator, count=count)
            for (human, evaluator), count in sorted(counts.items(), key=lambda item: (item[0][0].value, item[0][1].value))
        ]
        return FailureTypeAgreementMetrics(
            human_failure_cases=human_failure_cases,
            evaluator_failure_cases=evaluator_failure_cases,
            paired_typed_failure_cases=len(paired),
            exact_type_agreement_count=exact,
            exact_type_agreement_percent=cls._percent(exact, len(paired)),
            human_type_coverage_percent=cls._percent(human_typed, human_failure_cases),
            evaluator_type_coverage_percent=cls._percent(evaluator_typed, evaluator_failure_cases),
            confusion_cells=cells,
        )

    @staticmethod
    def _percent(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator * 100, 1) if denominator else None

    @classmethod
    def _f1(cls, true_positives: int, false_positives: int, false_negatives: int) -> float | None:
        precision = cls._percent(true_positives, true_positives + false_positives)
        recall = cls._percent(true_positives, true_positives + false_negatives)
        if precision is None or recall is None or precision + recall == 0:
            return None
        return round(2 * precision * recall / (precision + recall), 1)

    @staticmethod
    def _kappa(tp: int, fp: int, tn: int, fn: int) -> float | None:
        total = tp + fp + tn + fn
        if not total:
            return None
        observed = (tp + tn) / total
        human_failure_rate = (tp + fn) / total
        evaluator_failure_rate = (tp + fp) / total
        expected = human_failure_rate * evaluator_failure_rate + (1 - human_failure_rate) * (1 - evaluator_failure_rate)
        return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def calibration_fingerprint(request: EvaluatorCalibrationRequest) -> str:
    """Return a stable content fingerprint for recording the reviewed release."""
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
