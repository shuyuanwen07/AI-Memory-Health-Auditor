"""Research validity metrics are reproducible from an annotation release."""
import json
from pathlib import Path

import pytest

from app.research.validity import ResearchValidityService
from app.schemas.annotation import AnnotationDataset
from app.schemas.research import ResearchPredictionSet, annotation_import_report


DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "annotation" / "v1" / "seed_annotations.json"


def dataset() -> AnnotationDataset:
    return AnnotationDataset.model_validate(json.loads(DATASET_PATH.read_text()))


def predictions() -> ResearchPredictionSet:
    return ResearchPredictionSet.model_validate({
        "dataset_id": "memory-health-seed",
        "dataset_version": "1.0.0",
        "memory_predictions": [
            {"conversation_id": "ANN-C001", "candidate_id": "P1", "matched_gold_memory_id": "ANN-GM001"},
            {"conversation_id": "ANN-C001", "candidate_id": "P2", "matched_gold_memory_id": "ANN-GM002"},
            {"conversation_id": "ANN-C001", "candidate_id": "P-extra"},
        ],
        "relationship_predictions": [
            {"conversation_id": "ANN-C001", "source_gold_memory_id": "ANN-GM002", "type": "UPDATE", "target_gold_memory_id": "ANN-GM001"},
            {"conversation_id": "ANN-C001", "source_gold_memory_id": "ANN-GM001", "type": "CONFLICT", "target_gold_memory_id": "ANN-GM002"},
        ],
        "test_assessments": [
            {"conversation_id": "ANN-C001", "test_id": "ANN-T001", "grounded": True, "quality_label": "accept"},
            {"conversation_id": "ANN-C001", "test_id": "ANN-T002", "grounded": True, "quality_label": "accept"},
            {"conversation_id": "ANN-C001", "test_id": "ANN-T003", "grounded": True, "quality_label": "accept"},
            {"conversation_id": "ANN-C001", "test_id": "ANN-T004", "grounded": True, "quality_label": "accept"},
            {"conversation_id": "ANN-C001", "test_id": "ANN-T005", "grounded": True, "quality_label": "accept"},
        ],
        "evaluator_predictions": [
            {"conversation_id": "ANN-C001", "response_id": "ANN-R001", "test_id": "ANN-T001", "passed": True},
            {"conversation_id": "ANN-C001", "response_id": "ANN-R002", "test_id": "ANN-T002", "passed": True},
            {"conversation_id": "ANN-C001", "response_id": "ANN-R003", "test_id": "ANN-T002", "passed": False},
            {"conversation_id": "ANN-C001", "response_id": "ANN-R004", "test_id": "ANN-T003", "passed": True},
            {"conversation_id": "ANN-C001", "response_id": "ANN-R005", "test_id": "ANN-T004", "passed": True},
        ],
    })


def test_validity_report_separates_each_research_unit():
    report = ResearchValidityService().calculate(dataset(), predictions())
    # 2 correct matched memory candidates, one unmatched candidate, 7 gold.
    assert (report.extraction.true_positives, report.extraction.false_positives, report.extraction.false_negatives) == (2, 1, 5)
    assert report.extraction.precision == 66.7
    # One correct and one invented relationship against four gold links.
    assert (report.relationship.true_positives, report.relationship.false_positives, report.relationship.false_negatives) == (1, 1, 3)
    assert report.test_validity.false_positives == 1
    # Failing response R004 is missed; R003 is correctly detected.
    assert (report.evaluator.true_positives, report.evaluator.false_negatives) == (1, 1)
    assert report.evaluator.recall == 50.0


def test_validity_refuses_untraceable_gold_reference():
    payload = predictions().model_dump()
    payload["memory_predictions"] = [
        {"conversation_id": "ANN-C001", "candidate_id": "P1", "matched_gold_memory_id": "NOPE"},
    ]
    invalid = ResearchPredictionSet.model_validate(payload)
    with pytest.raises(ValueError, match="Unknown gold memory"):
        ResearchValidityService().calculate(dataset(), invalid)


