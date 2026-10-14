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
    diagnostics = dict(error_diagnostics or {})
    if receipt.get("response_format_fallback"):
        diagnostics["response_format_fallback"] = receipt["response_format_fallback"]
    rejected_status = receipt.get("schema_rejection_http_status")
    if type(rejected_status) is int:
        diagnostics["schema_rejection_http_status"] = rejected_status
    failed_attempts = receipt.get("failed_http_attempts")
    upstream_status = receipt.get("last_http_status")
    if type(upstream_status) is int and 100 <= upstream_status <= 599 and (
            (type(failed_attempts) is int and failed_attempts > 0) or status == "failed"):
        diagnostics["last_http_status"] = upstream_status
    error_scope = receipt.get("provider_error_scope")
    if error_scope in {"top_level", "choice", "finish_reason"}:
        diagnostics["provider_error_scope"] = error_scope
        error_status = receipt.get("provider_error_status")
        if type(error_status) is int and 400 <= error_status <= 599:
            diagnostics["provider_error_status"] = error_status
    if receipt.get("provider_error_category") == "capacity_limit":
        diagnostics["provider_error_category"] = "capacity_limit"
    choice_count = receipt.get("response_choice_count")
    if type(choice_count) is int and 0 <= choice_count <= 10000:
        diagnostics["response_choice_count"] = choice_count
    output_limit = receipt.get("requested_output_token_limit")
    if type(output_limit) is int and 0 < output_limit <= 1000000:
        diagnostics["requested_output_token_limit"] = output_limit
    for field in ("declared_output_token_limit", "configured_output_token_cap"):
        value = receipt.get(field)
        if type(value) is int and 0 < value <= 1000000:
            diagnostics[field] = value
    finish_reason = receipt.get("reported_finish_reason")
    if isinstance(finish_reason, str) and finish_reason in {"stop", "length", "content_filter", "tool_calls", "error", "other"}:
        diagnostics["reported_finish_reason"] = finish_reason
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
        error_diagnostics=diagnostics or None,
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
