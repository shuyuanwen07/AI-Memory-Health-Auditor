"""A migrated PostgreSQL path kept separate from fast SQLite unit tests."""

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url


def _require_isolated_postgres():
    value = os.getenv("DATABASE_URL", "")
    if not value.startswith("postgresql"):
        pytest.skip("PostgreSQL integration requires an isolated migrated test database.")
    database = make_url(value).database or ""
    if not database.endswith(("_ci", "_test")):
        pytest.skip("Refusing to run integration fixtures against the application database; use a database ending _ci or _test.")


@pytest.mark.postgres
def test_postgresql_migrated_benchmark_plan_metadata_survives_session_restart():
    """Exercise migration 0038's real JSON columns, without benchmark sources."""
    _require_isolated_postgres()
    from uuid import uuid4
    from sqlalchemy.orm import Session
    from app.database.session import engine
    from app.models.entities import BenchmarkPlanModel

    plan_id = 'BPLAN' + uuid4().hex
    protocol = {'schema_version': 'synthetic-storage-probe',
                'source_sha256': 'a' * 64, 'trials': [{'trial_id': 'repeat-1'}]}
    executions = {'repeat-1': {'status': 'FAILED', 'evidence_sha256': None}}
    try:
        with Session(engine) as writer:
            writer.add(BenchmarkPlanModel(id=plan_id, fingerprint_sha256='b' * 64,
                                          protocol=protocol, executions=executions))
            writer.commit()
        with Session(engine) as reader:
            saved = reader.get(BenchmarkPlanModel, plan_id)
            assert saved is not None
            assert saved.protocol == protocol
            assert saved.executions == executions
            assert saved.fingerprint_sha256 == 'b' * 64
            assert saved.created_at is not None
            # Full replacement is how the service persists execution receipts.
            saved.executions = {**saved.executions,
                                'repeat-2': {'status': 'COMPLETED', 'evidence_sha256': 'c' * 64}}
            reader.commit()
        with Session(engine) as observer:
            saved = observer.get(BenchmarkPlanModel, plan_id)
            assert saved.executions['repeat-1']['status'] == 'FAILED'
            assert saved.executions['repeat-2']['evidence_sha256'] == 'c' * 64
    finally:
        with Session(engine) as cleanup:
            saved = cleanup.get(BenchmarkPlanModel, plan_id)
            if saved is not None:
                cleanup.delete(saved)
                cleanup.commit()


@pytest.mark.postgres
def test_postgresql_comparison_plan_export_and_confirmed_erasure():
    _require_isolated_postgres()
    from uuid import uuid4
    from app.main import app
    with TestClient(app) as client:
        cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':[{'role':'user','content':'I prefer Rust.'}]}).json()['conversation_id']
        try:
            memories=client.post(f'/api/v1/conversations/{cid}/extract',json={'provider':'rule_based'}).json()
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':[m['memory_id'] for m in memories]})
            source=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based',
                'evaluator_provider':'rule_based','target_configuration':'strong','target_memory_writer':'rule_based'}).json()['run_id']
            path=f'/api/v1/audits/{source}'
            client.post(path+'/generate-tests');client.post(path+'/execute');client.post(path+'/evaluate')
            a=client.post('/api/v1/assessor-comparisons',json={'creation_request_key':uuid4().hex,'source_run_id':source,
                'assessors':[{'evaluator_provider':'rule_based'},{'evaluator_provider':'openrouter','evaluator_model':'fixed-model'}]})
            g=client.post('/api/v1/generator-comparisons',json={'creation_request_key':uuid4().hex,'source_run_id':source,
                'generators':[{'provider':'rule_based'},{'provider':'openrouter','model':'fixed-model'}]})
            assert a.status_code==201,a.text
            assert g.status_code==201,g.text
            extraction=client.post('/api/v1/extraction-comparisons',json={'creation_request_key':uuid4().hex,'source_run_id':source,
                'extractors':[{'provider':'rule_based'},{'provider':'openrouter','model':'fixed-model'}]})
            assert extraction.status_code==201,extraction.text
            extraction_id=extraction.json()['comparison_id']
            extracted=client.post(f'/api/v1/extraction-comparisons/{extraction_id}/entries/0/extract')
            assert extracted.status_code==200,extracted.text
            assert extracted.json()['entries'][0]['checks']['fact_coverage_percent']==100
            exported=client.get(f'/api/v1/conversations/{cid}/export').json()
            assert exported['extraction_comparisons'][0]['id']==extraction_id
            assert len(exported['assessor_comparisons'])==len(exported['generator_comparisons'])==1
            deleted=client.request('DELETE',f'/api/v1/conversations/{cid}',json={'confirmation':cid})
            assert deleted.status_code==200,deleted.text
            assert client.get(f"/api/v1/assessor-comparisons/{a.json()['comparison_id']}").status_code==404
            assert client.get(f"/api/v1/generator-comparisons/{g.json()['comparison_id']}").status_code==404
        finally:
            client.request('DELETE',f'/api/v1/conversations/{cid}',json={'confirmation':cid})


