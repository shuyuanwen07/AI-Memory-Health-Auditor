from app.memory_agent.writers import RuleBasedTargetMemoryWriter
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
            for retrieval in payload["retrievals"]:
                receipt = retrieval["memory_input"]
                assert receipt is not None
                assert receipt["record_count"] == len(receipt["sent_memory_ids"])
                assert set(receipt["sent_memory_ids"]) <= set(retrieval["selected_memory_ids"])
                assert len(receipt["instruction_sha256"]) == 64
            assert payload["target_memory_writer"] == "rule_based"
            assert payload["target_memory_writer_version"] == RuleBasedTargetMemoryWriter.VERSION
            assert "expected_behavior" not in str(payload)
            assert "target_memory_context" not in str(payload)
            assert any(event["details"].get("writer_version") for event in payload["events"])
        finally:
            app.dependency_overrides.clear()


def test_explicit_platform_withdrawal_reaches_target_store_without_retiring_other_projects(monkeypatch, tmp_path):
    monkeypatch.setenv('PIPELINE_PROVIDER', 'rule_based')
    monkeypatch.setenv('EVALUATOR_PROVIDER', 'rule_based')
    with _client(tmp_path) as client:
        try:
            messages = ['The Maple review meeting must use Zoom only.',
                        'The Birch review meeting must use Zoom only.',
                        'For the Maple project, the Zoom requirement is withdrawn; use Teams instead.']
            conversation_id = client.post('/api/v1/conversations', json={'authorised': True,
                'messages': [{'role': 'user', 'content': content} for content in messages]}).json()['conversation_id']
            memories = client.post(f'/api/v1/conversations/{conversation_id}/extract').json()
            assert client.post(f'/api/v1/conversations/{conversation_id}/confirm-ground-truth', json={
                'confirmed_memory_ids': [memory['memory_id'] for memory in memories]}).status_code == 200
            run_id = client.post('/api/v1/audits', json={'conversation_id': conversation_id,
                'target_configuration': 'strong', 'provider': 'rule_based', 'memory_strategy': 'scope_aware', 'test_budget': 4}).json()['run_id']
            for stage in ('generate-tests', 'execute', 'evaluate'):
                assert client.post(f'/api/v1/audits/{run_id}/{stage}').status_code == 200
            records = client.get(f'/api/v1/audits/{run_id}/target-memory-trace').json()['records']
            maple_old = next(record for record in records if 'Maple' in record['canonical_value'] and 'only' in record['canonical_value'])
            maple_current = next(record for record in records if 'requires Teams' in record['canonical_value'])
            birch = next(record for record in records if 'Birch' in record['canonical_value'])
            assert maple_old['lifecycle_state'] == 'SUPERSEDED'
            assert maple_current['lifecycle_state'] == 'ACTIVE'
            assert birch['lifecycle_state'] == 'ACTIVE'
            assert not any(record['lifecycle_state'] == 'CONFLICTED' for record in records)
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
            assert source["target_memory_writer_version"] == RuleBasedTargetMemoryWriter.VERSION

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


def test_rejected_probe_can_recover_from_incorrect_type_without_unfreezing_peers(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.schemas import TestCase, TestType
    monkeypatch.setenv('PIPELINE_PROVIDER', 'rule_based')
    with _client(tmp_path) as client:
        try:
            source, peer = _conversation_and_experiment(client)
            tests=client.post(f"/api/v1/audits/{source['run_id']}/generate-tests").json()
            initial=TestCase.model_validate(tests[0])
            new_type=TestType.INDIRECT if initial.test_type!=TestType.INDIRECT else TestType.CONTEXTUAL
            replacement=initial.model_copy(update={'test_type':new_type,'prompt':initial.prompt+' Answer briefly.'})
            monkeypatch.setattr(routes,'get_suite_generator',lambda *_: SimpleNamespace(generate=lambda *_:[replacement]))
            path=f"/api/v1/audits/{source['run_id']}/tests/{initial.test_id}"
            # An accepted probe keeps the stronger compatible-type guard.
            assert client.post(path+'/regenerate').status_code==422
            assert client.patch(path+'/review',json={'quality_status':'rejected'}).status_code==200
            revised=client.post(path+'/regenerate')
            assert revised.status_code==200,revised.text
            assert revised.json()['quality_status']=='pending'
            assert 'Evidence/type was replaced' in revised.json()['validation_notes']
            peer_tests=client.get(f"/api/v1/audits/{peer['run_id']}/test-review").json()['tests']
            assert any(test['prompt']==replacement.prompt and test['quality_status']=='pending' for test in peer_tests)
            assert client.post(f"/api/v1/audits/{peer['run_id']}/execute").status_code==409
        finally:
            app.dependency_overrides.clear()


def test_shared_suite_lock_blocks_peer_generation_edits_execution_and_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, peer = _conversation_and_experiment(client)
            suite_key = "suite:" + source["experiment_id"]
            with routes.audit_run_lock(suite_key):
                assert client.post(f"/api/v1/audits/{peer['run_id']}/generate-tests").status_code == 409
            generated = client.post(f"/api/v1/audits/{source['run_id']}/generate-tests").json()
            tid = generated[0]["test_id"]
            with routes.audit_run_lock(suite_key):
                assert client.patch(f"/api/v1/audits/{peer['run_id']}/tests/{tid}/review", json={"quality_status":"rejected"}).status_code == 409
                assert client.post(f"/api/v1/audits/{peer['run_id']}/tests/{tid}/regenerate").status_code == 409
                assert client.post(f"/api/v1/audits/{peer['run_id']}/execute").status_code == 409
                assert client.post(f"/api/v1/audits/{peer['run_id']}/retry").status_code == 409
            assert client.post(f"/api/v1/audits/{peer['run_id']}/execute").status_code == 200
        finally:
            app.dependency_overrides.clear()


def test_late_generator_reply_cannot_revive_a_cancelled_experiment(monkeypatch, tmp_path):
    from app.test_generator.rule_based import RuleBasedTestGenerator
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, peer = _conversation_and_experiment(client)
            class CancellingGenerator:
                def generate(self, memories, audit):
                    assert client.post(f"/api/v1/experiments/{source['experiment_id']}/cancel").status_code == 200
                    return RuleBasedTestGenerator().generate(memories, audit)
            monkeypatch.setattr(routes, "get_suite_generator", lambda *_: CancellingGenerator())
            result = client.post(f"/api/v1/audits/{source['run_id']}/generate-tests")
            assert result.status_code == 409
            for run in (source, peer):
                assert client.get(f"/api/v1/audits/{run['run_id']}").json()["status"] == "CANCELLED"
                assert client.get(f"/api/v1/audits/{run['run_id']}/tests").json() == []
        finally:
            app.dependency_overrides.clear()


def test_acceptance_and_execution_cannot_bypass_missing_source_memories(monkeypatch, tmp_path):
    from app.models import TestCaseModel, TargetResponseModel
    from sqlalchemy import select
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            source, _ = _conversation_and_experiment(client)
            run_id = source['run_id']
            generated = client.post(f'/api/v1/audits/{run_id}/generate-tests').json()
            test_id = generated[0]['test_id']
            session_generator = app.dependency_overrides[get_db]()
            db = next(session_generator)
            try:
                row = db.get(TestCaseModel, test_id)
                row.supporting_memory_ids = ['M_missing_source']
                row.quality_status = 'pending'
                db.commit()
                refused = client.patch(f'/api/v1/audits/{run_id}/tests/{test_id}/review', json={'quality_status':'accepted'})
                assert refused.status_code == 422
                assert 'Review the source memories' in refused.json()['detail']
                db.refresh(row)
                assert row.quality_status == 'pending'
                # Legacy accepted records must also be checked before a target call.
                row.quality_status = 'accepted'
                db.commit()
                blocked = client.post(f'/api/v1/audits/{run_id}/execute')
                assert blocked.status_code == 409
                assert 'supporting memories' in blocked.json()['detail']
                assert db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)).all() == []
            finally:
                session_generator.close()
        finally:
            app.dependency_overrides.clear()