def test_annotation_import_fingerprint_is_stable_and_records_counts():
    first = annotation_import_report(dataset())
    second = annotation_import_report(dataset())
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert (first.conversations, first.gold_memories, first.gold_relationships, first.gold_tests, first.gold_evaluations) == (1, 7, 4, 5, 5)
    assert first.data_origin == dataset().data_origin


def test_missing_judgments_never_become_passes_or_rejections():
    empty = ResearchPredictionSet(dataset_id=dataset().dataset_id, dataset_version=dataset().dataset_version)
    report = ResearchValidityService().calculate(dataset(), empty)
    assert report.evaluator.labelled_cases == report.test_validity.labelled_cases == 0
    assert report.evaluator.accuracy is report.test_validity.accuracy is None
    assert report.evaluator.true_negatives == report.test_validity.true_negatives == 0
    assert report.evaluator_coverage.model_dump() == dict(expected=5, submitted=0, decided=0, missing=5, abstained=0)


@pytest.mark.parametrize('first,second,outcomes,accuracy', [
    ({'passed':False,'failure_type':'freshness'}, {'passed':False,'failure_type':'conflict_resolution'}, (2,0,0,0,0,0), 100),
    ({'passed':False,'failure_type':'accuracy'}, {'passed':False}, (0,1,1,0,0,0), 0),
    ({'passed':True}, {'passed':None}, (0,0,0,1,1,0), 0),
    ({'passed':False,'failure_type':'freshness'}, None, (1,0,0,0,0,1), None),
])
def test_failure_classification_is_distinct_from_binary_detection(first, second, outcomes, accuracy):
    payload = predictions().model_dump()
    originals = {item['response_id']:item for item in payload['evaluator_predictions']}
    payload['evaluator_predictions'] = [{**originals['ANN-R003'],**first}]
    if second is not None:
        payload['evaluator_predictions'].append({**originals['ANN-R004'],**second})
    report = ResearchValidityService().calculate(dataset(), ResearchPredictionSet.model_validate(payload))
    result = report.failure_classification
    assert result.reference_failures == 2
    assert (result.correct, result.wrong_category, result.unclassified, result.missed,
            result.uncertain, result.missing) == outcomes
    assert result.accuracy_all_reference_failures == accuracy
    if outcomes[1:3] == (1,1):
        assert report.evaluator.recall == 100
        assert result.accuracy_detected_failures == 0


@pytest.mark.parametrize('passed', [True, None])
def test_category_requires_an_explicit_failure_verdict(passed):
    from pydantic import ValidationError
    payload=predictions().model_dump()
    payload['evaluator_predictions'][0].update(passed=passed, failure_type='accuracy')
    with pytest.raises(ValidationError, match='failure verdict'):
        ResearchPredictionSet.model_validate(payload)


def test_empty_predictions_and_absent_reference_failures_are_unmeasured():
    release=dataset()
    empty=ResearchPredictionSet(dataset_id=release.dataset_id,dataset_version=release.dataset_version)
    result=ResearchValidityService().calculate(release,empty).failure_classification
    assert result.missing == result.reference_failures == 2
    assert result.accuracy_all_reference_failures is result.accuracy_detected_failures is None
    payload=release.model_dump()
    for row in payload['conversations'][0]['gold_evaluations']:
        row.update(passed=True,failure_type=None)
    result=ResearchValidityService().calculate(AnnotationDataset.model_validate(payload),predictions())
    assert result.evaluator.false_positives == 1
    assert result.failure_classification.reference_failures == 0
    assert result.failure_classification.accuracy_all_reference_failures is None


def test_research_endpoint_preserves_categories_and_versioned_metrics():
    from fastapi.testclient import TestClient
    from app.main import app
    machine=predictions().model_dump(mode='json')
    machine['evaluator_predictions'][2]['failure_type']='freshness'
    machine['evaluator_predictions'][3].update(passed=False,failure_type='accuracy')
    with TestClient(app) as client:
        response=client.post('/api/v1/research/validity/report',json={
            'dataset':dataset().model_dump(mode='json'),'predictions':machine})
    assert response.status_code == 200
    body=response.json()
    assert body['metric_version']=='research-count-metrics-v3'
    assert body['evaluator']['recall']==100
    assert body['failure_classification']['correct']==body['failure_classification']['wrong_category']==1
    assert body['failure_classification']['accuracy_all_reference_failures']==50


