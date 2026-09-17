"""Public contracts for pre-execution suite review and post-audit target traces."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import routes
from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel
from app.schemas import EvaluationResult, TargetResponse


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
            assert payload["target_memory_writer"] == "rule_based"
            assert payload["target_memory_writer_version"] == "rule-based-memory-extractor-v1"
            assert "expected_behavior" not in str(payload)
            assert "target_memory_context" not in str(payload)
            assert any(event["details"].get("writer_version") for event in payload["events"])
        finally:
            app.dependency_overrides.clear()


def test_cancelled_audit_exposes_only_terminal_retained_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'cancelled-trace.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            conversation_id = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "content": "I am based in Sydney.",
                              "timestamp": datetime.now(timezone.utc).isoformat()}],
            }).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [item["memory_id"] for item in memories]
            }).status_code == 200
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "target_configuration": "strong", "provider": "rule_based",
            }).json()
            assert client.post(f"/api/v1/audits/{audit['run_id']}/generate-tests").status_code == 200
            assert client.post(f"/api/v1/audits/{audit['run_id']}/cancel").status_code == 200
            evidence = client.get(f"/api/v1/audits/{audit['run_id']}/cancelled-evidence")
            assert evidence.status_code == 200
            assert evidence.json()["completed_responses"] == []
            assert client.get(f"/api/v1/audits/{audit['run_id']}/target-memory-trace").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_cancellation_during_the_last_target_call_remains_terminal(monkeypatch, tmp_path):
    """A stale executor must never overwrite cancellation after its last call."""
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'target-cancel-race.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class CancellingTarget:
        def ingest(self, _conversation): pass
        def answer(self, test, audit):
            with session_factory() as cancellation_db:
                cancellation_db.get(AuditRunModel, audit.run_id).status = "CANCELLED"
                cancellation_db.commit()
            return TargetResponse(
                response_id="R-CANCELLED", test_id=test.test_id, run_id=audit.run_id,
                response_text="Sydney", model=audit.model, temperature=0,
                created_at=datetime.now(timezone.utc),
            )
        def trace(self): return {}
        def reset(self): pass

    app.dependency_overrides[get_db] = test_db
    monkeypatch.setattr(routes, "get_target_system_adapter", lambda _db, _audit: CancellingTarget())
    try:
        with TestClient(app) as client:
            conversation_id = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "content": "I am based in Sydney.",
                              "timestamp": datetime.now(timezone.utc).isoformat()}],
            }).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [item["memory_id"] for item in memories],
            })
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "target_configuration": "strong",
                "provider": "rule_based", "test_budget": 1,
            }).json()
            assert client.post(f"/api/v1/audits/{audit['run_id']}/generate-tests").status_code == 200
            executed = client.post(f"/api/v1/audits/{audit['run_id']}/execute")
            assert executed.status_code == 409
            assert client.get(f"/api/v1/audits/{audit['run_id']}").json()["status"] == "CANCELLED"
            assert len(client.get(f"/api/v1/audits/{audit['run_id']}/cancelled-evidence").json()["completed_responses"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_cancellation_during_the_last_evaluation_remains_terminal(monkeypatch, tmp_path):
    """A stale evaluator must never mark a concurrently cancelled run complete."""
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'evaluation-cancel-race.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class CancellingEvaluator:
        def evaluate(self, test, response, _memories):
            with session_factory() as cancellation_db:
                cancellation_db.get(AuditRunModel, response.run_id).status = "CANCELLED"
                cancellation_db.commit()
            return EvaluationResult(
                evaluation_id="E-CANCELLED", test_id=test.test_id, response_id=response.response_id,
                passed=True, reason="The evaluator completed before cancellation was observed.",
                evidence_memory_ids=[], evaluator="test-cancelling-evaluator",
            )

    app.dependency_overrides[get_db] = test_db
    monkeypatch.setattr(routes, "get_behaviour_evaluator", lambda _provider, _model: CancellingEvaluator())
    try:
        with TestClient(app) as client:
            conversation_id = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "content": "I am based in Sydney.",
                              "timestamp": datetime.now(timezone.utc).isoformat()}],
            }).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [item["memory_id"] for item in memories],
            })
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "target_configuration": "strong",
                "provider": "rule_based", "test_budget": 1,
            }).json()
            assert client.post(f"/api/v1/audits/{audit['run_id']}/generate-tests").status_code == 200
            assert client.post(f"/api/v1/audits/{audit['run_id']}/execute").status_code == 200
            evaluated = client.post(f"/api/v1/audits/{audit['run_id']}/evaluate")
            assert evaluated.status_code == 409
            assert client.get(f"/api/v1/audits/{audit['run_id']}").json()["status"] == "CANCELLED"
            assert len(client.get(f"/api/v1/audits/{audit['run_id']}/cancelled-evidence").json()["completed_responses"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_target_memory_writer_is_frozen_at_creation_even_if_environment_changes(monkeypatch, tmp_path):
    """Changing TARGET_MEMORY_WRITER after creation cannot change this run."""
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    monkeypatch.setenv("TARGET_MEMORY_WRITER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, _ = _conversation_and_experiment(client)
            run_id = source["run_id"]
            assert source["target_memory_writer"] == "rule_based"
            assert source["reproducibility"]["target_memory_writer"] == "rule_based"
            assert source["target_memory_writer_version"] == "rule-based-memory-extractor-v1"

            assert client.post(f"/api/v1/audits/{run_id}/generate-tests").status_code == 200
            # An invalid value would make the legacy env-resolving factory
            # fail. Execution succeeds because it uses the persisted field.
            monkeypatch.setenv("TARGET_MEMORY_WRITER", "not-a-writer")
            assert client.post(f"/api/v1/audits/{run_id}/execute").status_code == 200
            assert client.post(f"/api/v1/audits/{run_id}/evaluate").status_code == 200
            trace = client.get(f"/api/v1/audits/{run_id}/target-memory-trace").json()
            assert trace["target_memory_writer"] == "rule_based"
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