@pytest.mark.postgres
def test_postgresql_migrated_api_path(monkeypatch):
    _require_isolated_postgres()
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")

    from app.main import app

    with TestClient(app) as client:
        payload = {
            "authorised": True,
            "messages": [
                {"message_id": "export-message-1", "role": "user", "content": "The backend used MySQL before.", "timestamp": datetime.now(timezone.utc).isoformat()},
                {"message_id": "export-message-2", "role": "user", "content": "The backend now uses PostgreSQL instead of MySQL.", "timestamp": datetime.now(timezone.utc).isoformat()},
                {"message_id": "export-message-3", "role": "user", "content": "I prefer Python. This assignment requires Java.", "timestamp": datetime.now(timezone.utc).isoformat()},
            ],
        }
        created = client.post("/api/v1/conversations", json=payload)
        assert created.status_code == 201, created.text
        conversation_id = created.json()["conversation_id"]
        second_conversation_id = None
        try:
            extracted = client.post(f"/api/v1/conversations/{conversation_id}/extract")
            assert extracted.status_code == 200, extracted.text
            related = next(item for item in extracted.json() if item['relationships'])
            edited = client.patch(f"/api/v1/memories/{related['memory_id']}", json={
                'canonical_value': 'The backend currently uses PostgreSQL.',
                'relationships': related['relationships'],
                'status': 'edited',
            })
            assert edited.status_code == 200, edited.text
            assert [(r['type'], r['target_memory_id']) for r in edited.json()['relationships']] == [
                (r['type'], r['target_memory_id']) for r in related['relationships']
            ]
            # The PostgreSQL integration path must also prove that two normal
            # exports can reuse extractor-local labels such as M001.
            second = client.post("/api/v1/conversations", json=payload)
            assert second.status_code == 201, second.text
            second_conversation_id = second.json()["conversation_id"]
            second_extracted = client.post(f"/api/v1/conversations/{second_conversation_id}/extract")
            assert second_extracted.status_code == 200, second_extracted.text
            assert {item["memory_id"] for item in extracted.json()}.isdisjoint(
                {item["memory_id"] for item in second_extracted.json()}
            )
            confirmed = client.post(f"/api/v1/conversations/{conversation_id}/confirm-ground-truth", json={
                "confirmed_memory_ids": [memory["memory_id"] for memory in extracted.json()],
            })
            assert confirmed.status_code == 200, confirmed.text
            audit = client.post("/api/v1/audits", json={
                "conversation_id": conversation_id, "target_configuration": "strong", "provider": "rule_based", "test_budget": 4,
            })
            assert audit.status_code == 201, audit.text
            run_id = audit.json()["run_id"]
            generated = client.post(f"/api/v1/audits/{run_id}/generate-tests")
            assert generated.status_code == 200, generated.text
            assert client.post(f"/api/v1/audits/{run_id}/execute").status_code == 200
            assert client.post(f"/api/v1/audits/{run_id}/evaluate").status_code == 200
            assert client.get(f"/api/v1/audits/{run_id}/results").status_code == 200
        finally:
            if second_conversation_id:
                deleted_second = client.request("DELETE", f"/api/v1/conversations/{second_conversation_id}", json={"confirmation": second_conversation_id})
                assert deleted_second.status_code == 200, deleted_second.text
            deleted = client.request("DELETE", f"/api/v1/conversations/{conversation_id}", json={"confirmation": conversation_id})
            assert deleted.status_code == 200, deleted.text

