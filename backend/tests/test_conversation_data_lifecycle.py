"""Portable export and explicit local-erasure contracts for authorised data."""
from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app


def client_for(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    return TestClient(app)


def test_export_then_explicit_delete_removes_all_conversation_derived_records(tmp_path):
    with client_for(tmp_path) as client:
        try:
            conversation = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "timestamp": datetime.now(timezone.utc).isoformat(),
                              "content": "I prefer Python. The current project requires Java."}],
            }).json()
            conversation_id = conversation["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [memory["memory_id"] for memory in memories],
            }).status_code == 200
            experiment = client.post("/api/v1/experiments", json={
                "conversation_id": conversation_id, "label": "Erase test",
                "test_suite_configuration": {"test_budget": 2, "pipeline_provider": "rule_based", "pipeline_model": "rule-based-v2"},
            }).json()
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
                "target_configuration": "strong", "provider": "rule_based",
            }).json()
            assert client.post(f"/api/v1/audits/{audit['run_id']}/generate-tests").status_code == 200

            exported = client.get(f"/api/v1/conversations/{conversation_id}/export")
            assert exported.status_code == 200
            assert exported.headers["content-type"].startswith("application/json")
            data = json.loads(exported.text)
            assert data["conversation"]["conversation_id"] == conversation_id
            assert len(data["audits"]) == 1
            assert data["audits"][0]["tests"]
            assert "API keys" in data["notice"]

            rejected = client.request("DELETE", f"/api/v1/conversations/{conversation_id}", json={"confirmation": "wrong"})
            assert rejected.status_code == 422
            assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 200

            deleted = client.request("DELETE", f"/api/v1/conversations/{conversation_id}", json={"confirmation": conversation_id})
            assert deleted.status_code == 200
            assert deleted.json()["deleted_audit_runs"] == 1
            assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
            assert client.get("/api/v1/audits").json() == []
            assert client.get("/api/v1/experiments").json() == []
        finally:
            app.dependency_overrides.clear()
