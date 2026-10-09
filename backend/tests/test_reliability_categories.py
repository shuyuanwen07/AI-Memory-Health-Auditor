"""Different human judgements must not collapse into a binary accuracy claim."""
from types import SimpleNamespace as Row
from app.schemas import Dimension
from app.services.auditor_quality import reliability_summary


def item(automatic, human, automatic_type=None, human_type=None):
    return Row(automated=Row(passed=automatic, failure_type=automatic_type),
               human_review=Row(human_passed=human, human_failure_type=human_type),
               human_reviews=[], test=Row(dimension=Dimension.ACCURACY))


def test_wrong_failure_category_is_binary_agreement_only():
    report = reliability_summary([
        item(False, False, Dimension.FRESHNESS, Dimension.ACCURACY),
        item(False, False, Dimension.ACCURACY, Dimension.ACCURACY),
        item(True, False, None, Dimension.ACCURACY),
    ])
    assert report['accuracy']['percentage'] == 66.67
    assert report['failure_classification_accuracy']['percentage'] == 50
    assert report['failure_detection_and_classification_recall']['percentage'] == 33.33
    assert {'human_category': 'accuracy', 'automatic_category': 'no_failure_detected', 'count': 1} in report['category_confusion']


def test_human_labelled_uncertain_answers_count_as_coverage_not_accuracy():
    report = reliability_summary([item(None, False, None, Dimension.FRESHNESS)])
    assert report['resolved_reference_count'] == 1
    assert report['decided_reference_count'] == 0
    assert report['review_coverage']['percentage'] == 100
    assert report['labelled_abstention_rate']['percentage'] == 100
    assert report['accuracy']['percentage'] is None
    assert report['evidence_status'] == 'human_references_available'


def test_unknown_human_category_is_not_fabricated():
    report = reliability_summary([item(False, False, Dimension.FRESHNESS)])
    assert report['accuracy']['percentage'] == 100
    assert report['failure_classification_accuracy']['percentage'] is None
    assert report['category_confusion'] == []


def test_formal_score_uses_four_dimensional_macro_average_including_zero():
    from app.schemas import AuditResult, DimensionScores
    result = AuditResult(run_id='fixture', overall_score=75, tests_passed=3, tests_total=5,
        dimensions=[DimensionScores(dimension=dimension,percentage=score,passed=0,total=1)
                    for dimension,score in zip(Dimension,[0,50,100,50])],failures=[])
    assert result.formal_overall_score == 50
    result.dimensions[0].percentage = None
    assert result.formal_overall_score is None
