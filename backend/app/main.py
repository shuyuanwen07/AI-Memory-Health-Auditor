import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from app.api.routes import router
from app.api.research_routes import research_router
from app.database.session import Base, engine
import app.models  # register models


class RequestTooLarge(Exception):
    """Internal signal raised while the ASGI server streams an oversized body."""


class ContentSizeLimitMiddleware:
    """Reject accidentally oversized JSON uploads before parsing their body.

    This is a guardrail for authorised conversation and research uploads, not a
    substitute for production traffic protection. Route schemas retain their
    own field-level limits for clients without a Content-Length header.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        raw_length = headers.get("content-length")
        if raw_length is not None:
            try:
                declared_length = int(raw_length)
            except ValueError:
                await JSONResponse(status_code=400, content={"detail": "Content-Length must be a whole number."})(scope, receive, send)
                return
            if declared_length < 0:
                await JSONResponse(status_code=400, content={"detail": "Content-Length cannot be negative."})(scope, receive, send)
                return
            if declared_length > self.max_bytes:
                await JSONResponse(
                    status_code=413,
                    content={"detail": f"Request exceeds the {self.max_bytes // 1_000_000} MB upload limit."},
                )(scope, receive, send)
                return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await JSONResponse(status_code=413, content={"detail": f"Request exceeds the {self.max_bytes // 1_000_000} MB upload limit."})(scope, receive, send)

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tests and an explicitly opted-in local mode can create an empty schema.
    # Docker development runs the versioned Alembic migration chain instead.
    if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Memory Health Auditor", version="0.1.0", lifespan=lifespan)
app.add_middleware(ContentSizeLimitMiddleware, max_bytes=int(os.getenv("MAX_REQUEST_BYTES", "5000000")))
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(research_router)
