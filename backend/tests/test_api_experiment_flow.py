"""End-to-end API coverage for the reproducible offline experiment path."""
from datetime import datetime, timezone
from io import BytesIO
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, TargetAgentMemoryModel, TargetAgentRetrievalModel


def test_complete_audit_keeps_private_target_context_off_the_api(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    database_url = f"sqlite:///{tmp_path / 'audit.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with TestClient(app) as client:
            conversation = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp, "content": (
                    "I used MySQL before. The backend now uses PostgreSQL. I generally prefer Python. "
                    "This assignment currently requires Java. I am based in Sydney."
                )}],
            }).json()
            conversation_id = conversation["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert memories
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [memory["memory_id"] for memory in memories]
            }).status_code == 200

            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "target_configuration": "weak", "provider": "rule_based",
                "test_budget": 4,
            }).json()
            assert audit["pipeline_provider"] == "rule_based"
            assert audit["evaluator_provider"] == "rule_based"
            assert audit["target_memory_capacity"] == 50
            assert audit["target_system_adapter"] == "controlled-memory"
            run_id = audit["run_id"]

            generated = client.post(f"/api/v1/audits/{run_id}/generate-tests")
            assert generated.status_code == 200
            assert generated.json()
            assert all("target_memory_context" not in test for test in generated.json())
            assert all(test["quality_status"] == "accepted" for test in generated.json())
            assert all(test["grounding_status"] == "grounded" for test in generated.json())
            listed = client.get(f"/api/v1/audits/{run_id}/tests")
            assert listed.status_code == 200
            assert all("target_memory_context" not in test for test in listed.json())
            assert client.post(f"/api/v1/audits/{run_id}/execute").status_code == 200
            check = session_factory()
            try:
                assert check.query(TargetAgentMemoryModel).filter_by(run_id=run_id).count() > 0
                assert check.query(TargetAgentRetrievalModel).filter_by(run_id=run_id).count() == len(generated.json())
                assert check.query(TargetAgentRetrievalModel).filter_by(run_id=run_id, final_response_id=None).count() == 0
            finally:
                check.close()
            assert client.post(f"/api/v1/audits/{run_id}/evaluate").status_code == 200
            results = client.get(f"/api/v1/audits/{run_id}/results")
            assert results.status_code == 200
            assert results.json()["tests_total"] == len(generated.json())
            assert "retrieval_quality" in results.json()
            assert results.json()["retrieval_quality"]["tests_measured"] == len(generated.json())
            assert results.json()["retrieval_quality"]["evidence_recall_at_k"] is not None
            review_items = client.get(f"/api/v1/audits/{run_id}/evaluation-review")
            assert review_items.status_code == 200
            assert len(review_items.json()) == len(generated.json())
            first = review_items.json()[0]
            saved_review = client.patch(
                f"/api/v1/audits/{run_id}/evaluations/{first['automated']['evaluation_id']}/review",
                json={"human_passed": True, "reviewer_label": "reviewer-a", "note": "Checked against the response."},
            )
            assert saved_review.status_code == 200
            # Existing clients did not send a role and may change their
            # pseudonym while editing the historical single reference row.
            legacy_update = client.patch(
                f"/api/v1/audits/{run_id}/evaluations/{first['automated']['evaluation_id']}/review",
                json={"human_passed": True, "reviewer_label": "reviewer-b"},
            )
            assert legacy_update.status_code == 200
            assert legacy_update.json()["review_role"] == "reference"
            independent_a = client.patch(
                f"/api/v1/audits/{run_id}/evaluations/{first['automated']['evaluation_id']}/review",
                json={"human_passed": False, "human_failure_type": "accuracy", "reviewer_label": "annotator-1", "review_role": "independent"},
            )
            independent_b = client.patch(
                f"/api/v1/audits/{run_id}/evaluations/{first['automated']['evaluation_id']}/review",
                json={"human_passed": False, "human_failure_type": "accuracy", "reviewer_label": "annotator-2", "review_role": "independent"},
            )
            assert independent_a.status_code == 200
            assert independent_b.status_code == 200
            adjudication = client.patch(
                f"/api/v1/audits/{run_id}/evaluations/{first['automated']['evaluation_id']}/review",
                json={
                    "human_passed": False, "human_failure_type": "accuracy", "reviewer_label": "adjudicator-1",
                    "review_role": "adjudication",
                    "based_on_review_ids": [independent_a.json()["review_id"], independent_b.json()["review_id"]],
                },
            )
            assert adjudication.status_code == 200
            reviewed_item = client.get(f"/api/v1/audits/{run_id}/evaluation-review").json()[0]
            assert reviewed_item["human_review"]["review_role"] == "adjudication"
            assert len(reviewed_item["human_reviews"]) == 4
            calibration = client.get(f"/api/v1/audits/{run_id}/evaluation-calibration")
            assert calibration.status_code == 200
            assert calibration.json()["human_reviewed_count"] == 1
            assert calibration.json()["independent_review_count"] == 2
            assert calibration.json()["independent_consensus_count"] == 1
            assert calibration.json()["independent_pair_kappa"] is None
            # Simulate an interruption after every durable artifact committed
            # but before the final public lifecycle transition. Recovery must
            # repair status without invoking a target or evaluator again.
            with session_factory() as db:
                interrupted = db.get(AuditRunModel, run_id)
                interrupted.status = "FAILED"
                interrupted.completed_at = None
                db.commit()
            assert client.get(f"/api/v1/audits/{run_id}/retry-plan").json()["retryable"] is False
            assert client.post(f"/api/v1/audits/{run_id}/retry").json()["status"] == "COMPLETED"
            for failure in results.json()["failures"]:
                assert "target_memory_context" not in failure["test"]
    finally:
        app.dependency_overrides.clear()


