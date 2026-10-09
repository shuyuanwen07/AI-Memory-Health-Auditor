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
def test_postgresql_migrated_api_path():
    _require_isolated_postgres()

    from app.main import app

    with TestClient(app) as client:
        payload = {
            "authorised": True,
            "messages": [
                {"message_id": "export-message-1", "role": "user", "content": "I used MySQL before.", "timestamp": datetime.now(timezone.utc).isoformat()},
                {"message_id": "export-message-2", "role": "user", "content": "The backend now uses PostgreSQL.", "timestamp": datetime.now(timezone.utc).isoformat()},
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
            assert client.post(f"/api/v1/audits/{run_id}/generate-tests").status_code == 200
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
