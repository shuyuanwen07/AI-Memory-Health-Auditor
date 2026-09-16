"""Public contracts for pre-execution suite review and post-audit target traces."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app


def _client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'trace-review.db'}")
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


def _conversation_and_experiment(client):
    timestamp = datetime.now(timezone.utc).isoformat()
    conversation_id = client.post("/api/v1/conversations", json={
        "authorised": True,
        "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp,
                      "content": "I used MySQL before. The backend now uses PostgreSQL. I prefer Python. This assignment requires Java."}],
    }).json()["conversation_id"]
    memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
    client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
        "confirmed_memory_ids": [item["memory_id"] for item in memories],
    })
    experiment = client.post("/api/v1/experiments", json={
        "conversation_id": conversation_id, "label": "Review fairness",
        "test_suite_configuration": {"test_budget": 4, "pipeline_provider": "rule_based", "pipeline_model": "rule-based-v2"},
    }).json()
    runs = [client.post("/api/v1/audits", json={
        "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
        "target_configuration": target, "provider": "rule_based", "memory_strategy": strategy,
    }).json() for target, strategy in (("weak", "weak_first_hit"), ("strong", "strong_rule_based"))]
    return runs


def test_review_decision_and_regeneration_are_synchronised_to_experiment_peers(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, peer = _conversation_and_experiment(client)
            generated = client.post(f"/api/v1/audits/{source['run_id']}/generate-tests").json()
            review = client.get(f"/api/v1/audits/{peer['run_id']}/test-review")
            assert review.status_code == 200
            assert review.json()["canonical_run_id"] == source["run_id"]
            source_test_id = generated[0]["test_id"]

            rejected = client.patch(f"/api/v1/audits/{peer['run_id']}/tests/{source_test_id}/review", json={
                "quality_status": "rejected", "note": "Needs a clearer scenario.",
            })
            assert rejected.status_code == 200
            assert {item["quality_status"] for item in client.get(f"/api/v1/audits/{peer['run_id']}/tests").json() if item["dimension"] == generated[0]["dimension"]} >= {"rejected"}
            assert client.post(f"/api/v1/audits/{peer['run_id']}/execute").status_code == 409

            regenerated = client.post(f"/api/v1/audits/{peer['run_id']}/tests/{source_test_id}/regenerate")
            assert regenerated.status_code == 200
            assert regenerated.json()["quality_status"] == "pending"
            accepted = client.patch(f"/api/v1/audits/{source['run_id']}/tests/{source_test_id}/review", json={"quality_status": "accepted"})
            assert accepted.status_code == 200
            assert client.post(f"/api/v1/audits/{peer['run_id']}/execute").status_code == 200
        finally:
            app.dependency_overrides.clear()


def test_target_memory_trace_is_post_completion_only_and_hides_evaluator_material(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, _ = _conversation_and_experiment(client)
            run_id = source["run_id"]
            client.post(f"/api/v1/audits/{run_id}/generate-tests")
            client.post(f"/api/v1/audits/{run_id}/execute")
            assert client.get(f"/api/v1/audits/{run_id}/target-memory-trace").status_code == 409
            assert client.post(f"/api/v1/audits/{run_id}/evaluate").status_code == 200
            trace = client.get(f"/api/v1/audits/{run_id}/target-memory-trace")
            assert trace.status_code == 200
            payload = trace.json()
            assert payload["records"] and payload["retrievals"]
            assert "expected_behavior" not in str(payload)
            assert "target_memory_context" not in str(payload)
            assert any(event["details"].get("writer_version") for event in payload["events"])
        finally:
            app.dependency_overrides.clear()


def test_rule_based_workflow_reviews_then_executes_and_exposes_trace(monkeypatch, tmp_path):
    """One offline smoke path mirrors the user workflow without any cloud provider."""
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, _ = _conversation_and_experiment(client)
            run_id = source["run_id"]
            generated = client.post(f"/api/v1/audits/{run_id}/generate-tests")
            assert generated.status_code == 200
            first_test_id = generated.json()[0]["test_id"]

            # A rejected item blocks execution. Regeneration creates a pending
            # replacement which must be accepted before the target can run.
            assert client.patch(f"/api/v1/audits/{run_id}/tests/{first_test_id}/review", json={
                "quality_status": "rejected", "note": "Check wording before execution.",
            }).status_code == 200
            assert client.post(f"/api/v1/audits/{run_id}/execute").status_code == 409
            replacement = client.post(f"/api/v1/audits/{run_id}/tests/{first_test_id}/regenerate")
            assert replacement.status_code == 200
            assert replacement.json()["quality_status"] == "pending"
            assert client.patch(f"/api/v1/audits/{run_id}/tests/{first_test_id}/review", json={
                "quality_status": "accepted",
            }).status_code == 200

            assert client.post(f"/api/v1/audits/{run_id}/execute").status_code == 200
            assert client.post(f"/api/v1/audits/{run_id}/evaluate").status_code == 200
            result = client.get(f"/api/v1/audits/{run_id}/results")
            assert result.status_code == 200
            assert result.json()["tests_total"] > 0
            trace = client.get(f"/api/v1/audits/{run_id}/target-memory-trace")
            assert trace.status_code == 200
            assert trace.json()["records"]
            assert trace.json()["retrievals"]
        finally:
            app.dependency_overrides.clear()
