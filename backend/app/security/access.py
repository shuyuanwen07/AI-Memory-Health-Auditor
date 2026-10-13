"""Revocable opaque operator sessions; passwords and bearer tokens stay off logs."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import secrets
from threading import Lock
import time
from urllib.parse import urlparse

from fastapi import Request
from sqlalchemy import delete
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.database.session import SessionLocal
from app.models import OperatorSessionModel

COOKIE_NAME = 'auditor_operator'
DEFAULT_ITERATIONS = 600_000
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
PUBLIC_PATHS = {'/api/v1/access/status', '/api/v1/access/sign-in'}


def now_utc():
    return datetime.now(timezone.utc)


def password_hash(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, DEFAULT_ITERATIONS)
    return f'pbkdf2_sha256${DEFAULT_ITERATIONS}${salt.hex()}${digest.hex()}'


def parse_password_hash(encoded: str):
    algorithm, iterations_text, salt_text, digest_text = encoded.split('$')
    if not iterations_text.isascii() or not iterations_text.isdigit():
        raise ValueError('Invalid password configuration.')
    iterations = int(iterations_text)
    salt, digest = bytes.fromhex(salt_text), bytes.fromhex(digest_text)
    if algorithm != 'pbkdf2_sha256' or not DEFAULT_ITERATIONS <= iterations <= 2_000_000 or len(salt) < 16 or len(digest) != 32:
        raise ValueError('Invalid password configuration.')
    return iterations, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    iterations, salt, expected = parse_password_hash(encoded)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return hmac.compare_digest(digest, expected)


@dataclass(frozen=True)
class AccessSettings:
    mode: str
    password: str
    origins: tuple[str, ...]
    secure_cookie: bool
    lifetime_seconds: int

    @classmethod
    def read(cls):
        mode = os.getenv('AUDITOR_ACCESS_MODE', 'local').strip()
        if mode not in {'local', 'protected'}:
            raise ValueError('Access mode must be local or protected.')
        origins = tuple(item.strip() for item in os.getenv('AUDITOR_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if item.strip())
        if not origins or any(urlparse(origin).scheme not in {'http', 'https'} or not urlparse(origin).hostname or urlparse(origin).path or urlparse(origin).query or urlparse(origin).fragment for origin in origins):
            raise ValueError('Explicit browser origins are required.')
        secure_value = os.getenv('AUDITOR_COOKIE_SECURE', 'true').lower()
        if secure_value not in {'true', 'false'}:
            raise ValueError('Cookie security must be true or false.')
        secure = secure_value == 'true'
        lifetime = int(os.getenv('AUDITOR_SESSION_SECONDS', '14400'))
        if not 60 <= lifetime <= 86400:
            raise ValueError('Session lifetime must be between one minute and one day.')
        encoded = os.getenv('AUDITOR_OPERATOR_PASSWORD_HASH', '')
        if mode == 'protected':
            parse_password_hash(encoded)
            if any(urlparse(origin).scheme != 'https' and urlparse(origin).hostname not in {'localhost', '127.0.0.1', '::1', 'testserver'} for origin in origins):
                raise ValueError('Remote protected browser origins require HTTPS.')
            if not secure and any(urlparse(origin).hostname not in {'localhost', '127.0.0.1', '::1', 'testserver'} for origin in origins):
                raise ValueError('Remote protected access requires secure cookies.')
        return cls(mode, encoded, origins, secure, lifetime)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode('ascii'), b'auditor-csrf-v1', hashlib.sha256).hexdigest()


def current_session(token: str | None, settings: AccessSettings):
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    with SessionLocal() as db:
        session = db.get(OperatorSessionModel, token_digest(token))
        if session is None:
            return None
        expiration = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
        created = session.created_at.replace(tzinfo=timezone.utc) if session.created_at.tzinfo is None else session.created_at
        expiration = min(expiration, created+timedelta(seconds=settings.lifetime_seconds))
        if expiration <= now_utc() or session.credential_fingerprint != token_digest(settings.password):
            db.delete(session)
            db.commit()
            return None
        return expiration


def create_session(settings: AccessSettings):
    token = secrets.token_urlsafe(32)
    now = now_utc()
    expiration = now + timedelta(seconds=settings.lifetime_seconds)
    with SessionLocal() as db:
        db.execute(delete(OperatorSessionModel).where(OperatorSessionModel.expires_at <= now))
        db.add(OperatorSessionModel(token_digest=token_digest(token), credential_fingerprint=token_digest(settings.password), created_at=now, expires_at=expiration))
        db.commit()
    return token, expiration


class LoginLimiter:
    """Bounded failure counter for the documented single API worker."""
    def __init__(self):
        self.failures = {}
        self.lock = Lock()
        self.window = 900
        self.limit = 6

    def blocked(self, address):
        now = time.monotonic()
        with self.lock:
            self.failures = {key: value for key, value in self.failures.items() if value[0] > now-self.window}
            value = self.failures.get(address)
            if value is None and len(self.failures) >= 2048:
                value = self.failures.get('overflow')
            return bool(value and value[1] >= self.limit)

    def failed(self, address):
        with self.lock:
            # One overflow bucket prevents spoofed/distributed addresses from
            # turning the in-process guard into an unbounded memory store.
            if address not in self.failures and len(self.failures) >= 2048:
                address = 'overflow'
            start, count = self.failures.get(address, (time.monotonic(), 0))
            self.failures[address] = (start, count+1)

    def succeeded(self, address):
        with self.lock:
            self.failures.pop(address, None)


LOGIN_LIMITER = LoginLimiter()


class OperatorAccessMiddleware:
    """Authenticate before JSON parsing or any business route can run."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        try:
            settings = AccessSettings.read()
        except (ValueError, TypeError):
            await JSONResponse({'detail': 'Operator access is not configured correctly. Contact the workspace owner.'}, status_code=503)(scope, receive, send)
            return
        request = Request(scope)
        origin = request.headers.get('origin')
        if request.method not in SAFE_METHODS and origin and origin not in settings.origins:
            await JSONResponse({'detail': 'This browser origin is not authorised.'}, status_code=403)(scope, receive, send)
            return
        if settings.mode == 'protected' and request.method != 'OPTIONS' and request.url.path not in PUBLIC_PATHS:
            token = request.cookies.get(COOKIE_NAME)
            expires = await run_in_threadpool(current_session, token, settings)
            if expires is None:
                await JSONResponse({'detail': 'Your workspace session has ended. Sign in to continue.'}, status_code=401)(scope, receive, send)
                return
            if request.method not in SAFE_METHODS and not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode('utf-8'), csrf_token(token).encode('ascii')):
                await JSONResponse({'detail': 'Refresh the workspace and retry this action.'}, status_code=403)(scope, receive, send)
                return
        async def private_send(message):
            if message['type'] == 'http.response.start':
                headers = [(key, value) for key, value in message.get('headers', []) if key.lower() != b'cache-control']
                message = {**message, 'headers': headers + [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')]}
            await send(message)
        await self.app(scope, receive, private_send)
