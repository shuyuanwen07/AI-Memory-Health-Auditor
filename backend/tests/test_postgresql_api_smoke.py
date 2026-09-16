"""A migrated PostgreSQL path kept separate from fast SQLite unit tests."""

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.mark.postgres
def test_postgresql_migrated_api_path():
    if not os.getenv("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("PostgreSQL integration is enabled only by the CI database job.")

    from app.main import app

    with TestClient(app) as client:
        created = client.post("/api/v1/conversations", json={
            "authorised": True,
            "messages": [
                {"message_id": "export-message-1", "role": "user", "content": "I used MySQL before.", "timestamp": datetime.now(timezone.utc).isoformat()},
                {"message_id": "export-message-2", "role": "user", "content": "The backend now uses PostgreSQL.", "timestamp": datetime.now(timezone.utc).isoformat()},
            ],
        })
        assert created.status_code == 201, created.text
        conversation_id = created.json()["conversation_id"]
        try:
            extracted = client.post(f"/api/v1/conversations/{conversation_id}/extract")
            assert extracted.status_code == 200, extracted.text
            confirmed = client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [memory["memory_id"] for memory in extracted.json()],
            })
            assert confirmed.status_code == 200, confirmed.text
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "target_configuration": "strong", "provider": "rule_based", "test_budget": 4,
            })
            assert audit.status_code == 201, audit.text
            run_id = audit.json()["run_id"]
            assert client.post(f"/api/v1/audits/{run_id}/generate-tests").status_code == 200
            assert client.post(f"/api/v1/audits/{run_id}/execute").status_code == 200
            assert client.post(f"/api/v1/audits/{run_id}/evaluate").status_code == 200
            assert client.get(f"/api/v1/audits/{run_id}/results").status_code == 200
        finally:
            deleted = client.request("DELETE", f"/api/v1/conversations/{conversation_id}", json={"confirmation": conversation_id})
            assert deleted.status_code == 200, deleted.text
