import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.research_routes import research_router
from app.database.session import Base, engine
import app.models  # register models

app = FastAPI(title="AI Memory Health Auditor", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(research_router)
@app.on_event("startup")
def startup():
    # Tests and an explicitly opted-in local mode can create an empty schema.
    # Docker development runs the versioned Alembic migration chain instead.
    if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
        Base.metadata.create_all(engine)
