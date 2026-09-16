"""Focused contracts for the ephemeral double-annotation pilot service."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.research.pilot import PilotAnnotationService
from app.schemas.pilot import PilotAnalysisRequest, PilotAnnotationPackage


def _package() -> dict:
    return {
        "pilot_id": "pilot-deidentified-v1",
        "dataset_id": "synthetic-pilot",
        "dataset_version": "1.0.0",
        "created_at": datetime(2026, 9, 16, tzinfo=timezone.utc).isoformat(),
        "authorised_for_research": True,
        "data_origin": "Synthetic, de-identified calibration scenarios.",
        "deidentification_note": "No participant names, accounts, addresses, or source text are included.",
        "minimum_paired_items_per_task": 1,
        "minimum_kappa": 0.6,
        "items": [
            {"item_id": "PI-MEM-01", "task": "memory_inclusion"},
            {"item_id": "PI-TEST-01", "task": "test_validity"},
            {"item_id": "PI-EVAL-01", "task": "evaluator_verdict"},
        ],
        "annotators": [
            {
                "annotator_id": "annotator-a",
                "labels": [
                    {"item_id": "PI-MEM-01", "task": "memory_inclusion", "label": "include"},
                    {"item_id": "PI-TEST-01", "task": "test_validity", "label": "accept"},
                    {"item_id": "PI-EVAL-01", "task": "evaluator_verdict", "label": "fail"},
                ],
            },
            {
                "annotator_id": "annotator-b",
                "labels": [
                    {"item_id": "PI-MEM-01", "task": "memory_inclusion", "label": "include"},
                    {"item_id": "PI-TEST-01", "task": "test_validity", "label": "reject"},
                    {"item_id": "PI-EVAL-01", "task": "evaluator_verdict", "label": "fail"},
                ],
            },
        ],
        "adjudications": [
            {"item_id": "PI-MEM-01", "task": "memory_inclusion", "label": "include", "basis": "adjudicated", "decision_note": "Both independent labels agree."},
            {"item_id": "PI-TEST-01", "task": "test_validity", "label": "accept", "basis": "adjudicated", "decision_note": "Resolved after checking the written test criteria."},
            {"item_id": "PI-EVAL-01", "task": "evaluator_verdict", "label": "fail", "basis": "external_reference", "decision_note": "Checked against the approved response reference."},
        ],
    }


def test_pilot_report_keeps_disagreement_and_adjudication_separate():
    package = PilotAnnotationPackage.model_validate(_package())
    report = PilotAnnotationService().analyse(PilotAnalysisRequest(package=package))

    validity = next(item for item in report.by_task if item.task.value == "test_validity")
    assert validity.disagreement_count == 1
    assert validity.disagreements_adjudicated == 1
    assert validity.unresolved_disagreements == 0
    assert report.overall.paired_items == 3
    assert report.retention == "request_scoped_not_persisted"
    # The small test-validity sample is a kappa edge case (all disagreement),
    # so the explicit readiness criteria correctly stop a formal run.
    assert not report.ready_for_formal_evaluation
    assert any("test_validity: Cohen's kappa" in item for item in report.blocking_reasons)


def test_pilot_contract_rejects_unknown_units_and_duplicate_annotators():
    payload = _package()
    payload["annotators"][1]["annotator_id"] = "annotator-a"
    with pytest.raises(ValidationError, match="two distinct"):
        PilotAnnotationPackage.model_validate(payload)

    payload = _package()
    payload["annotators"][0]["labels"][0]["item_id"] = "not-declared"
    with pytest.raises(ValidationError, match="declared pilot items"):
        PilotAnnotationPackage.model_validate(payload)


def test_pilot_endpoint_returns_ephemeral_readiness_report():
    with TestClient(app) as client:
        response = client.post("/api/v1/research/pilot/analyse", json={"package": _package()})
    assert response.status_code == 200
    body = response.json()
    assert body["pilot_id"] == "pilot-deidentified-v1"
    assert body["overall"]["disagreement_count"] == 1
    assert body["fingerprint_sha256"]
