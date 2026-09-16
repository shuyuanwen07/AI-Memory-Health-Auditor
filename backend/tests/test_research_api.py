"""Research endpoints validate transient payloads without a database dependency."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = json.loads((ROOT / "datasets" / "annotation" / "v1" / "seed_annotations.json").read_text())
LONGMEMEVAL = json.loads((ROOT / "datasets" / "benchmarks" / "longmemeval-compatible-v1" / "local_sample.json").read_text())


def test_annotation_and_longmemeval_research_endpoints_are_available():
    with TestClient(app) as client:
        validated = client.post("/api/v1/research/annotations/validate", json={"dataset": ANNOTATIONS})
        assert validated.status_code == 200
        assert validated.json()["fingerprint_sha256"]
        benchmark = client.post("/api/v1/research/benchmarks/longmemeval/validate", json={"payload": LONGMEMEVAL})
        assert benchmark.status_code == 200
        assert benchmark.json()["report"]["cases_imported"] == 2


def test_validity_endpoint_reports_extraction_test_and_evaluator_metrics():
    request = {
        "dataset": ANNOTATIONS,
        "predictions": {
            "dataset_id": "memory-health-seed", "dataset_version": "1.0.0",
            "memory_predictions": [{"conversation_id": "ANN-C001", "candidate_id": "candidate-1", "matched_gold_memory_id": "ANN-GM001"}],
            "relationship_predictions": [],
            "test_assessments": [{"conversation_id": "ANN-C001", "test_id": "ANN-T001", "grounded": True, "quality_label": "accept"}],
            "evaluator_predictions": [{"conversation_id": "ANN-C001", "response_id": "ANN-R001", "test_id": "ANN-T001", "passed": True}],
        },
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/research/validity/report", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["true_positives"] == 1
    assert body["test_validity"]["labelled_cases"] == 5
    assert body["evaluator"]["labelled_cases"] == 5


def test_evaluator_calibration_endpoint_is_request_scoped_and_reports_agreement():
    payload = {
        "dataset_id": "human-review-v1", "dataset_version": "1.0.0", "review_set_id": "pilot-a",
        "cases": [
            {"case_id": "R1", "dimension": "freshness", "evaluator_passed": False, "human_passed": False,
             "evaluator_failure_type": "freshness", "human_failure_type": "freshness"},
            {"case_id": "R2", "dimension": "accuracy", "evaluator_passed": False, "human_passed": True},
        ],
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/research/evaluator-calibration/analyse", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["retention"] == "request_scoped_not_persisted"
    assert body["overall_failure_detection"]["true_positives"] == 1
    assert body["overall_failure_detection"]["false_positives"] == 1
    assert body["fingerprint_sha256"]
