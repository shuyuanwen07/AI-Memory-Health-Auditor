from app.metrics.validity import AuditorValidityService
from app.schemas import EvaluationResult


def decision(test_id: str, passed: bool) -> EvaluationResult:
    return EvaluationResult(
        evaluation_id=f"E-{test_id}", test_id=test_id, response_id=f"R-{test_id}",
        passed=passed, failure_type=None, reason="label", evidence_memory_ids=[],
        evaluator="rule-based-v1",
    )


def test_validity_counts_failure_detection_and_agreement():
    report = AuditorValidityService().calculate(
        [
            decision("actual-failure-detected", False),
            decision("false-alarm", False),
            decision("correct-pass", True),
            decision("missed-failure", True),
            decision("unlabelled", False),
        ],
        {
            "actual-failure-detected": False,
            "false-alarm": True,
            "correct-pass": True,
            "missed-failure": False,
        },
    )
    assert report.labelled_cases == 4
    assert (report.true_positives, report.false_positives, report.true_negatives, report.false_negatives) == (1, 1, 1, 1)
    assert report.accuracy == 50.0
    assert report.failure_precision == 50.0
    assert report.failure_recall == 50.0
    assert report.false_positive_rate == 50.0
    assert report.cohens_kappa == 0.0


def test_validity_keeps_missing_denominators_unknown_and_ignores_duplicates():
    report = AuditorValidityService().calculate(
        [decision("only-pass", True), decision("only-pass", False)], {"only-pass": True}
    )
    assert report.labelled_cases == 1
    assert report.accuracy == 100.0
    assert report.failure_precision is None
    assert report.failure_recall is None
    assert report.false_positive_rate == 0.0
    assert report.cohens_kappa is None
