import pytest
from pydantic import ValidationError

from app.evaluator.calibration import EvaluatorCalibrationRequest, EvaluatorCalibrationService


def _request() -> EvaluatorCalibrationRequest:
    return EvaluatorCalibrationRequest.model_validate(
        {
            "dataset_id": "deidentified-evaluator-set",
            "dataset_version": "2026.1",
            "review_set_id": "reviewer-pair-a",
            "cases": [
                # TP: human and evaluator find the same, correctly typed failure.
                {"case_id": "C1", "dimension": "freshness", "evaluator_passed": False, "human_passed": False, "evaluator_failure_type": "freshness", "human_failure_type": "freshness"},
                # FP: automated evaluator reports a failure that human review rejects.
                {"case_id": "C2", "dimension": "freshness", "evaluator_passed": False, "human_passed": True, "evaluator_failure_type": "freshness"},
                # TN: both agree the response passes.
                {"case_id": "C3", "dimension": "accuracy", "evaluator_passed": True, "human_passed": True},
                # FN: evaluator misses a human-confirmed conflict failure.
                {"case_id": "C4", "dimension": "conflict_resolution", "evaluator_passed": True, "human_passed": False, "human_failure_type": "conflict_resolution"},
                # Both find a failure but disagree about its taxonomy.
                {"case_id": "C5", "dimension": "appropriate_use", "evaluator_passed": False, "human_passed": False, "evaluator_failure_type": "accuracy", "human_failure_type": "appropriate_use"},
            ],
        }
    )


def test_calibration_reports_binary_agreement_and_dimension_breakdown():
    report = EvaluatorCalibrationService().analyse(_request())

    assert report.retention == "request_scoped_not_persisted"
    assert report.fingerprint_sha256
    overall = report.overall_failure_detection
    assert (overall.true_positives, overall.false_positives, overall.true_negatives, overall.false_negatives) == (2, 1, 1, 1)
    assert overall.percent_agreement == 60.0
    assert overall.failure_precision == 66.7
    assert overall.failure_recall == 66.7
    assert overall.failure_f1 == 66.7
    assert overall.specificity == 50.0
    assert overall.false_positive_rate == 50.0
    assert overall.cohens_kappa == 0.167

    freshness = next(item for item in report.by_dimension if item.dimension.value == "freshness")
    assert freshness.failure_detection.labelled_cases == 2
    assert freshness.failure_detection.true_positives == 1
    assert freshness.failure_detection.false_positives == 1


def test_calibration_reports_failure_type_confusion_and_coverage():
    report = EvaluatorCalibrationService().analyse(_request())
    types = report.overall_failure_type_agreement

    assert types.human_failure_cases == 3
    assert types.evaluator_failure_cases == 3
    assert types.paired_typed_failure_cases == 2
    assert types.exact_type_agreement_count == 1
    assert types.exact_type_agreement_percent == 50.0
    assert types.human_type_coverage_percent == 100.0
    assert types.evaluator_type_coverage_percent == 100.0
    assert [cell.model_dump(mode="json") for cell in types.confusion_cells] == [
        {"human_failure_type": "appropriate_use", "evaluator_failure_type": "accuracy", "count": 1},
        {"human_failure_type": "freshness", "evaluator_failure_type": "freshness", "count": 1},
    ]


def test_calibration_rejects_duplicate_or_inconsistent_cases():
    payload = _request().model_dump(mode="json")
    payload["cases"].append(payload["cases"][0])
    with pytest.raises(ValidationError, match="duplicate case_id"):
        EvaluatorCalibrationRequest.model_validate(payload)

    payload = _request().model_dump(mode="json")
    payload["cases"][0]["evaluator_passed"] = True
    with pytest.raises(ValidationError, match="passing evaluator"):
        EvaluatorCalibrationRequest.model_validate(payload)


def test_calibration_keeps_undefined_denominators_null():
    request = EvaluatorCalibrationRequest.model_validate(
        {
            "dataset_id": "set", "dataset_version": "v1", "review_set_id": "r1",
            "cases": [{"case_id": "pass", "dimension": "accuracy", "evaluator_passed": True, "human_passed": True}],
        }
    )
    metrics = EvaluatorCalibrationService().analyse(request).overall_failure_detection
    assert metrics.failure_precision is None
    assert metrics.failure_recall is None
    assert metrics.failure_f1 is None
    assert metrics.false_positive_rate == 0.0
    assert metrics.cohens_kappa is None
