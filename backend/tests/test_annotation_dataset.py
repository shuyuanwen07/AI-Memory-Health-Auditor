"""Contracts for the versioned, offline research annotation artefact."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.annotation import AnnotationDataset


DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "annotation" / "v1" / "seed_annotations.json"
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "datasets" / "annotation" / "v1" / "annotation_template.json"


def test_seed_annotation_dataset_is_valid_and_has_all_dimensions():
    dataset = AnnotationDataset.model_validate(json.loads(DATASET_PATH.read_text()))
    dimensions = {test.dimension.value for conversation in dataset.conversations for test in conversation.gold_tests}
    assert dimensions == {"accuracy", "freshness", "conflict_resolution", "appropriate_use"}
    assert any(not evaluation.passed for conversation in dataset.conversations for evaluation in conversation.gold_evaluations)


def test_annotation_rejects_evaluation_with_inconsistent_failure_label():
    payload = json.loads(DATASET_PATH.read_text())
    payload["conversations"][0]["gold_evaluations"][0]["failure_type"] = "accuracy"
    with pytest.raises(ValidationError, match="passing evaluation"):
        AnnotationDataset.model_validate(payload)


def test_annotation_template_keeps_the_versioned_contract():
    template = AnnotationDataset.model_validate(json.loads(TEMPLATE_PATH.read_text()))
    assert template.dataset_version == "1.0.0"


def test_synthetic_pilot_v2_is_a_valid_balanced_calibration_release():
    path = Path(__file__).resolve().parents[2] / "datasets" / "annotation" / "synthetic-pilot-v2" / "synthetic_pilot_annotations.json"
    dataset = AnnotationDataset.model_validate(json.loads(path.read_text()))

    assert len(dataset.conversations) == 5
    assert sum(len(item.gold_tests) for item in dataset.conversations) == 20
    assert {test.dimension.value for item in dataset.conversations for test in item.gold_tests} == {
        "accuracy", "freshness", "conflict_resolution", "appropriate_use",
    }
    assert any(not evaluation.passed for item in dataset.conversations for evaluation in item.gold_evaluations)
