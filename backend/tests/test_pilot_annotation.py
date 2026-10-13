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
        "dataset_fingerprint_sha256": "a" * 64,
        "created_at": datetime(2026, 9, 16, tzinfo=timezone.utc).isoformat(),
        "authorised_for_research": True,
        "annotation_mode": "human_double_annotation",
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


@pytest.mark.parametrize("identifier", [" annotator-a ", "ANNOTATOR-A", "\tAnnotator-A\n"])
def test_pilot_rejects_same_reviewer_with_spacing_or_case(identifier):
    payload = _package()
    payload["annotators"][1]["annotator_id"] = identifier
    with pytest.raises(ValidationError, match="two distinct"):
        PilotAnnotationPackage.model_validate(payload)


def test_pilot_rejects_whitespace_reviewer_and_preserves_valid_original_ids():
    payload = _package()
    payload["annotators"][1]["annotator_id"] = " \t "
    with pytest.raises(ValidationError, match="non-whitespace"):
        PilotAnnotationPackage.model_validate(payload)
    payload["annotators"][1]["annotator_id"] = " Reviewer B "
    package = PilotAnnotationPackage.model_validate(payload)
    assert package.annotators[1].annotator_id == " Reviewer B "


def test_missing_provenance_cannot_default_to_independent_human_labels():
    payload = _package()
    del payload['annotation_mode']
    with pytest.raises(ValidationError, match='annotation_mode'):
        PilotAnnotationPackage.model_validate(payload)
    with TestClient(app) as client:
        response = client.post('/api/v1/research/pilot/analyse', json={'package': payload})
    assert response.status_code == 422
    assert any(error['loc'][-1] == 'annotation_mode' for error in response.json()['detail'])


def test_ai_assisted_synthetic_dry_run_can_never_open_the_formal_gate():
    payload = _package()
    payload["annotation_mode"] = "ai_assisted_synthetic_dry_run"
    for annotator in payload["annotators"]:
        annotator["labels"] = [
            {"item_id": item["item_id"], "task": item["task"], "label": "accept" if item["task"] == "test_validity" else "include" if item["task"] == "memory_inclusion" else "fail" if item["task"] == "evaluator_verdict" else "none"}
            for item in payload["items"]
        ]
    payload["adjudications"] = [
        {"item_id": item["item_id"], "task": item["task"], "label": "accept" if item["task"] == "test_validity" else "include" if item["task"] == "memory_inclusion" else "fail" if item["task"] == "evaluator_verdict" else "none", "basis": "external_reference", "decision_note": "Synthetic reference."}
        for item in payload["items"]
    ]

    report = PilotAnnotationService().analyse(PilotAnalysisRequest.model_validate({"package": payload}))

    assert not report.ready_for_formal_evaluation
    assert report.annotation_mode.value == "ai_assisted_synthetic_dry_run"
    assert any("not independent human" in blocker for blocker in report.blocking_reasons)


def test_missing_dataset_fingerprint_blocks_an_otherwise_complete_pilot():
    from copy import deepcopy
    from test_formal_synthetic_matrix import PILOT

    payload = deepcopy(PILOT)
    payload.pop("dataset_fingerprint_sha256")
    report = PilotAnnotationService().analyse(PilotAnalysisRequest.model_validate({"package": payload}))

    assert not report.ready_for_formal_evaluation
    assert any("exact validated dataset fingerprint" in blocker for blocker in report.blocking_reasons)

@pytest.mark.parametrize('missing_task', ['memory_inclusion', 'relationship_type', 'test_validity', 'evaluator_verdict', 'failure_dimension'])
def test_omitting_entire_review_task_cannot_open_formal_gate(monkeypatch, missing_task):
    from copy import deepcopy
    from test_formal_synthetic_matrix import PILOT, DATASET, CRITERIA
    from app.database.session import get_db
    from app.services.formal_matrix import FormalSyntheticMatrixService
    payload = deepcopy(PILOT)
    payload['items'] = [x for x in payload['items'] if x['task'] != missing_task]
    for reviewer in payload['annotators']:
        reviewer['labels'] = [x for x in reviewer['labels'] if x['task'] != missing_task]
    payload['adjudications'] = [x for x in payload['adjudications'] if x['task'] != missing_task]
    report = PilotAnnotationService().analyse(PilotAnalysisRequest.model_validate({'package':payload}))
    assert not report.ready_for_formal_evaluation
    assert any(missing_task in reason for reason in report.blocking_reasons)
    monkeypatch.setattr(FormalSyntheticMatrixService, 'create', lambda *a, **kwargs: pytest.fail('Incomplete pilot must not materialise any audit rows'))
    development=deepcopy(DATASET)
    for history in development['conversations']:
        for message in history['messages']:
            message['content'] += ' Distinct development-only content.'
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/research/formal/synthetic-matrix', json={
                'dataset':DATASET, 'pilot':payload, 'development_dataset':development,
                'study_design':{'sampling_rule':'Select the entire frozen inventory before viewing target responses; exclude none.','primary_outcome':'freshness'},
                'repetitions':3, 'synthetic_data_confirmation':True, 'success_criteria':CRITERIA,
                'conditions':[{'label':'Weak','memory_strategy':'weak_first_hit','provider':'rule_based','model':'rule-based-target-ai'},
                              {'label':'Strong','memory_strategy':'strong_rule_based','provider':'rule_based','model':'rule-based-target-ai'}]})
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('cells,threshold,ready', [
    ((10, 1, 6, 20), 0.6, False),
    ((10, 1, 6, 20), 0.5995, True),
    ((4, 1, 1, 4), 0.6, True),
])
def test_pilot_readiness_compares_unrounded_kappa(cells, threshold, ready):
    # Fully labelled five-task fixtures isolate the numerical gate from
    # missing labels, provenance and adjudication blockers. These are test
    # fixtures, not evidence of independent human work.
    from app.schemas.pilot import PilotTask, _TASK_LABELS
    payload = _package()
    payload['items'] = []
    payload['adjudications'] = []
    payload['minimum_kappa'] = threshold
    for annotator in payload['annotators']:
        annotator['labels'] = []
    for task in PilotTask:
        left, right = sorted(_TASK_LABELS[task])[:2]
        pairs = [(left, left), (left, right), (right, left), (right, right)]
        number = 0
        for (label_a, label_b), count in zip(pairs, cells, strict=True):
            for _ in range(count):
                item = {'item_id': f'{task.value}-{number}', 'task': task.value}
                payload['items'].append(item)
                for annotator, label in zip(payload['annotators'], (label_a, label_b), strict=True):
                    annotator['labels'].append({**item, 'label': label})
                payload['adjudications'].append({**item, 'label': label_a,
                    'basis': 'external_reference', 'decision_note': 'Numerical regression fixture.'})
                number += 1
    report = PilotAnnotationService().analyse(PilotAnalysisRequest.model_validate({'package': payload}))
    assert report.ready_for_formal_evaluation is ready
    if cells == (10, 1, 6, 20):
        assert all(item.cohens_kappa == pytest.approx(0.5996908809891808) for item in report.by_task)
    else:
        assert all(item.cohens_kappa == 0.6 for item in report.by_task)
    if not ready:
        assert len(report.blocking_reasons) == 5
        assert all('0.599691' in reason and '0.6' in reason for reason in report.blocking_reasons)
