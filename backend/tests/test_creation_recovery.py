"""Lost creation responses reuse identity; altered retry payloads never reuse it."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, ExperimentModel


def test_lost_response_creation_replay_and_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPELINE_PROVIDER', 'rule_based')
    monkeypatch.setenv('EVALUATOR_PROVIDER', 'rule_based')
    engine = create_engine(f'sqlite:///{tmp_path / "creation.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def db_override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            cid = client.post('/api/v1/conversations', json={'authorised': True, 'pasted_text': '[User] I live in Albury.'}).json()['conversation_id']
            memories = client.post(f'/api/v1/conversations/{cid}/extract').json()
            assert client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth', json={'confirmed_memory_ids': [m['memory_id'] for m in memories]}).status_code == 200
            exp = {'conversation_id': cid, 'label': 'Frozen creation', 'creation_request_key': 'experiment-request-0001'}
            first = client.post('/api/v1/experiments', json=exp)
            assert first.status_code == 201
            eid = first.json()['experiment_id']
            assert client.post('/api/v1/experiments', json=exp).json()['experiment_id'] == eid
            assert client.post('/api/v1/experiments', json={**exp, 'label': 'Changed'}).status_code == 409
            body = {'conversation_id': cid, 'experiment_id': eid, 'target_configuration': 'strong', 'creation_request_key': 'audit-request-0000001'}
            original = client.post('/api/v1/audits', json=body)
            assert original.status_code == 201
            rid = original.json()['run_id']
            assert client.post('/api/v1/audits', json=body).json()['run_id'] == rid
            assert client.post('/api/v1/audits', json={**body, 'target_memory_capacity': 1}).status_code == 409
            # Intentional repetitions use separate keys even with identical settings.
            peer = client.post('/api/v1/audits', json={**body, 'creation_request_key': 'audit-request-0000002'})
            assert peer.status_code == 201 and peer.json()['run_id'] != rid
            assert client.post(f'/api/v1/audits/{rid}/generate-tests').status_code == 200
            # Replay returns the committed record after membership freezes.
            replay = client.post('/api/v1/audits', json=body)
            assert replay.status_code == 201 and replay.json()['status'] == 'TESTS_GENERATED'
            assert client.post('/api/v1/experiments', json=exp).json()['experiment_id'] == eid
            with factory() as db:
                assert db.scalar(select(func.count()).select_from(ExperimentModel)) == 1
                assert db.scalar(select(func.count()).select_from(AuditRunModel)) == 2
            assert 'creation_request_key' not in replay.json()
            assert client.post('/api/v1/audits', json={**body, 'creation_request_key': 'bad'}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
