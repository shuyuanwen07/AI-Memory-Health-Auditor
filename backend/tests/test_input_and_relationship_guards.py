"""Boundary checks that keep accidental uploads and invalid ground truth safe."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app


def client_for(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'guards.db'}")
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


def test_declared_oversized_request_is_rejected_before_json_parsing(tmp_path):
    with client_for(tmp_path) as client:
        try:
            response = client.post(
                "/api/v1/conversations",
                content=b"{}",
                headers={"content-type": "application/json", "content-length": "5000001"},
            )
            assert response.status_code == 413
            assert "upload limit" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


def test_memory_evidence_and_update_lineage_reject_duplicates_and_cycles(tmp_path):
    with client_for(tmp_path) as client:
        try:
            conversation = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{
                    "message_id": "MSG001", "role": "user", "content": "The backend now uses PostgreSQL.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }).json()
            conversation_id = conversation["conversation_id"]
            first = client.post("/api/v1/memories", json={
                "conversation_id": conversation_id,
                "canonical_value": "The backend used MySQL.",
                "source_message_ids": ["MSG001"],
            })
            second = client.post("/api/v1/memories", json={
                "conversation_id": conversation_id,
                "canonical_value": "The backend now uses PostgreSQL.",
                "source_message_ids": ["MSG001"],
            })
            assert first.status_code == 201
            assert second.status_code == 201

            duplicate_evidence = client.patch(f"/api/v1/memories/{first.json()['memory_id']}", json={
                "source_message_ids": ["MSG001", "MSG001"],
            })
            assert duplicate_evidence.status_code == 422

            first_update = client.patch(f"/api/v1/memories/{first.json()['memory_id']}", json={
                "relationships": [{"type": "UPDATE", "target_memory_id": second.json()["memory_id"]}],
            })
            assert first_update.status_code == 200
            cycle = client.patch(f"/api/v1/memories/{second.json()['memory_id']}", json={
                "relationships": [{"type": "UPDATE", "target_memory_id": first.json()["memory_id"]}],
            })
            assert cycle.status_code == 422
            assert "cannot form a cycle" in cycle.json()["detail"]
        finally:
            app.dependency_overrides.clear()
