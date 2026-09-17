"""Contracts for the versioned, offline research annotation artefact."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.annotation import AnnotationDataset


DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "annotation" / "v1" / "seed_annotations.json"
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "datasets" / "annotation" / "v1" / "annotation_template.json"


def _synthetic_calibration_fixture() -> dict:
    """Build the small synthetic release used by CI without local artefacts.

    The full Pilot v2 release remains a local research artefact and is
    intentionally ignored by git.  This fixture keeps the contract test
    reproducible in a clean checkout while matching its five-scenario,
    twenty-test shape.
    """
    dimensions = [
        ("accuracy", "direct"),
        ("freshness", "contextual"),
        ("conflict_resolution", "indirect"),
        ("appropriate_use", "paraphrased"),
    ]
    conversations = []
    for scenario_number in range(1, 6):
        suffix = f"S{scenario_number}"
        message_id = f"{suffix}-M1"
        memory_id = f"{suffix}-G1"
        value = f"Synthetic calibration fact {scenario_number}."
        tests = [
            {
                "test_id": f"{suffix}-T{test_number}",
                "dimension": dimension,
                "test_type": test_type,
                "prompt": f"What is calibration fact {scenario_number} ({dimension})?",
                "expected_behavior": f"State {value}",
                "supporting_memory_ids": [memory_id],
                "grounded": True,
                "quality_label": "accept",
                "quality_note": "Inline synthetic CI fixture.",
            }
            for test_number, (dimension, test_type) in enumerate(dimensions, start=1)
        ]
        evaluations = [
            {
                "response_id": f"{suffix}-R{test_number}",
                "test_id": test["test_id"],
                "response_text": value if scenario_number != 1 or test_number != 1 else "An incorrect answer.",
                "passed": not (scenario_number == 1 and test_number == 1),
                "failure_type": None if scenario_number != 1 or test_number != 1 else "accuracy",
                "reason": "Matches the fixture." if scenario_number != 1 or test_number != 1 else "Deliberate calibration failure.",
                "evidence_memory_ids": [memory_id],
            }
            for test_number, test in enumerate(tests, start=1)
        ]
        conversations.append(
            {
                "conversation_id": f"SYN-C{scenario_number:03d}",
                "messages": [
                    {
                        "message_id": message_id,
                        "role": "user",
                        "content": value,
                        "timestamp": "2026-01-01T09:00:00Z",
                    }
                ],
                "gold_memories": [
                    {
                        "memory_id": memory_id,
                        "canonical_value": value,
                        "source_message_ids": [message_id],
                    }
                ],
                "gold_tests": tests,
                "gold_evaluations": evaluations,
            }
        )
    return {
        "dataset_id": "ci-inline-synthetic-calibration",
        "dataset_version": "2.0.0",
        "created_at": "2026-01-01T00:00:00Z",
        "authorised_for_research": True,
        "data_origin": "Five synthetic calibration fixtures with no participant data.",
        "deidentification_note": "Inline synthetic test data only.",
        "conversations": conversations,
    }


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
    dataset = AnnotationDataset.model_validate(_synthetic_calibration_fixture())

    assert len(dataset.conversations) == 5
    assert sum(len(item.gold_tests) for item in dataset.conversations) == 20
    assert {test.dimension.value for item in dataset.conversations for test in item.gold_tests} == {
        "accuracy", "freshness", "conflict_resolution", "appropriate_use",
    }
    assert any(not evaluation.passed for item in dataset.conversations for evaluation in item.gold_evaluations)