@pytest.mark.postgres
def test_postgresql_profiles_paired_probes_and_replay_identity(monkeypatch):
    _require_isolated_postgres()
    monkeypatch.setenv('PIPELINE_PROVIDER', 'rule_based')
    monkeypatch.setenv('EVALUATOR_PROVIDER', 'rule_based')
    from app.main import app
    from app.database.session import SessionLocal
    from test_quality_workflows import test_paired_grouping_and_repair_preserves_exact_questions
    with TestClient(app) as client:
        client.sessions = SessionLocal
        test_paired_grouping_and_repair_preserves_exact_questions(client)


@pytest.mark.postgres
def test_postgresql_operator_session_is_revocable_and_timezone_aware(monkeypatch):
    _require_isolated_postgres()
    from sqlalchemy import select
    from app.database.session import SessionLocal
    from app.models import OperatorSessionModel
    from app.security import access
    from app.main import app
    monkeypatch.setenv('AUDITOR_ACCESS_MODE','protected')
    monkeypatch.setenv('AUDITOR_OPERATOR_PASSWORD_HASH',access.password_hash('postgres-fixture-password-only'))
    monkeypatch.setenv('AUDITOR_COOKIE_SECURE','false')
    with TestClient(app) as client:
        response=client.post('/api/v1/access/sign-in',json={'password':'postgres-fixture-password-only'})
        assert response.status_code==200,response.text
        csrf=response.json()['csrf_token']
        token=client.cookies.get(access.COOKIE_NAME)
        try:
            with SessionLocal() as db:
                row=db.scalar(select(OperatorSessionModel).where(OperatorSessionModel.token_digest==access.token_digest(token)))
                assert row.expires_at.tzinfo is not None
                assert row.token_digest!=token
            assert client.get('/api/v1/audits').status_code==200
            assert client.post('/api/v1/access/sign-out',headers={'X-CSRF-Token':csrf}).status_code==200
            assert client.get('/api/v1/audits',headers={'Cookie':f'{access.COOKIE_NAME}={token}'}).status_code==401
        finally:
            with SessionLocal() as db:
                row=db.get(OperatorSessionModel,access.token_digest(token))
                if row:db.delete(row);db.commit()


@pytest.mark.postgres
def test_postgresql_concurrent_creation_reuses_exact_identity(monkeypatch):
    """Force both requests to miss the key lookup before their inserts race."""
    _require_isolated_postgres()
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from uuid import uuid4
    from app.api import routes
    from app.main import app
    monkeypatch.setenv('PIPELINE_PROVIDER', 'rule_based')
    monkeypatch.setenv('EVALUATOR_PROVIDER', 'rule_based')
    cid = None
    try:
        with TestClient(app) as setup:
            response = setup.post('/api/v1/conversations', json={'authorised': True, 'pasted_text': '[User] I live in Albury.'})
            assert response.status_code == 201, response.text
            cid = response.json()['conversation_id']
            memories = setup.post(f'/api/v1/conversations/{cid}/extract').json()
            assert setup.post(f'/api/v1/conversations/{cid}/confirm-ground-truth', json={'confirmed_memory_ids': [m['memory_id'] for m in memories]}).status_code == 200
        original_lookup = routes.existing_creation
        for endpoint, payload, identity in [
            ('experiments', {'conversation_id': cid, 'label': 'Concurrent recovery'}, 'experiment_id'),
            ('audits', {'conversation_id': cid, 'target_configuration': 'strong'}, 'run_id'),
        ]:
            key = uuid4().hex
            body = {**payload, 'creation_request_key': key}
            barrier = Barrier(2)
            guard = Lock()
            checked = [0]
            def synchronised_lookup(db, model, request):
                row = original_lookup(db, model, request)
                should_wait = False
                with guard:
                    if request.creation_request_key == key and checked[0] < 2:
                        checked[0] += 1
                        should_wait = True
                if should_wait:
                    assert row is None
                    barrier.wait(timeout=10)
                return row
            monkeypatch.setattr(routes, 'existing_creation', synchronised_lookup)
            def create():
                with TestClient(app) as client:
                    return client.post(f'/api/v1/{endpoint}', json=body)
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: create(), range(2)))
            assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
            assert responses[0].json()[identity] == responses[1].json()[identity]
            monkeypatch.setattr(routes, 'existing_creation', original_lookup)
    finally:
        if cid:
            with TestClient(app) as cleanup:
                assert cleanup.request('DELETE', f'/api/v1/conversations/{cid}', json={'confirmation': cid}).status_code == 200


