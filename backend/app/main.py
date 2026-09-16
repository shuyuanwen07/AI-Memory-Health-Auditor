import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.api.routes import router
from app.api.research_routes import research_router
from app.database.session import Base, engine
import app.models  # register models


class ContentLengthLimitMiddleware(BaseHTTPMiddleware):
    """Reject accidentally oversized JSON uploads before parsing their body.

    This is a guardrail for authorised conversation and research uploads, not a
    substitute for production traffic protection. Route schemas retain their
    own field-level limits for clients without a Content-Length header.
    """

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        raw_length = request.headers.get("content-length")
        if raw_length is not None:
            try:
                declared_length = int(raw_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Content-Length must be a whole number."})
            if declared_length < 0:
                return JSONResponse(status_code=400, content={"detail": "Content-Length cannot be negative."})
            if declared_length > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request exceeds the {self.max_bytes // 1_000_000} MB upload limit."},
                )
        return await call_next(request)

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tests and an explicitly opted-in local mode can create an empty schema.
    # Docker development runs the versioned Alembic migration chain instead.
    if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AI Memory Health Auditor", version="0.1.0", lifespan=lifespan)
app.add_middleware(ContentLengthLimitMiddleware, max_bytes=int(os.getenv("MAX_REQUEST_BYTES", "5000000")))
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(research_router)
