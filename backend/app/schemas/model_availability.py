from pydantic import BaseModel, Field


class ModelAvailabilityCheckRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
