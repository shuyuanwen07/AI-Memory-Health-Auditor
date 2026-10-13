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
    assert report['failure_detection_and_classification_recall']['percentage'] == 0
    assert report['category_confusion'] == [{'human_category': 'freshness', 'automatic_category': 'abstained', 'count': 1}]


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


def test_failure_detection_does_not_hide_abstentions_or_require_category_labels():
    report = reliability_summary([
        item(False, False), item(True, False), item(None, False), item(False, True), item(None, True),
    ])
    assert report['failure_recall']['percentage'] == 50
    assert report['failure_recall_including_abstentions']['percentage'] == 33.33
    assert report['failure_recall_including_abstentions']['denominator'] == 3
    assert report['reference_outcomes'] == {'human_failures': 3, 'human_passes': 2, 'uncertain_on_failure': 1, 'uncertain_on_pass': 1}
    assert report['reference_only_count'] == 5
    assert report['adjudicated_reference_count'] == 0


def test_repeating_one_history_cannot_invent_between_history_uncertainty():
    from app.services.auditor_quality import scenario_reliability
    report = scenario_reliability({'one': [item(True, True)] * 100})
    assert report['labelled_histories'] == 1
    assert report['resamples'] == 0
    assert report['metrics']['accuracy']['interval_95'] is None


def test_scenario_bootstrap_is_deterministic_and_keeps_abstentions_in_detection():
    from app.services.auditor_quality import scenario_reliability
    groups = {'first': [item(False, False), item(None, False)], 'second': [item(None, False)]}
    first = scenario_reliability(groups)
    assert first == scenario_reliability(dict(reversed(list(groups.items()))))
    assert first['labelled_histories'] == 2
    assert first['metrics']['failure_recall_including_abstentions']['interval_95'] == [0, 50]
    assert first['metrics']['failure_precision']['valid_resamples'] < 1000