def test_uncertain_judgment_is_separate_from_missing_and_preserves_decided_failure():
    payload = predictions().model_dump()
    payload['evaluator_predictions'] = [payload['evaluator_predictions'][2], {**payload['evaluator_predictions'][0], 'passed': None}]
    report = ResearchValidityService().calculate(dataset(), ResearchPredictionSet.model_validate(payload))
    assert report.evaluator.labelled_cases == report.evaluator.true_positives == 1
    assert report.evaluator.accuracy == 100
    assert report.evaluator_coverage.model_dump() == dict(expected=5, submitted=2, decided=1, missing=3, abstained=1)
    assert report.evaluator.false_negatives == report.evaluator.true_negatives == 0


def test_response_identity_cannot_be_joined_to_another_valid_test():
    payload = predictions().model_dump()
    payload['evaluator_predictions'][0]['test_id'] = 'ANN-T002'
    with pytest.raises(ValueError, match='same gold evidence pair'):
        ResearchValidityService().calculate(dataset(), ResearchPredictionSet.model_validate(payload))


@pytest.mark.parametrize("predicted,actual,expected", [
    ({"wrong"}, {"missed"}, 0.0),
    (set(), {"missed"}, 0.0),
    ({"wrong"}, set(), 0.0),
    (set(), set(), None),
])
def test_f1_distinguishes_positive_errors_from_absent_positive_denominator(predicted, actual, expected):
    from app.research.validity import _binary_metrics
    metrics = _binary_metrics(predicted, actual, predicted | actual | {"negative"})
    assert metrics.f1 == expected


def test_f1_uses_raw_counts_instead_of_rounded_precision_and_recall():
    from app.research.validity import _binary_metrics
    actual = {str(i) for i in range(3)}
    predicted = {"0", "1"} | {f"extra-{i}" for i in range(41)}
    metrics = _binary_metrics(predicted, actual, actual | predicted)
    assert metrics.f1 == round(4 / 46 * 100, 1)


def collision_dataset():
    """Distinct conversation/local IDs that collide when joined with '::'."""
    from copy import deepcopy
    payload = dataset().model_dump(mode="json")
    original = payload["conversations"][0]
    conversations = []
    for conversation_id, local_id in [("a", "b::c"), ("a::b", "c")]:
        item = deepcopy(original)
        item["conversation_id"] = conversation_id
        memory = {**item["gold_memories"][0], "memory_id": local_id, "relationships": []}
        test = {**item["gold_tests"][0], "test_id": local_id, "supporting_memory_ids": [local_id]}
        evaluation = {**item["gold_evaluations"][0], "response_id": local_id, "test_id": local_id, "evidence_memory_ids": [local_id]}
        item.update(gold_memories=[memory], gold_tests=[test], gold_evaluations=[evaluation])
        conversations.append(item)
    payload["conversations"] = conversations
    return AnnotationDataset.model_validate(payload)


def test_delimited_identifiers_cannot_merge_memory_or_missing_assessment_counts():
    release = collision_dataset()
    predictions = ResearchPredictionSet(dataset_id=release.dataset_id, dataset_version=release.dataset_version,
        memory_predictions=[{"conversation_id": item.conversation_id, "candidate_id": "found", "matched_gold_memory_id": item.gold_memories[0].memory_id} for item in release.conversations],
        test_assessments=[{"conversation_id": "a", "test_id": "b::c", "grounded": True, "quality_label": "accept"}],
        evaluator_predictions=[{"conversation_id": "a", "response_id": "b::c", "test_id": "b::c", "passed": True}])
    result = ResearchValidityService().calculate(release, predictions)
    assert result.extraction.true_positives == result.extraction.labelled_cases == 2
    assert result.test_assessment_coverage.expected == result.evaluator_coverage.expected == 2
    assert result.test_assessment_coverage.missing == result.evaluator_coverage.missing == 1


