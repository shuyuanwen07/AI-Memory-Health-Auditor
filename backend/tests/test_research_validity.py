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
