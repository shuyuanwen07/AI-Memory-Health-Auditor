"""Request-scoped comparison exports; never persisted as audit labels."""
from pydantic import BaseModel


class SceneEvidenceCheckRequest(BaseModel):
    summary: dict