def test_llm_replacement_receives_current_quality_failure_and_keeps_peer_review_pending(monkeypatch,tmp_path):
    from app.models import TestCaseModel
    from app.schemas import TestCase
    from app.test_generator.llm_generator import LLMTestGenerator
    monkeypatch.setenv('PIPELINE_PROVIDER','rule_based')
    with _client(tmp_path) as client:
        try:
            source,peer = _conversation_and_experiment(client)
            initial = TestCase.model_validate(client.post(f"/api/v1/audits/{source['run_id']}/generate-tests").json()[0])
            db = next(app.dependency_overrides[get_db]())
            try:
                row = db.get(TestCaseModel,initial.test_id)
                row.prompt = "What is the user's recorded stored information?"
                db.commit()
            finally:
                db.close()
            captured = {}
            def replacement(self,memories,audit,generation_context=None):
                captured['context'] = generation_context
                return [initial.model_copy(update={'prompt':initial.prompt+' Answer briefly.'})]
            monkeypatch.setattr(LLMTestGenerator,'generate',replacement)
            monkeypatch.setattr(routes,'get_suite_generator',lambda *_:LLMTestGenerator(client=object()))
            path = f"/api/v1/audits/{source['run_id']}/tests/{initial.test_id}"
            result = client.post(path+'/regenerate')
            assert result.status_code == 200,result.text
            assert 'does not identify the fact or event' in captured['context']
            assert 'Do not repeat this question' in captured['context']
            assert result.json()['quality_status'] == 'pending'
            assert client.post(f"/api/v1/audits/{peer['run_id']}/execute").status_code == 409
        finally:
            app.dependency_overrides.clear()


def test_recovery_plan_reports_live_locks_without_starting_or_blocking_recovery(monkeypatch,tmp_path):
    monkeypatch.setenv('PIPELINE_PROVIDER','rule_based')
    with _client(tmp_path) as client:
        try:
            source,_ = _conversation_and_experiment(client)
            run_id = source['run_id']
            initial = client.get(f'/api/v1/audits/{run_id}/retry-plan').json()
            assert initial['busy'] is False
            assert initial['status'] == source['status']
            assert initial['completed_at'] is None
            with routes.audit_run_lock(run_id):
                current = client.get(f'/api/v1/audits/{run_id}/retry-plan').json()
                assert current['busy'] is True
                assert current['busy_reason'] == 'this_run'
                assert current['retryable'] == initial['retryable']
            assert client.get(f'/api/v1/audits/{run_id}/tests').json() == []
            assert client.get(f'/api/v1/audits/{run_id}/retry-plan').json()['busy'] is False
            assert client.post(f'/api/v1/audits/{run_id}/retry').status_code == 200
            assert client.post(f'/api/v1/audits/{run_id}/retry').status_code == 200
            assert client.post(f'/api/v1/audits/{run_id}/retry').status_code == 200
            finished = client.get(f'/api/v1/audits/{run_id}/retry-plan').json()
            assert finished['status'] == 'COMPLETED'
            assert finished['completed_at']
            assert finished['retryable'] is False
        finally:
            app.dependency_overrides.clear()