def test_unmatched_candidate_name_cannot_impersonate_a_reference_memory():
    payload = collision_dataset().model_dump(mode="json")
    item = payload["conversations"][0]
    item["gold_memories"][0]["memory_id"] = "candidate:ghost"
    item["gold_tests"][0]["supporting_memory_ids"] = ["candidate:ghost"]
    item["gold_evaluations"][0]["evidence_memory_ids"] = ["candidate:ghost"]
    payload["conversations"] = [item]
    release = AnnotationDataset.model_validate(payload)
    predictions = ResearchPredictionSet(dataset_id=release.dataset_id, dataset_version=release.dataset_version,
        memory_predictions=[{"conversation_id": "a", "candidate_id": "ghost", "matched_gold_memory_id": None}])
    result = ResearchValidityService().calculate(release, predictions)
    assert (result.extraction.true_positives, result.extraction.false_positives, result.extraction.false_negatives) == (0, 1, 1)
    assert result.extraction.precision == result.extraction.recall == result.extraction.f1 == 0


def test_relationship_components_remain_distinct_with_delimiters():
    from app.research.validity import _relationship_key
    assert _relationship_key("a", "b::c", "UPDATE", "d") != _relationship_key("a::b", "c", "UPDATE", "d")


def test_metrics_bind_exact_canonical_inputs_even_when_release_name_is_reused():
    service = ResearchValidityService()
    release, machine = dataset(), predictions()
    first = service.calculate(release, machine)
    repeat = service.calculate(release, machine)
    assert first.metric_version == service.VERSION
    assert first.annotation_fingerprint_sha256 == repeat.annotation_fingerprint_sha256
    assert first.prediction_fingerprint_sha256 == repeat.prediction_fingerprint_sha256
    changed = release.model_copy(deep=True)
    changed.conversations[0].gold_memories[0].canonical_value += " Revised reference wording."
    new_labels = service.calculate(changed, machine)
    assert first.dataset_version == new_labels.dataset_version
    assert first.annotation_fingerprint_sha256 != new_labels.annotation_fingerprint_sha256
    assert first.prediction_fingerprint_sha256 == new_labels.prediction_fingerprint_sha256
    changed_machine = machine.model_copy(deep=True)
    changed_machine.evaluator_predictions[0].passed = not changed_machine.evaluator_predictions[0].passed
    new_predictions = service.calculate(release, changed_machine)
    assert first.annotation_fingerprint_sha256 == new_predictions.annotation_fingerprint_sha256
    assert first.prediction_fingerprint_sha256 != new_predictions.prediction_fingerprint_sha256

@pytest.mark.parametrize('second,expected,missing,uncertain', [
    ({'passed': None}, 50, 0, 1),
    (None, None, 1, 0),
    ({'passed': True}, 50, 0, 0),
    ({'passed': False}, 100, 0, 0),
])
def test_complete_reference_recall_does_not_hide_uncertain_or_missing_failures(second, expected, missing, uncertain):
    payload = predictions().model_dump()
    originals = {item['response_id']: item for item in payload['evaluator_predictions']}
    payload['evaluator_predictions'] = [{**originals['ANN-R003'], 'passed': False}]
    if second is not None:
        payload['evaluator_predictions'].append({**originals['ANN-R004'], **second})
    report = ResearchValidityService().calculate(dataset(), ResearchPredictionSet.model_validate(payload))
    result = report.failure_detection
    assert result.reference_failures == 2
    assert result.detected == (2 if second == {'passed': False} else 1)
    assert result.missing == missing
    assert result.uncertain == uncertain
    assert result.recall_all_reference_failures == expected
    if uncertain or missing:
        assert report.evaluator.recall == 100


def test_reference_recall_without_actual_failures_is_not_measured():
    payload = dataset().model_dump()
    for row in payload['conversations'][0]['gold_evaluations']:
        row.update(passed=True, failure_type=None)
    result = ResearchValidityService().calculate(AnnotationDataset.model_validate(payload), predictions()).failure_detection
    assert result.reference_failures == 0
    assert result.recall_all_reference_failures is None
