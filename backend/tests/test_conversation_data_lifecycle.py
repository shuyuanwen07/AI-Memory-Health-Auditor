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


def test_extraction_uses_durable_ids_when_two_conversations_share_local_labels(tmp_path):
    """M001 from one extractor invocation must never collide with another."""
    with client_for(tmp_path) as client:
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            payload = {
                "authorised": True,
                "messages": [{
                    "message_id": "MSG001", "role": "user", "timestamp": timestamp,
                    "content": "I used MySQL before. The backend now uses PostgreSQL.",
                }],
            }
            first_conversation = client.post("/api/v1/conversations", json=payload).json()["conversation_id"]
            second_conversation = client.post("/api/v1/conversations", json=payload).json()["conversation_id"]
            first = client.post(f"/api/v1/conversations/{first_conversation}/extract")
            second = client.post(f"/api/v1/conversations/{second_conversation}/extract")

            assert first.status_code == 200, first.text
            assert second.status_code == 200, second.text
            first_ids = {memory["memory_id"] for memory in first.json()}
            second_ids = {memory["memory_id"] for memory in second.json()}
            assert first_ids.isdisjoint(second_ids)
            assert all(relationship["target_memory_id"] in first_ids for memory in first.json() for relationship in memory["relationships"])
            assert all(relationship["target_memory_id"] in second_ids for memory in second.json() for relationship in memory["relationships"])
        finally:
            app.dependency_overrides.clear()
