"""Shared redacted trace ledger for the semantic-agent pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from app.models import AgentExecutionModel


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def record_agent_execution(
    db,
    *,
    role: str,
    provider: str,
    model: str,
    prompt_template_version: str,
    instructions: str,
    prompt: str,
    schema: dict | None,
    input_payload: Any,
    input_refs: dict,
    output_data: dict | list | None,
    status: str,
    execution: dict | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
    error_diagnostics: dict | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
    handoff_from: str | None = None,
    handoff_to: str | None = None,
) -> AgentExecutionModel:
    """Save exact role/output metadata and hashes, while source data stays in its parent records."""
    receipt = execution or {}
    prompt_sha = receipt.get("prompt_fingerprint") or fingerprint({
        "version": prompt_template_version,
        "instructions": instructions,
        "prompt": prompt,
        "schema": schema,
    })
    row = AgentExecutionModel(
        id=f"AGT{uuid4().hex.upper()}",
        role=role,
        conversation_id=conversation_id,
        run_id=run_id,
        provider=str(receipt.get("provider") or provider),
        model=str(receipt.get("model") or model),
        reported_model=receipt.get("reported_model"),
        prompt_template_version=prompt_template_version,
        prompt_fingerprint=prompt_sha,
        input_fingerprint=receipt.get("input_fingerprint") or fingerprint(input_payload),
        input_refs=input_refs,
        output_data=output_data,
        status=status,
        attempt_count=int(receipt.get("request_attempts") or 0),
        elapsed_ms=receipt.get("elapsed_ms"),
        error_code=error_code or receipt.get("error_code"),
        error_summary=error_summary,
        error_diagnostics=error_diagnostics,
        handoff_from=handoff_from,
        handoff_to=handoff_to,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(row)
    db.flush()
    return row


def agent_execution_schema(row: AgentExecutionModel) -> dict:
    return {
        "execution_id": row.id,
        "role": row.role,
        "conversation_id": row.conversation_id,
        "run_id": row.run_id,
        "provider": row.provider,
        "model": row.model,
        "reported_model": row.reported_model,
        "prompt_template_version": row.prompt_template_version,
        "prompt_fingerprint": row.prompt_fingerprint,
        "input_fingerprint": row.input_fingerprint,
        "input_refs": row.input_refs or {},
        "output_data": row.output_data,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "elapsed_ms": row.elapsed_ms,
        "error_code": row.error_code,
        "error_summary": row.error_summary,
        "error_diagnostics": row.error_diagnostics,
        "handoff_from": row.handoff_from,
        "handoff_to": row.handoff_to,
        "created_at": row.created_at,
    }
