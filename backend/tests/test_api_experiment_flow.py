"""End-to-end API coverage for the reproducible offline experiment path."""
from datetime import datetime, timezone
from io import BytesIO, StringIO
import csv
import hashlib
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base, get_db
from app.main import app
from app.evaluator.factory import configured_evaluator
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
                    "based_on_review_versions": {r.json()["review_id"]: r.json()["updated_at"] for r in (independent_a, independent_b)},
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
            assert {test["generator_version"] for test in tests} == {"direct-ground-truth-v3"}
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
            answer_rows = [answer for item in body["runs"] for answer in item["answers"]]
            answer_keys = {(answer["run_id"], answer["test_id"]) for answer in answer_rows}
            assert len(answer_keys) == len(answer_rows) == 8
            assert {answer["outcome"] for answer in answer_rows} >= {"pass", "fail"}
            assert all(answer["response_id"] and answer["evaluation_id"] and answer["prompt"]
                       and answer["expected_behavior"] and answer["answer"] is not None
                       and "source_evidence" in answer for answer in answer_rows)
            assert len(body["paired_comparisons"]) == 1
            pair = body["paired_comparisons"][0]
            assert pair["shared_tests"] == 4
            assert pair["candidate_delta_confidence_interval_low"] is not None
            assert pair["two_sided_sign_test_p_value"] is not None

            export = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv")
            assert export.status_code == 200
            assert export.headers["content-type"].startswith("text/csv")
            records = list(csv.DictReader(StringIO(export.text)))
            assert all(None not in row for row in records)
            answer_csv_rows = [row for row in records if row["record_type"] == "answer"]
            assert {(row["run_id"], row["test_id"]) for row in answer_csv_rows} == answer_keys
            csv_answers_by_key = {(row["run_id"], row["test_id"]): row for row in answer_csv_rows}
            for answer in answer_rows:
                row = csv_answers_by_key[(answer["run_id"], answer["test_id"])]
                assert row["response_id"] == answer["response_id"]
                assert row["evaluation_id"] == answer["evaluation_id"]
                assert row["prompt"] == answer["prompt"]
                assert row["expected_behavior"] == answer["expected_behavior"]
                assert row["answer"] == answer["answer"]
                assert row["outcome"].lower() == answer["outcome"]
            assert {row["condition_id"] for row in records if row["record_type"] == "condition"} == {item["condition_id"] for item in body["conditions"]}
            for item in body["conditions"]:
                metrics = {row["metric"]: row["value"] for row in records if row["record_type"] == "condition" and row["condition_id"] == item["condition_id"]}
                assert int(metrics["answers_decided"]) == item["tests_total"]
                assert int(metrics["answers_passed"]) == item["tests_passed"]
                assert int(metrics["pending_judgments"]) == 0
            metadata = json.loads(next(row["detail"] for row in records if row["record_type"] == "analysis_metadata"))
            assert metadata["single_question_interval"] == "not_estimable"
            assert metadata["resampling_unit"] == "paired_decided_question"
            assert "paired_comparison" in export.text
            assert "Analytics comparison" not in export.text  # only public identifiers/configuration are emitted
            bundle = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/reproducibility-bundle.json")
            assert bundle.status_code == 200
            assert bundle.headers["content-type"].startswith("application/json")
            assert bundle.json()["analysis_metadata"] == metadata
            assert bundle.json()["frozen_test_suite"]
            assert len(bundle.json()["runs"]) == 2
            assert {(answer["run_id"], answer["test_id"])
                    for run in bundle.json()["runs"] for answer in run["answers"]} == answer_keys
            artifact = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/artifact.zip")
            assert artifact.status_code == 200
            assert artifact.headers["content-type"].startswith("application/zip")
            with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                assert json.loads(archive.read("analysis-metadata.json")) == metadata
                assert "analysis-metadata.json" in manifest["files"]
                assert manifest["schema_version"] == "memory-health-experiment-artifact-v2"
                assert manifest["frozen_test_suite_sha256"] == hashlib.sha256(
                    archive.read("frozen-test-suite.json")
                ).hexdigest()
                assert "dataset_hash_sha256" not in manifest
                assert "frozen-test-suite.json" in manifest["files"]
                assert any(name.endswith("retrieval-trace.json") for name in archive.namelist())
            # Fixed ZIP timestamps and canonical JSON make the completed
            # artifact byte-stable for the same persisted experiment.
            assert artifact.content == client.get(f"/api/v1/experiments/{experiment['experiment_id']}/artifact.zip").content
            # Identical questions alone do not make different judges comparable.
            from app.models import EvaluationResultModel, TargetResponseModel, TestCaseModel
            from sqlalchemy import select
            with session_factory() as db:
                failed = db.scalar(select(EvaluationResultModel).join(TestCaseModel).where(
                    TestCaseModel.run_id == runs[0]['run_id'], EvaluationResultModel.passed.is_(False)))
                assert failed is not None
                failed.reason = '=1+1'
                db.commit()
            guarded_csv = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv")
            protected_rows = list(csv.DictReader(StringIO(guarded_csv.text)))
            assert any(row['record_type'] == 'failure' and row['detail'] == '\t=1+1' for row in protected_rows)
            assert any(row['record_type'] == 'serialization_metadata' and row['value'] == 'spreadsheet-text-v1' for row in protected_rows)
            original_bundle = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/reproducibility-bundle.json").json()
            assert any(failure['evaluation']['reason'] == '=1+1' for run in original_bundle['runs']
                       for failure in run['result']['failures'])
            with session_factory() as db:
                evaluation = db.scalar(select(EvaluationResultModel).join(TestCaseModel).where(
                    TestCaseModel.run_id == runs[1]['run_id']))
                evaluation.evaluator = 'different-review-standard-v1'
                db.commit()
            guarded = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results").json()['paired_comparisons'][0]
            assert guarded['shared_tests'] == 3
            assert guarded['excluded_assessment_count'] == 1
            with session_factory() as db:
                uncertain = db.scalar(select(EvaluationResultModel).join(TestCaseModel).where(
                    TestCaseModel.run_id == runs[1]['run_id'],
                    EvaluationResultModel.evaluator != 'different-review-standard-v1'))
                uncertain.passed = None
                db.commit()
            partial = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results").json()['paired_comparisons'][0]
            assert partial['shared_question_count'] == 4
            assert partial['shared_tests'] == 2
            assert partial['excluded_assessment_count'] == partial['excluded_uncertain_count'] == 1
            with session_factory() as db:
                saved_uncertain = db.scalar(select(EvaluationResultModel).join(TestCaseModel).where(
                    TestCaseModel.run_id == runs[1]['run_id'], EvaluationResultModel.passed.is_(None)))
                uncertain_id = saved_uncertain.id
                uncertain_test_id = saved_uncertain.test_id
                dimension = db.get(TestCaseModel, saved_uncertain.test_id).dimension
                original_response_id = saved_uncertain.response_id
            partial_report = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results").json()
            partial_answers = [answer for run in partial_report["runs"] for answer in run["answers"]]
            assert any(answer["run_id"] == runs[1]["run_id"] and answer["test_id"] == uncertain_test_id
                       and answer["outcome"] == "uncertain" for answer in partial_answers)
            partial_answer_csv = list(csv.DictReader(StringIO(
                client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv").text)))
            assert any(row["record_type"] == "answer" and row["run_id"] == runs[1]["run_id"]
                       and row["test_id"] == uncertain_test_id and row["outcome"] == "uncertain"
                       for row in partial_answer_csv)
            condition_id = next(item['condition_id'] for item in partial_report['conditions'] if runs[1]['run_id'] in item['run_ids'])
            def dimension_export():
                response = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv")
                assert response.status_code == 200
                return {row['metric']: row['value'] for row in csv.DictReader(StringIO(response.text))
                        if row['record_type'] == 'dimension' and row['condition_id'] == condition_id and row['dimension'] == dimension}
            pending_export = dimension_export()
            assert pending_export['score_state'] == 'awaiting_review'
            assert pending_export['mean_percentage'] == ''
            assert pending_export['pending_judgments'] == pending_export['expected_questions'] == '1'
            assert pending_export['excluded_evidence'] == '0'
            paired_export = {row['metric']: row['value'] for row in csv.DictReader(StringIO(
                client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv").text))
                if row['record_type'] == 'paired_comparison'}
            assert paired_export['shared_questions'] == '4'
            assert paired_export['comparable_decided_questions'] == '2'
            assert paired_export['pending_comparisons'] == paired_export['excluded_assessments'] == '1'
            with session_factory() as db:
                mismatched = db.scalar(select(TargetAgentRetrievalModel.final_response_id).where(
                    TargetAgentRetrievalModel.run_id == runs[1]['run_id'],
                    TargetAgentRetrievalModel.final_response_id != original_response_id))
                db.get(EvaluationResultModel, uncertain_id).response_id = mismatched
                db.commit()
            unavailable_export = dimension_export()
            assert unavailable_export['score_state'] == 'evidence_unavailable'
            assert unavailable_export['mean_percentage'] == ''
            assert unavailable_export['excluded_evidence'] == unavailable_export['expected_questions'] == '1'
            assert unavailable_export['pending_judgments'] == '0'
            with session_factory() as db:
                db.get(EvaluationResultModel, uncertain_id).response_id = original_response_id
                db.commit()
            # Matching incomplete local-judge provenance is still not comparable.
            with session_factory() as db:
                for evaluation in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(
                        TestCaseModel.run_id.in_([row['run_id'] for row in runs]))):
                    evaluation.evaluator = 'llm-judge-ollama-v4'
                    evaluation.judge_execution = None
                    evaluation.passed = True
                db.commit()
            incomplete = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results").json()['paired_comparisons'][0]
            assert incomplete['shared_tests'] == 0
            assert incomplete['excluded_assessment_count'] == 4
            assert incomplete['candidate_delta_percentage_points'] is None
            assert incomplete['two_sided_sign_test_p_value'] is None

            # A uniquely saved response remains reportable when no assessment
            # exists; ambiguous duplicate responses and cross-run verdict
            # bindings are omitted rather than selected by row order.
            with session_factory() as db:
                unassessed_evaluation = db.scalar(select(EvaluationResultModel).join(TestCaseModel).where(
                    TestCaseModel.run_id == runs[0]['run_id']))
                unassessed_test_id = unassessed_evaluation.test_id
                unassessed_response_id = unassessed_evaluation.response_id
                db.delete(unassessed_evaluation)
                db.commit()
            unassessed_report = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results").json()
            unassessed_answers = [answer for run in unassessed_report['runs'] for answer in run['answers']]
            unassessed_answer = next(answer for answer in unassessed_answers
                                     if answer['run_id'] == runs[0]['run_id'] and answer['test_id'] == unassessed_test_id)
            assert unassessed_answer['response_id'] == unassessed_response_id
            assert unassessed_answer['evaluation_id'] is None
            assert unassessed_answer['outcome'] == 'unassessed'
            assert unassessed_answer['observed_category'] is None
            assert unassessed_answer['evaluation_reason'] is None
            unassessed_csv = list(csv.DictReader(StringIO(
                client.get(f"/api/v1/experiments/{experiment['experiment_id']}/export.csv").text)))
            unassessed_row = next(row for row in unassessed_csv
                                  if row['record_type'] == 'answer' and row['run_id'] == runs[0]['run_id']
                                  and row['test_id'] == unassessed_test_id)
            assert unassessed_row['response_id'] == unassessed_response_id
            assert unassessed_row['evaluation_id'] == ''
            assert unassessed_row['outcome'] == 'unassessed'
            answer_bundle = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/reproducibility-bundle.json").json()
            assert any(answer['test_id'] == unassessed_test_id and answer['outcome'] == 'unassessed'
                       and answer['evaluation_id'] is None for run in answer_bundle['runs'] for answer in run['answers'])
            with session_factory() as db:
                original_response = db.get(TargetResponseModel, unassessed_response_id)
                db.add(TargetResponseModel(
                    id='RESP-DUPLICATE-PAIR', run_id=original_response.run_id, test_id=original_response.test_id,
                    response_text=original_response.response_text, model=original_response.model,
                    temperature=original_response.temperature, execution_metadata=original_response.execution_metadata,
                ))
                cross_run_test = db.scalar(select(TestCaseModel).where(
                    TestCaseModel.run_id == runs[0]['run_id'], TestCaseModel.id != unassessed_test_id))
                cross_run_test_id = cross_run_test.id
                cross_run_evaluation = db.scalar(select(EvaluationResultModel).where(
                    EvaluationResultModel.test_id == cross_run_test_id))
                foreign_response = db.scalar(select(TargetResponseModel).where(
                    TargetResponseModel.run_id == runs[1]['run_id'],
                    TargetResponseModel.test_id != cross_run_test_id))
                cross_run_evaluation.response_id = foreign_response.id
                db.commit()
            ambiguous_report = client.get(f"/api/v1/experiments/{experiment['experiment_id']}/results").json()
            ambiguous_keys = {(answer['run_id'], answer['test_id'])
                              for run in ambiguous_report['runs'] for answer in run['answers']}
            assert (runs[0]['run_id'], unassessed_test_id) not in ambiguous_keys
            assert (runs[0]['run_id'], cross_run_test_id) not in ambiguous_keys
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
            assert audit.json()["evaluator_model"] == configured_evaluator("rule_based")[1]
    finally:
        app.dependency_overrides.clear()