def test_experiment_generates_one_shared_suite_for_multiple_memory_strategies(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'shared-suite.db'}")
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
            timestamp = datetime.now(timezone.utc).isoformat()
            conversation_id = client.post("/api/v1/conversations", json={"authorised": True, "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp, "content": "I used MySQL before. The backend now uses PostgreSQL. I generally prefer Python. This assignment currently requires Java. I am based in Sydney."}]}).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={"confirmed_memory_ids": [item["memory_id"] for item in memories]})
            experiment = client.post("/api/v1/experiments", json={"conversation_id": conversation_id, "label": "Shared strategy comparison", "test_suite_configuration": {"test_budget": 4, "random_seed": 42, "prompt_template_version": "rule-based-v1", "pipeline_provider": "rule_based", "pipeline_model": "rule-based-v2"}}).json()
            runs = [client.post("/api/v1/audits", json={"conversation_id": conversation_id, "experiment_id": experiment["experiment_id"], "target_configuration": target, "memory_strategy": strategy, "provider": "rule_based"}).json() for target, strategy in [("weak", "weak_first_hit"), ("strong", "strong_rule_based")]]

            source_tests = client.post(f"/api/v1/audits/{runs[0]['run_id']}/generate-tests").json()
            peer_tests = client.get(f"/api/v1/audits/{runs[1]['run_id']}/tests").json()
            assert [item["prompt"] for item in source_tests] == [item["prompt"] for item in peer_tests]
            assert [item["expected_behavior"] for item in source_tests] == [item["expected_behavior"] for item in peer_tests]
            assert {item["test_id"] for item in source_tests}.isdisjoint({item["test_id"] for item in peer_tests})
            assert client.post(f"/api/v1/audits/{runs[1]['run_id']}/generate-tests").status_code == 200
            late_member = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
                "target_configuration": "strong", "provider": "rule_based",
            })
            assert late_member.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_experiment_can_freeze_a_direct_ground_truth_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'direct-baseline.db'}")
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
            timestamp = datetime.now(timezone.utc).isoformat()
            conversation_id = client.post("/api/v1/conversations", json={"authorised": True, "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp, "content": "I am based in Sydney. I prefer Python."}]}).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={"confirmed_memory_ids": [item["memory_id"] for item in memories]}).status_code == 200
            experiment = client.post("/api/v1/experiments", json={"conversation_id": conversation_id, "label": "Direct baseline", "test_suite_configuration": {"test_budget": 8, "random_seed": 42, "prompt_template_version": "baseline-v1", "pipeline_provider": "rule_based", "pipeline_model": "rule-based-v2", "suite_mode": "direct_ground_truth"}}).json()
            run = client.post("/api/v1/audits", json={"conversation_id": conversation_id, "experiment_id": experiment["experiment_id"], "target_configuration": "strong", "provider": "rule_based"}).json()
            tests = client.post(f"/api/v1/audits/{run['run_id']}/generate-tests").json()
            assert tests
            assert {test["test_type"] for test in tests} == {"direct"}
            assert {test["generator_version"] for test in tests} == {"direct-ground-truth-v1"}
    finally:
        app.dependency_overrides.clear()


def test_experiment_history_aligns_completed_runs_and_exports_csv(monkeypatch, tmp_path):
    """History is group-scoped and pair alignment uses the frozen shared suite."""
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
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
            timestamp = datetime.now(timezone.utc).isoformat()
            conversation_id = client.post("/api/v1/conversations", json={"authorised": True, "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp, "content": "I used MySQL before. The backend now uses PostgreSQL. I generally prefer Python. This assignment currently requires Java. I am based in Sydney."}]}).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={"confirmed_memory_ids": [item["memory_id"] for item in memories]})
            experiment = client.post("/api/v1/experiments", json={"conversation_id": conversation_id, "label": "Analytics comparison", "test_suite_configuration": {"test_budget": 4, "pipeline_provider": "rule_based", "pipeline_model": "rule-based-v2"}}).json()
            runs = [client.post("/api/v1/audits", json={"conversation_id": conversation_id, "experiment_id": experiment["experiment_id"], "target_configuration": target, "memory_strategy": strategy, "provider": "rule_based"}).json() for target, strategy in [("weak", "weak_first_hit"), ("strong", "strong_rule_based")]]
            client.post(f"/api/v1/audits/{runs[0]['run_id']}/generate-tests")
            for run in runs:
                assert client.post(f"/api/v1/audits/{run['run_id']}/execute").status_code == 200
                assert client.post(f"/api/v1/audits/{run['run_id']}/evaluate").status_code == 200

            report = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results")
            assert report.status_code == 200
            body = report.json()
            assert len(body["runs"]) == 2
            assert len(body["conditions"]) == 2
            assert all(item["result"] is not None for item in body["runs"])
            assert len(body["paired_comparisons"]) == 1
            pair = body["paired_comparisons"][0]
            assert pair["shared_tests"] == 4
            assert pair["candidate_delta_confidence_interval_low"] is not None
            assert pair["two_sided_sign_test_p_value"] is not None

            export = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv")
            assert export.status_code == 200
            assert export.headers["content-type"].startswith("text/csv")
            assert "paired_comparison" in export.text
            assert "Analytics comparison" not in export.text  # only public identifiers/configuration are emitted
            bundle = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/reproducibility-bundle.json")
            assert bundle.status_code == 200
            assert bundle.headers["content-type"].startswith("application/json")
            assert bundle.json()["frozen_test_suite"]
            assert len(bundle.json()["runs"]) == 2
            artifact = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/artifact.zip")
            assert artifact.status_code == 200
            assert artifact.headers["content-type"].startswith("application/zip")
            with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                assert manifest["dataset_hash_sha256"]
                assert "frozen-test-suite.json" in manifest["files"]
                assert any(name.endswith("retrieval-trace.json") for name in archive.namelist())
            # Fixed ZIP timestamps and canonical JSON make the completed
            # artifact byte-stable for the same persisted experiment.
            assert artifact.content == client.get(f"/api/v1/experiments/{experiment['experiment_id']}/artifact.zip").content
    finally:
        app.dependency_overrides.clear()


def test_cancelling_every_condition_finishes_the_experiment_group(monkeypatch, tmp_path):
    """A cancelled condition must not leave a fair-comparison group running."""
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'cancelled-group.db'}")
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
            timestamp = datetime.now(timezone.utc).isoformat()
            conversation_id = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp,
                              "content": "I am based in Sydney."}],
            }).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [item["memory_id"] for item in memories]
            }).status_code == 200
            experiment = client.post("/api/v1/experiments", json={
                "conversation_id": conversation_id, "label": "Cancelled comparison"
            }).json()
            runs = [client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
                "target_configuration": target, "provider": "rule_based",
            }).json() for target in ("weak", "strong")]
            assert client.post(f"/api/v1/audits/{runs[0]['run_id']}/cancel").status_code == 200
            cancelled = client.post(f"/api/v1/audits/{runs[1]['run_id']}/cancel")
            assert cancelled.status_code == 200
            listed = client.get("/api/v1/experiments").json()
            group = next(item for item in listed if item["experiment_id"] == experiment["experiment_id"])
            assert group["status"] == "CANCELLED"
            assert group["completed_at"] is not None
    finally:
        app.dependency_overrides.clear()


