"""The formal matrix persists only approved synthetic scenarios and frozen suites."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, ExperimentModel, TestCaseModel


ROOT = Path(__file__).resolve().parents[2]
DATASET = json.loads((ROOT / "datasets/annotation/synthetic-pilot-v2/synthetic_pilot_annotations.json").read_text())
PILOT = json.loads((ROOT / "datasets/annotation/synthetic-pilot-v2/double-annotation/human_double_annotation.json").read_text())


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

    non_synthetic = json.loads(json.dumps(DATASET))
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