@pytest.mark.postgres
def test_postgresql_conversation_retry_and_extraction_row_lock(monkeypatch):
    _require_isolated_postgres()
    from uuid import uuid4
    from sqlalchemy import select
    from app.main import app
    from app.api import routes
    from app.models import ConversationModel
    from app.database.session import SessionLocal
    class EmptyExtractor:
        VERSION = 'postgres-recovery-check'
        calls = 0
        def extract(self, conversation):
            self.calls += 1
            return []
    extractor = EmptyExtractor()
    monkeypatch.setattr(routes, 'get_memory_extractor', lambda *_: extractor)
    cid = None
    with TestClient(app) as client:
        try:
            body = {'authorised': True, 'pasted_text': '[User] Disposable recovery transaction check.', 'creation_request_key': uuid4().hex}
            original = client.post('/api/v1/conversations', json=body)
            assert original.status_code == 201
            cid = original.json()['conversation_id']
            assert client.post('/api/v1/conversations', json=body).json()['conversation_id'] == cid
            assert client.post('/api/v1/conversations', json={**body, 'pasted_text': 'Changed'}).status_code == 409
            # Independent DB session simulates a peer worker holding the extraction row.
            with SessionLocal() as peer:
                peer.scalar(select(ConversationModel).where(ConversationModel.id == cid).with_for_update())
                busy = client.post(f'/api/v1/conversations/{cid}/extract', json={'provider': 'rule_based'})
                assert busy.status_code == 409 and 'Memory extraction is still running' in busy.json()['detail']
                assert extractor.calls == 0
                peer.rollback()
            assert client.post(f'/api/v1/conversations/{cid}/extract', json={'provider': 'rule_based'}).json() == []
            assert client.post(f'/api/v1/conversations/{cid}/extract', json={'provider': 'rule_based'}).json() == []
            assert extractor.calls == 1
        finally:
            if cid:
                assert client.request('DELETE', f'/api/v1/conversations/{cid}', json={'confirmation': cid}).status_code == 200

@pytest.mark.postgres
def test_postgresql_stage_lock_survives_commits_and_blocks_another_process():
    _require_isolated_postgres()
    import subprocess
    import sys
    from uuid import uuid4
    from sqlalchemy.orm import Session
    from app.database.session import engine
    from app.services.stage_lock import database_stage_lock, database_stage_busy

    scope = 'integration-stage:' + uuid4().hex
    # A fresh interpreter has no shared Python lock dictionary with this worker.
    worker = '''
import sys
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.session import engine
from app.services.stage_lock import database_stage_lock
with Session(engine) as db:
    try:
        with database_stage_lock(db, sys.argv[1], 'Please wait for the running stage.'):
            print('acquired')
    except HTTPException as exc:
        assert exc.status_code == 409
        print('busy')
'''
    def other_worker():
        result = subprocess.run([sys.executable, '-c', worker, scope], capture_output=True, text=True, timeout=20, check=True)
        return result.stdout.strip()

    with Session(engine) as db, Session(engine) as observer:
        with pytest.raises(RuntimeError, match='interrupted stage'):
            with database_stage_lock(db, scope, 'Stage is running.'):
                db.commit()  # Persisting an answer must not let a duplicate in.
                assert database_stage_busy(observer, scope)
                assert other_worker() == 'busy'
                with database_stage_lock(observer, scope + ':different', 'Stage is running.'):
                    pass
                raise RuntimeError('interrupted stage')
        assert not database_stage_busy(observer, scope)
        assert other_worker() == 'acquired'