def test_cancelling_an_experiment_stops_unfinished_conditions_without_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'cancel-experiment.db'}")
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
            timestamp = datetime.now(timezone.utc).isoformat()
            conversation_id = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp,
                              "content": "I am based in Sydney."}],
            }).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [item["memory_id"] for item in memories]
            }).status_code == 200
            experiment = client.post("/api/v1/experiments", json={
                "conversation_id": conversation_id, "label": "Stop comparison"
            }).json()
            runs = [client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
                "target_configuration": target, "provider": "rule_based",
            }).json() for target in ("weak", "strong")]

            cancelled = client.post(f"/api/v1/experiments/{experiment['experiment_id']}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "CANCELLED"
            assert all(client.get(f"/api/v1/audits/{run['run_id']}").json()["status"] == "CANCELLED" for run in runs)
            assert all(client.get(f"/api/v1/audits/{run['run_id']}/retry-plan").json()["retryable"] is False for run in runs)
            assert all(client.post(f"/api/v1/audits/{run['run_id']}/retry").json()["status"] == "CANCELLED" for run in runs)
            late_member = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
                "target_configuration": "strong", "provider": "rule_based",
            })
            assert late_member.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_experiment_freezes_evaluator_identity_for_every_condition(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'frozen-evaluator.db'}")
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
            timestamp = datetime.now(timezone.utc).isoformat()
            conversation_id = client.post("/api/v1/conversations", json={
                "authorised": True,
                "messages": [{"message_id": "MSG001", "role": "user", "timestamp": timestamp,
                              "content": "I am based in Sydney."}],
            }).json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation_id}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [item["memory_id"] for item in memories]
            }).status_code == 200
            experiment = client.post("/api/v1/experiments", json={
                "conversation_id": conversation_id, "label": "Frozen evaluator",
                "test_suite_configuration": {
                    "pipeline_provider": "rule_based", "pipeline_model": "rule-based-v2",
                    "evaluator_provider": "rule_based", "evaluator_model": "rule-based-v2",
                },
            }).json()
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "experiment_id": experiment["experiment_id"],
                "target_configuration": "strong", "provider": "rule_based",
                "evaluator_provider": "openai", "evaluator_model": "unrelated-judge",
            })
            assert audit.status_code == 201, audit.text
            assert audit.json()["evaluator_provider"] == "rule_based"
            assert audit.json()["evaluator_model"] == "rule-based-v2"
    finally:
        app.dependency_overrides.clear()
