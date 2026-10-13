"""Access tests use synthetic credentials and an isolated database only."""
from datetime import timedelta
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.api import access_routes
from app.database.session import Base, get_db
from app.models import ConversationModel, OperatorSessionModel
from app.security import access

PASSWORD = 'synthetic-test-password-only'
ENCODED = access.password_hash(PASSWORD)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('AUDITOR_ACCESS_MODE', 'protected')
    monkeypatch.setenv('AUDITOR_OPERATOR_PASSWORD_HASH', ENCODED)
    monkeypatch.setenv('AUDITOR_COOKIE_SECURE', 'false')
    monkeypatch.setenv('AUDITOR_ALLOWED_ORIGINS', 'http://localhost:5173')
    monkeypatch.setattr(access, 'LOGIN_LIMITER', access.LoginLimiter())
    engine=create_engine(f"sqlite:///{tmp_path/'access.sqlite'}",connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    monkeypatch.setattr(access,'SessionLocal',sessions)
    monkeypatch.setattr(access_routes,'SessionLocal',sessions)
    def database():
        with sessions() as db:yield db
    app.dependency_overrides[get_db]=database
    with TestClient(app) as browser:
        browser.sessions=sessions
        yield browser
    app.dependency_overrides.clear()
    engine.dispose()


def sign_in(client):
    response=client.post('/api/v1/access/sign-in',json={'password':PASSWORD},headers={'Origin':'http://localhost:5173'})
    assert response.status_code==200,response.text
    return response.json()['csrf_token']


@pytest.mark.parametrize('path',['/api/v1/audits','/api/v1/conversations/not-known/export','/api/v1/experiments/not-known/artifact.zip','/api/v1/audits/not-known/results','/api/v1/auditor-quality','/api/v1/docs','/api/v1/openapi.json'])
def test_private_reads_are_denied_before_route_details_are_visible(client,path):
    response=client.get(path)
    assert response.status_code==401
    assert 'not-known' not in response.text


def test_unauthenticated_body_is_not_parsed_and_cannot_create_data(client):
    response=client.post('/api/v1/conversations',content='not even JSON',headers={'Content-Type':'application/json'})
    assert response.status_code==401
    with client.sessions() as db:assert db.query(ConversationModel).count()==0


def test_login_never_exposes_password_bearer_or_hash_in_json_and_rotates_session(client):
    csrf=sign_in(client)
    old=client.cookies.get(access.COOKIE_NAME)
    status=client.get('/api/v1/access/status')
    assert status.json()['authenticated']
    assert status.json()['csrf_token']==csrf
    assert all(value not in status.text for value in [PASSWORD,ENCODED,old])
    sign_in(client)
    assert client.cookies.get(access.COOKIE_NAME)!=old
    with client.sessions() as db:
        sessions=db.scalars(select(OperatorSessionModel)).all()
        assert len(sessions)==1
        assert sessions[0].token_digest!=client.cookies.get(access.COOKIE_NAME)
        assert sessions[0].token_digest==access.token_digest(client.cookies.get(access.COOKIE_NAME))


def test_writes_require_csrf_and_reject_foreign_origin_even_with_valid_token(client):
    csrf=sign_in(client)
    body={'authorised':True,'pasted_text':'[User] I prefer Ruby.'}
    assert client.post('/api/v1/conversations',json=body).status_code==403
    assert client.post('/api/v1/conversations',json=body,headers={'X-CSRF-Token':csrf,'Origin':'https://untrusted.example'}).status_code==403
    assert client.post('/api/v1/conversations',json=body,headers={'X-CSRF-Token':csrf,'Origin':'http://localhost:5173'}).status_code==201
    assert client.get('/api/v1/audits').headers['cache-control']=='no-store'


def test_logout_revokes_server_side_token_not_just_browser_cookie(client):
    csrf=sign_in(client)
    token=client.cookies.get(access.COOKIE_NAME)
    response=client.post('/api/v1/access/sign-out',headers={'X-CSRF-Token':csrf})
    assert response.status_code==200
    assert 'Max-Age=0' in response.headers['set-cookie']
    assert client.get('/api/v1/audits',headers={'Cookie':f'{access.COOKIE_NAME}={token}'}).status_code==401
    assert not client.get('/api/v1/access/status').json()['authenticated']


def test_expiry_and_credential_rotation_revoke_existing_session(client,monkeypatch):
    sign_in(client)
    with client.sessions() as db:
        session=db.scalar(select(OperatorSessionModel))
        session.expires_at=access.now_utc()-timedelta(seconds=1);db.commit()
    assert client.get('/api/v1/audits').status_code==401
    sign_in(client)
    monkeypatch.setenv('AUDITOR_OPERATOR_PASSWORD_HASH',access.password_hash('another-test-password-only'))
    assert client.get('/api/v1/audits').status_code==401


def test_bruteforce_guard_returns_retry_after_and_errors_never_echo_password(client):
    for _ in range(6):
        response=client.post('/api/v1/access/sign-in',json={'password':'wrong-test-value'})
        assert response.status_code==401
        assert 'wrong-test-value' not in response.text
    response=client.post('/api/v1/access/sign-in',json={'password':PASSWORD})
    assert response.status_code==429
    assert response.headers['retry-after']=='900'
    invalid='secret-test-value'*100
    response=client.post('/api/v1/access/sign-in',json={'password':invalid})
    assert response.status_code==422
    assert invalid not in response.text


def test_cookie_flags_and_missing_configuration_fail_closed(client,monkeypatch):
    monkeypatch.setenv('AUDITOR_COOKIE_SECURE','true')
    response=client.post('/api/v1/access/sign-in',json={'password':PASSWORD})
    cookie=response.headers['set-cookie']
    assert all(flag in cookie for flag in ['HttpOnly','Secure','SameSite=strict','Path=/api/v1'])
    monkeypatch.delenv('AUDITOR_OPERATOR_PASSWORD_HASH')
    response=client.get('/api/v1/audits')
    assert response.status_code==503
    assert 'pbkdf2' not in response.text


def test_insecure_remote_cookie_setting_is_rejected(monkeypatch):
    monkeypatch.setenv('AUDITOR_ACCESS_MODE','protected')
    monkeypatch.setenv('AUDITOR_OPERATOR_PASSWORD_HASH',ENCODED)
    monkeypatch.setenv('AUDITOR_ALLOWED_ORIGINS','https://workspace.example')
    monkeypatch.setenv('AUDITOR_COOKIE_SECURE','false')
    with pytest.raises(ValueError,match='secure cookies'):access.AccessSettings.read()


def test_untrusted_host_and_local_cross_site_writes_are_denied(client,monkeypatch):
    assert client.get('/api/v1/access/status',headers={'Host':'untrusted.example'}).status_code==400
    monkeypatch.setenv('AUDITOR_ACCESS_MODE','local')
    assert client.post('/api/v1/conversations',json={'authorised':True,'pasted_text':'[User] I prefer Ruby.'},headers={'Origin':'https://untrusted.example'}).status_code==403


def test_remote_plain_http_origin_and_invalid_cookie_flag_fail_closed(monkeypatch):
    monkeypatch.setenv('AUDITOR_ACCESS_MODE','protected')
    monkeypatch.setenv('AUDITOR_OPERATOR_PASSWORD_HASH',ENCODED)
    monkeypatch.setenv('AUDITOR_ALLOWED_ORIGINS','http://workspace.example')
    monkeypatch.setenv('AUDITOR_COOKIE_SECURE','true')
    with pytest.raises(ValueError,match='HTTPS'):access.AccessSettings.read()
    monkeypatch.setenv('AUDITOR_ALLOWED_ORIGINS','http://localhost:5173')
    monkeypatch.setenv('AUDITOR_COOKIE_SECURE','typo')
    with pytest.raises(ValueError,match='true or false'):access.AccessSettings.read()
