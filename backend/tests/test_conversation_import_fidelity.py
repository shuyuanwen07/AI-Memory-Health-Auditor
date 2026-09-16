from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app


def test_structured_import_preserves_source_ids_timestamps_and_reused_export_ids(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fidelity.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    stamp = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc).isoformat()
    payload = {"authorised": True, "messages": [
        {"message_id": "MSG001", "role": "user", "content": "I used MySQL before.", "timestamp": stamp},
        {"message_id": "MSG002", "role": "user", "content": "I now use PostgreSQL.", "timestamp": "2025-01-03T03:04:00Z"},
    ]}
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/conversations", json=payload)
            assert first.status_code == 201
            assert [message["message_id"] for message in first.json()["messages"]] == ["MSG001", "MSG002"]
            assert first.json()["messages"][0]["timestamp"].startswith("2025-01-02T03:04:00")

            # Typical provider exports restart numbering in every conversation.
            second = client.post("/api/v1/conversations", json=payload)
            assert second.status_code == 201
            assert [message["message_id"] for message in second.json()["messages"]] == ["MSG001", "MSG002"]
    finally:
        app.dependency_overrides.clear()


def test_pasted_text_creates_one_ordered_record_per_non_empty_line(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pasted.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/conversations", json={
                "authorised": True,
                "pasted_text": "[User] I prefer Python.\n\n[Assistant] Understood.\n[User] This assignment requires Java.",
            })
            assert response.status_code == 201
            messages = response.json()["messages"]
            assert [(item["message_id"], item["role"], item["content"]) for item in messages] == [
                ("MSG001", "User", "I prefer Python."),
                ("MSG002", "Assistant", "Understood."),
                ("MSG003", "User", "This assignment requires Java."),
            ]
    finally:
        app.dependency_overrides.clear()
