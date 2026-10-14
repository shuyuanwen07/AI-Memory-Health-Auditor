"""A reviewed suite must still satisfy its frozen coverage before any target call."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api import routes
from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, TestCaseModel, TargetResponseModel


@pytest.fixture
def saved_suite(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    engine = create_engine(f"sqlite:///{tmp_path / 'coverage.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)

    def test_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            imported = client.post("/api/v1/conversations", json={
                "authorised": True, "source_origin": "synthetic",
                "messages": [{"role": "user", "content": "I used MySQL before. The backend now uses PostgreSQL. I prefer Python. This assignment requires Java."}],
            })
            assert imported.status_code == 201
            conversation = imported.json()["conversation_id"]
            memories = client.post(f"/api/v1/conversations/{conversation}/extract").json()
            assert client.post(f"/api/v1/conversations/{conversation}/confirm-ground-truth", json={
                "confirmed_memory_ids": [m["memory_id"] for m in memories],
            }).status_code == 200
            experiment = client.post("/api/v1/experiments", json={
                "conversation_id": conversation, "label": "Synthetic coverage regression",
                "test_suite_configuration": {"test_budget": 4, "pipeline_provider": "rule_based"},
            }).json()
            runs = [client.post("/api/v1/audits", json={
                "conversation_id": conversation, "experiment_id": experiment["experiment_id"],
                "target_configuration": configuration, "provider": "rule_based", "memory_strategy": strategy,
            }).json()["run_id"] for configuration, strategy in (("weak", "weak_first_hit"), ("strong", "strong_rule_based"))]
            response = client.post(f"/api/v1/audits/{runs[0]}/generate-tests")
            assert response.status_code == 200
            generated = response.json()
            assert {test["dimension"] for test in generated} == {"accuracy", "freshness", "conflict_resolution", "appropriate_use"}
            observation = {
                "agent_version": "agent-coverage-semantic-v10", "saved_suite": True,
                "status": "completed", "count_target_met": True,
                "dimension_coverage": [{"dimension": test["dimension"], "evidence_supported": True,
                                        "required_question_count": 1} for test in generated],
                "coverage_plan": [{"dimension": test["dimension"], "test_type": test["test_type"],
                                   "supporting_memory_ids": test["supporting_memory_ids"]} for test in generated],
            }
            with sessions() as db:
                source = db.get(AuditRunModel, runs[0])
                source.reproducibility_metadata = {**source.reproducibility_metadata, "generation_observations": [observation]}
                db.commit()
            yield client, sessions, runs, observation
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize("version", [5, 9, 10, 99])
@pytest.mark.parametrize("member", [0, 1])
def test_all_generator_versions_and_shared_peers_enforce_dimension_quotas(saved_suite, monkeypatch, version, member):
    client, sessions, runs, observation = saved_suite
    with sessions() as db:
        source = db.get(AuditRunModel, runs[0])
        changed = deepcopy(observation)
        changed["agent_version"] = f"agent-coverage-semantic-v{version}"
        source.reproducibility_metadata = {**source.reproducibility_metadata, "generation_observations": [changed]}
        row = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[member], TestCaseModel.dimension == "freshness"))
        row.dimension = "accuracy"
        db.commit()
    monkeypatch.setattr(routes, "get_target_system_adapter", lambda *_args: pytest.fail("Coverage failure must precede target calls"))
    response = client.post(f"/api/v1/audits/{runs[member]}/execute")
    assert response.status_code == 409
    assert "freshness needs 1, has 0" in response.json()["detail"]
    with sessions() as db:
        assert db.get(AuditRunModel, runs[member]).status == "TESTS_GENERATED"
        assert db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id == runs[member])) is None


@pytest.mark.parametrize("drift", ["test_type", "evidence", "duplicate_evidence"])
def test_dimension_totals_cannot_hide_drift_from_frozen_evidence_slot(saved_suite, monkeypatch, drift):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        row = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[1], TestCaseModel.dimension == "freshness"))
        if drift == "test_type":
            row.test_type = "direct"
        elif drift == "evidence":
            row.supporting_memory_ids = row.supporting_memory_ids[:1]
        else:
            row.supporting_memory_ids = [*row.supporting_memory_ids, row.supporting_memory_ids[0]]
        db.commit()
    monkeypatch.setattr(routes, "get_target_system_adapter", lambda *_args: pytest.fail("Evidence drift must precede target calls"))
    response = client.post(f"/api/v1/audits/{runs[1]}/execute")
    assert response.status_code == 409
    assert "frozen freshness evidence slot" in response.json()["detail"]


def test_failed_refill_cannot_remove_saved_suite_quota(saved_suite, monkeypatch):
    client, sessions, runs, observation = saved_suite
    with sessions() as db:
        source = db.get(AuditRunModel, runs[0])
        source.reproducibility_metadata = {**source.reproducibility_metadata, "generation_observations": [
            observation, {"status": "failed", "saved_suite": False, "coverage_plan": []},
        ]}
        row = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[0], TestCaseModel.dimension == "freshness"))
        row.dimension = "accuracy"
        db.commit()
    monkeypatch.setattr(routes, "get_target_system_adapter", lambda *_args: pytest.fail("Failed refill cannot relax quotas"))
    review = client.get(f"/api/v1/audits/{runs[0]}/test-review")
    assert review.status_code == 200
    freshness = next(row for row in review.json()["dimension_coverage"] if row["dimension"] == "freshness")
    assert freshness["required_question_count"] == 1
    assert freshness["accepted_question_count"] == 0
    response = client.post(f"/api/v1/audits/{runs[0]}/execute")
    assert response.status_code == 409
    assert "freshness needs 1, has 0" in response.json()["detail"]


def test_complete_matching_shared_suite_executes(saved_suite):
    client, sessions, runs, _ = saved_suite
    response = client.post(f"/api/v1/audits/{runs[1]}/execute")
    assert response.status_code == 200
    assert len(response.json()) == 4
    with sessions() as db:
        assert db.get(AuditRunModel, runs[1]).status == "TESTS_EXECUTED"


@pytest.mark.parametrize("defect", ["missing_contract", "shortfall"])
def test_modern_suite_cannot_execute_with_missing_plan_or_declared_shortfall(saved_suite, monkeypatch, defect):
    client, sessions, runs, observation = saved_suite
    changed = deepcopy(observation)
    if defect == "missing_contract":
        changed.pop("coverage_plan")
        changed.pop("dimension_coverage")
    else:
        changed["count_target_met"] = False
    with sessions() as db:
        source = db.get(AuditRunModel, runs[0])
        source.reproducibility_metadata = {**source.reproducibility_metadata, "generation_observations": [changed]}
        db.commit()
    monkeypatch.setattr(routes, "get_target_system_adapter", lambda *_args: pytest.fail("Incomplete coverage cannot invoke the target"))
    response = client.post(f"/api/v1/audits/{runs[0]}/execute")
    assert response.status_code == 409
    assert "before execution" in response.json()["detail"]


def test_true_count_receipt_cannot_authorise_questions_beyond_frozen_budget(saved_suite, monkeypatch):
    client, sessions, runs, _ = saved_suite
    with sessions() as db:
        original = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == runs[1], TestCaseModel.dimension == "accuracy"))
        db.add(TestCaseModel(
            id="T-SYN-EXTRA", run_id=runs[1], dimension="accuracy", test_type=original.test_type,
            prompt="What additional recorded detail should be recalled?", expected_behavior=original.expected_behavior,
            supporting_memory_ids=original.supporting_memory_ids, generator_version=original.generator_version,
            quality_status="accepted", grounding_status="grounded", target_memory_context=[],
        ))
        db.commit()
    monkeypatch.setattr(routes, "get_target_system_adapter", lambda *_args: pytest.fail("A stale count flag cannot increase the budget"))
    response = client.post(f"/api/v1/audits/{runs[1]}/execute")
    assert response.status_code == 409
    assert "requires 4 accepted questions, but has 5" in response.json()["detail"]


def test_target_failure_receipt_is_saved_without_losing_prior_replies(saved_suite,monkeypatch):
    from fastapi import HTTPException
    from app.models import AgentExecutionModel,TargetResponseModel
    client,sessions,runs,_=saved_suite
    original=routes.get_target_system_adapter
    class FailingAdapter:
        def __init__(self,delegate):
            self.delegate=delegate
            self.calls=0
        def ingest(self,conversation):return self.delegate.ingest(conversation)
        def trace(self):return self.delegate.trace()
        def reset(self):return self.delegate.reset()
        def answer(self,test,audit):
            self.calls+=1
            if self.calls==3:
                failure=HTTPException(502,'The target service rejected the request during peak load.')
                failure.target_execution={'test_id':test.test_id,'request_attempts':1,'last_http_status':200,'provider_error_scope':'top_level','provider_error_status':502,'provider_error_category':'capacity_limit','requested_output_token_limit':512,'error_summary':failure.detail}
                raise failure
            return self.delegate.answer(test,audit)
    monkeypatch.setattr(routes,'get_target_system_adapter',lambda db,audit:FailingAdapter(original(db,audit)))
    response=client.post(f'/api/v1/audits/{runs[0]}/execute')
    assert response.status_code==502
    with sessions() as db:
        replies=db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==runs[0])).all()
        failures=db.scalars(select(AgentExecutionModel).where(AgentExecutionModel.run_id==runs[0],AgentExecutionModel.role=='target_answer')).all()
        assert len(replies)==2
        assert len(failures)==1
        failure=failures[0]
        assert failure.status=='failed' and failure.output_data is None
        assert failure.input_refs['test_id'] not in {r.test_id for r in replies}
        assert failure.attempt_count==1
        assert failure.error_diagnostics['last_http_status']==200
        assert failure.error_diagnostics['provider_error_category']=='capacity_limit'
        assert failure.error_diagnostics['requested_output_token_limit']==512
        assert db.get(AuditRunModel,runs[0]).status=='FAILED'
