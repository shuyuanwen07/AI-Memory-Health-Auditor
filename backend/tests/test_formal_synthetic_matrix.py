"""The formal matrix persists only approved synthetic scenarios and frozen suites."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, ExperimentModel, TestCaseModel


def _build_dataset() -> dict:
    """Return a tiny, deterministic fixture that is safe to run in CI.

    The full pilot release is intentionally local and ignored by git.  This
    test exercises the API contract with synthetic records instead of making
    CI depend on that private research artefact being present in a checkout.
    Four dimensions per scenario preserve the formal matrix's paired-suite
    assertions while keeping the fixture small and readable.
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
        value = f"Synthetic fact {scenario_number}."
        tests = [
            {
                "test_id": f"{suffix}-T{test_number}",
                "dimension": dimension,
                "test_type": test_type,
                "prompt": f"What is synthetic fact {scenario_number} ({dimension})?",
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
                "response_text": value,
                "passed": True,
                "failure_type": None,
                "reason": "Matches the inline synthetic fixture.",
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
        "dataset_id": "ci-inline-synthetic",
        "dataset_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00Z",
        "authorised_for_research": True,
        "data_origin": "Five synthetic CI fixtures with no participant data.",
        "deidentification_note": "Inline synthetic test data only.",
        "conversations": conversations,
    }


def _build_pilot() -> dict:
    """Return complete, matching labels for the formal readiness gate."""
    task_labels = [
        ("memory_inclusion", "include"),
        ("relationship_type", "UPDATE"),
        ("test_validity", "accept"),
        ("evaluator_verdict", "pass"),
        ("failure_dimension", "freshness"),
    ]
    items = [
        {"item_id": f"{task.upper()}-{number:02d}", "task": task}
        for task, _ in task_labels
        for number in range(1, 6)
    ]
    labels_by_task = dict(task_labels)

    def labels():
        return [
            {"item_id": item["item_id"], "task": item["task"], "label": labels_by_task[item["task"]]}
            for item in items
        ]

    adjudications = [
        {
            "item_id": item["item_id"],
            "task": item["task"],
            "label": labels_by_task[item["task"]],
            "basis": "external_reference",
            "decision_note": "Inline synthetic CI reference label.",
        }
        for item in items
    ]
    return {
        "pilot_id": "ci-inline-pilot",
        "dataset_id": "ci-inline-synthetic",
        "dataset_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00Z",
        "authorised_for_research": True,
        "data_origin": "Synthetic CI fixture with no participant data.",
        "deidentification_note": "Inline synthetic labels only.",
        "annotation_mode": "human_double_annotation",
        "minimum_paired_items_per_task": 5,
        "minimum_kappa": 0.6,
        "items": items,
        "annotators": [
            {"annotator_id": "yc", "labels": labels()},
            {"annotator_id": "sd", "labels": labels()},
        ],
        "adjudications": adjudications,
    }


DATASET = _build_dataset()
PILOT = _build_pilot()


def test_ready_human_pilot_materialises_paired_frozen_synthetic_runs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matrix.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    payload = {
        "dataset": DATASET, "pilot": PILOT, "synthetic_data_confirmation": True,
        "conditions": [
            {"label": "Weak", "memory_strategy": "weak_first_hit", "provider": "rule_based", "model": "rule-based-target-ai"},
            {"label": "Scope", "memory_strategy": "scope_aware", "provider": "rule_based", "model": "rule-based-target-ai"},
        ],
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/research/formal/synthetic-matrix", json=payload)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["scenario_count"] == 5
            assert body["total_audit_runs"] == 10
            assert body["total_target_calls"] == 40
            duplicate = client.post("/api/v1/research/formal/synthetic-matrix", json=payload)
            assert duplicate.status_code == 409
    finally:
        app.dependency_overrides.clear()

    db = factory()
    try:
        assert db.query(ExperimentModel).count() == 5
        assert db.query(AuditRunModel).count() == 10
        tests = db.query(TestCaseModel).all()
        assert len(tests) == 40
        assert {test.quality_status for test in tests} == {"accepted"}
        assert {test.grounding_status for test in tests} == {"grounded"}
        canonical = [test for test in tests if test.suite_test_id is None]
        peers = [test for test in tests if test.suite_test_id is not None]
        assert len(canonical) == len(peers) == 20
        assert all(test.suite_test_id in {source.id for source in canonical} for test in peers)
    finally:
        db.close()


def test_matrix_rejects_non_synthetic_dataset_before_persistence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matrix-reject.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    non_synthetic = {**DATASET, "conversations": list(DATASET["conversations"])}
    non_synthetic["data_origin"] = "Authorised research conversations"
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/research/formal/synthetic-matrix", json={
                "dataset": non_synthetic, "pilot": PILOT, "synthetic_data_confirmation": True,
                "conditions": [
                    {"label": "Weak", "memory_strategy": "weak_first_hit", "provider": "rule_based", "model": "rule-based-target-ai"},
                    {"label": "Scope", "memory_strategy": "scope_aware", "provider": "rule_based", "model": "rule-based-target-ai"},
                ],
            })
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
    db = factory()
    try:
        assert db.query(ExperimentModel).count() == 0
    finally:
        db.close()
