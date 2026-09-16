"""Portable benchmark case contracts, intentionally independent of source data."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BenchmarkMessage(BaseModel):
    message_id: str
    role: str
    content: str = Field(min_length=1)
    timestamp: datetime


class LongMemEvalCase(BaseModel):
    case_id: str
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    messages: list[BenchmarkMessage] = Field(min_length=1)
    category: str
    dimension_hint: str | None = None
    source_metadata: dict = Field(default_factory=dict)


class LongMemEvalImportRequest(BaseModel):
    """Raw JSON from a locally obtained, licence-compliant source file."""

    payload: dict | list


class LongMemEvalImportReport(BaseModel):
    adapter_version: str
    cases_imported: int
    case_ids: list[str]
    dimension_hints: list[str]
    source_format: str
    notice: str


class LongMemEvalValidationResponse(BaseModel):
    report: LongMemEvalImportReport
    # Small metadata previews, not full source conversations.
    cases: list[LongMemEvalCase]
