"""Workspace access; provider API keys are never login credentials."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from starlette.responses import JSONResponse
from app.database.session import SessionLocal
from app.models import OperatorSessionModel
from app.security import access

access_router = APIRouter(prefix='/api/v1/access', tags=['workspace-access'])


class SignInRequest(BaseModel):
    password: SecretStr = Field(min_length=1, max_length=1024)


def status_payload(request: Request, settings: access.AccessSettings):
    token = request.cookies.get(access.COOKIE_NAME)
    expiration = access.current_session(token, settings) if settings.mode == 'protected' else None
    return {'mode': settings.mode, 'requires_sign_in': settings.mode == 'protected',
            'authenticated': settings.mode == 'local' or expiration is not None,
            'expires_at': expiration.isoformat() if expiration else None,
            'expires_in_seconds': max(0, int((expiration-access.now_utc()).total_seconds())) if expiration else None,
            'csrf_token': access.csrf_token(token) if expiration else None}


@access_router.get('/status')
def access_status(request: Request):
    return JSONResponse(status_payload(request, access.AccessSettings.read()), headers={'Cache-Control': 'no-store'})


@access_router.post('/sign-in')
def sign_in(payload: SignInRequest, request: Request):
    settings = access.AccessSettings.read()
    if settings.mode != 'protected':
        raise HTTPException(409, 'This local workspace does not require sign-in.')
    address = request.client.host if request.client else 'unknown'
    if access.LOGIN_LIMITER.blocked(address):
        raise HTTPException(429, 'Too many unsuccessful attempts. Try again in 15 minutes.', headers={'Retry-After': '900'})
    if not access.verify_password(payload.password.get_secret_value(), settings.password):
        access.LOGIN_LIMITER.failed(address)
        raise HTTPException(401, 'The password was not accepted.')
    access.LOGIN_LIMITER.succeeded(address)
    # Signing in creates a fresh bearer; an old session supplied by the client
    # cannot fixate the new session and is revoked if it existed.
    previous = request.cookies.get(access.COOKIE_NAME)
    if previous and len(previous) <= 128 and previous.isascii():
        with SessionLocal() as db:
            existing = db.get(OperatorSessionModel, access.token_digest(previous))
            if existing:
                db.delete(existing)
                db.commit()
    token, expiration = access.create_session(settings)
    response = JSONResponse({'mode':'protected','requires_sign_in':True,'authenticated':True,
                             'expires_at':expiration.isoformat(),'expires_in_seconds':settings.lifetime_seconds,'csrf_token':access.csrf_token(token)}, headers={'Cache-Control':'no-store'})
    response.set_cookie(access.COOKIE_NAME, token, httponly=True, secure=settings.secure_cookie,
                        samesite='strict', max_age=settings.lifetime_seconds, path='/api/v1')
    return response


@access_router.post('/sign-out')
def sign_out(request: Request):
    token = request.cookies.get(access.COOKIE_NAME)
    if token and len(token) <= 128 and token.isascii():
        with SessionLocal() as db:
            existing = db.get(OperatorSessionModel, access.token_digest(token))
            if existing:
                db.delete(existing)
                db.commit()
    response = JSONResponse({'signed_out':True}, headers={'Cache-Control':'no-store'})
    response.delete_cookie(access.COOKIE_NAME, path='/api/v1', httponly=True, secure=access.AccessSettings.read().secure_cookie, samesite='strict')
    return response
