"""Stable receipts for explicitly rejected auxiliary identity output.

Receipt construction checks observed transport/input provenance. The controlled
adapter separately requires a matching, persisted failed execution before it
can continue. No rejected output or database/time identifier enters a receipt.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer, _digest
from app.target_ai.openrouter import build_openrouter_json_payload, CHAT_COMPLETIONS_URL
from app.target_ai.request_contracts import build_openrouter_request_contract, request_contract_sha256


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity_failure_receipt_sha256(receipt: dict) -> str:
    return hashlib.sha256(_json(receipt).encode("utf-8")).hexdigest()


def build_identity_failure_receipt(*, observation: dict | None, provider: str, model: str,
                                   max_output_tokens: int, question: str | None = None,
                                   context: list[str] | None = None, reasoning_effort: str | None = None) -> dict | None:
    """Return a stable candidate only for a completely attributable rejection.

    The caller must also verify a persisted stage with
    ``recorded_identity_failure_matches`` before allowing a final target call.
    Pure reconstruction by offline tooling does not establish persistence.
    """
    try:
        return _build(observation=observation, provider=provider, model=model,
                      max_output_tokens=max_output_tokens, question=question, context=context, reasoning_effort=reasoning_effort)
    except (KeyError, TypeError, ValueError, AttributeError):
        # Malformed or unknown provenance always retains fail-closed behavior.
        return None


def _build(*, observation, provider, model, max_output_tokens, question, context, reasoning_effort):
    analyzer = TargetIdentityEvidenceAnalyzer
    # Only this transport currently records and sends the frozen output cap
    # together with model identity, HTTP status and choice completion metadata.
    if (provider != "openrouter" or not isinstance(observation, dict)
            or observation.get("status") != "failed"):
        return None
    raw = observation["raw_input_payload"]
    question = raw["question"] if question is None else question
    context = raw["selected_context"] if context is None else context
    if (not isinstance(question, str) or not question.strip()
            or len(question) > analyzer.MAX_QUESTION_CHARACTERS
            or not isinstance(context, list) or not context or len(context) > analyzer.MAX_RECORDS
            or any(not isinstance(value, str) or not value.strip() for value in context)
            or type(max_output_tokens) is not int or not 128 <= max_output_tokens <= 8192
            or raw != {"question": question, "selected_context": context}):
        return None
    if (observation.get("role") != analyzer.ROLE or observation.get("provider") != provider
            or observation.get("model") != model
            or observation.get("prompt_template_version") != analyzer.VERSION
            or observation.get("instructions") != analyzer.INSTRUCTIONS
            or observation.get("schema") != analyzer.REQUEST_SCHEMA.model_json_schema()):
        return None
    payload, _catalog = analyzer.build_request_payload(question, context)
    prompt = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if (observation.get("input_payload") != payload or observation.get("prompt") != prompt
            or observation.get("input_refs", {}).get("selected_context_sha256") != _digest(context)
            or observation.get("input_refs", {}).get("record_indices") != list(range(1, len(context) + 1))):
        return None
    execution = observation["execution"]
    if not isinstance(execution, dict):
        return None
    expected_prompt = {
        "version": analyzer.VERSION, "instructions": analyzer.INSTRUCTIONS,
        "prompt": prompt, "schema": analyzer.REQUEST_SCHEMA.model_json_schema(),
        "ollama_thinking": False if provider == "ollama" else None,
    }
    if (execution.get("version") != "pipeline-http-meter-v2"
            or execution.get("provider") != provider or execution.get("model") != model
            or execution.get("reported_model") != model or execution.get("agent_role") != analyzer.ROLE
            or execution.get("prompt_template_version") != analyzer.VERSION
            or execution.get("prompt_fingerprint") != _digest(expected_prompt)
            or execution.get("input_fingerprint") != hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            or type(execution.get("last_http_status")) is not int or execution["last_http_status"] != 200
            or type(execution.get("request_attempts")) is not int or execution["request_attempts"] != 1
            or type(execution.get("failed_http_attempts")) is not int or execution["failed_http_attempts"] != 0):
        return None
    for key in ("requested_output_token_limit", "declared_output_token_limit"):
        if type(execution.get(key)) is not int or execution[key] != max_output_tokens:
            return None
    configured = execution.get("configured_output_token_cap")
    if "configured_output_token_cap" not in execution or (configured is not None
            and (type(configured) is not int or configured != max_output_tokens)):
        return None
    if any(execution.get(key) for key in ("provider_error_scope", "provider_error_status",
                                         "provider_error_category", "response_format_fallback",
                                         "schema_rejection_http_status")):
        return None
    diagnostics = observation.get("error_diagnostics") or {}
    phase = diagnostics.get("phase")
    finish = execution.get("reported_finish_reason")
    if (type(execution.get("response_choice_count")) is not int
            or execution["response_choice_count"] != 1
            or execution.get("completion_status", "complete" if finish == "stop" else "truncated")
            != ("complete" if finish == "stop" else "truncated")):
        return None
    if (phase == "output_validation" and observation.get("error_code") == "invalid_identity_contract"
            and diagnostics.get("validation_type") in {"ValueError", "ValidationError"}
            and execution.get("status") == "parsed" and execution.get("error_code") is None
            and finish == "stop"):
        if execution.get("output_fingerprint") != _digest(observation.get("raw_model_draft")):
            return None
        reason = "invalid_identity_contract"
    elif (phase == "provider_request" and observation.get("error_code") == "PipelineRequestError"
          and diagnostics.get("validation_type") == "PipelineRequestError"
          and execution.get("status") == "failed" and execution.get("error_code") == "PipelineRequestError"
          and finish == "length"):
        if execution.get("output_fingerprint") is not None:
            return None
        reason = "provider_output_truncated"
    else:
        return None
    controls = {}
    has_wire = any(key in execution for key in ('request_contract', 'request_contract_sha256', 'request_contract_attempts'))
    if reasoning_effort is not None or has_wire:
        if (observation.get('requested_reasoning_effort') != reasoning_effort
                or execution.get('requested_reasoning_effort') != reasoning_effort):
            return None
        wire_payload = build_openrouter_json_payload(model=model, instructions=analyzer.INSTRUCTIONS,
            prompt=prompt, schema_name=analyzer.ROLE, schema=analyzer.REQUEST_SCHEMA.model_json_schema(),
            max_output_tokens=max_output_tokens, reasoning_effort=reasoning_effort,
            provider_options=execution['request_contract']['provider']['value'])
        contract = build_openrouter_request_contract(url=CHAT_COMPLETIONS_URL, payload=wire_payload, role=analyzer.ROLE)
        contract_hash = request_contract_sha256(contract)
        attempts = execution.get('request_contract_attempts')
        if (execution.get('request_contract') != contract
                or execution.get('request_contract_sha256') != contract_hash
                or not isinstance(attempts, list) or len(attempts) != 1):
            return None
        sent = attempts[0]
        if (sent.get('version') != 'http-request-attempt-receipt-v1' or sent.get('role') != analyzer.ROLE
                or sent.get('attempt_index') != 1 or sent.get('status') != 'response'
                or sent.get('http_status') != 200 or sent.get('error_type') is not None
                or sent.get('observer_error_type') is not None or sent.get('request_contract') != contract
                or sent.get('request_contract_sha256') != contract_hash):
            return None
        controls = {'request_contract_version': contract['version'], 'request_contract_sha256': contract_hash,
                    'reasoning': contract['reasoning']}
    return {
        "version": "target-identity-failure-receipt-v2" if controls else "target-identity-failure-receipt-v1", "reason": reason,
        **controls,
        "analysis_version": analyzer.VERSION, "source_context_sha256": _digest(context),
        "question_sha256": _digest(question), "prompt_fingerprint": execution["prompt_fingerprint"],
        "input_fingerprint": execution["input_fingerprint"], "provider": provider, "model": model,
        "reported_model": execution["reported_model"], "agent_role": analyzer.ROLE,
        "requested_output_token_limit": execution["requested_output_token_limit"],
        "declared_output_token_limit": execution["declared_output_token_limit"],
        "configured_output_token_cap": configured, "http_status": 200, "finish_reason": finish,
        "phase": phase, "execution_status": execution["status"], "request_attempts": 1,
        "failed_http_attempts": 0, "response_choice_count": 1,
        "output_fingerprint": execution.get("output_fingerprint"),
    }


def validate_identity_failure_receipt(receipt: dict, *, observation: dict | None, provider: str,
                                      model: str, max_output_tokens: int,
                                      question: str | None = None, context: list[str] | None = None, reasoning_effort: str | None = None) -> bool:
    """Pure observed-input validation; does not claim SQL persistence."""
    expected = build_identity_failure_receipt(observation=observation, provider=provider, model=model,
        max_output_tokens=max_output_tokens, question=question, context=context, reasoning_effort=reasoning_effort)
    return expected is not None and receipt == expected


def recorded_identity_failure_matches(receipt: dict, recorded_stage: dict | None) -> bool:
    """Bind a candidate to the actual saved failed identity stage, without ID hashing."""
    if (not isinstance(receipt, dict) or not isinstance(recorded_stage, dict)
            or recorded_stage.get("status") != "failed"
            or receipt.get("version") not in {"target-identity-failure-receipt-v1", "target-identity-failure-receipt-v2"}
            or receipt.get("phase") not in {"output_validation", "provider_request"}):
        return False
    keys = {"role": "agent_role", "provider": "provider", "model": "model",
            "reported_model": "reported_model", "prompt_template_version": "analysis_version",
            "prompt_fingerprint": "prompt_fingerprint", "input_fingerprint": "input_fingerprint",
            "attempt_count": "request_attempts"}
    if any(recorded_stage.get(stage_key) != receipt.get(receipt_key)
           for stage_key, receipt_key in keys.items()):
        return False
    if (not recorded_stage.get("execution_id")
            or recorded_stage.get("output_data") is not None
            or not isinstance(recorded_stage.get("input_refs"), dict)
            or recorded_stage["input_refs"].get("selected_context_sha256") != receipt.get("source_context_sha256")):
        return False
    expected_error = "invalid_identity_contract" if receipt["phase"] == "output_validation" else "PipelineRequestError"
    if recorded_stage.get("error_code") != expected_error:
        return False
    diagnostics = recorded_stage.get("error_diagnostics") or {}
    if not isinstance(diagnostics, dict):
        return False
    if receipt['version'] == 'target-identity-failure-receipt-v2':
        contract = diagnostics.get('request_contract')
        if (not isinstance(contract, dict) or contract.get('version') != receipt.get('request_contract_version')
                or diagnostics.get('request_contract_sha256') != receipt.get('request_contract_sha256')
                or request_contract_sha256(contract) != receipt.get('request_contract_sha256')
                or contract.get('reasoning') != receipt.get('reasoning')):
            return False
        attempts = diagnostics.get('request_contract_attempts')
        if (not isinstance(attempts, list) or len(attempts) != 1
                or attempts[0].get('request_contract_sha256') != receipt['request_contract_sha256']
                or attempts[0].get('observer_error_type') is not None
                or attempts[0].get('request_contract') != contract
                or attempts[0].get('role') != receipt['agent_role']
                or attempts[0].get('attempt_index') != 1
                or attempts[0].get('status') != 'response'
                or attempts[0].get('http_status') != 200
                or attempts[0].get('error_type') is not None):
            return False
    return all(diagnostics.get(key) == receipt.get(value) for key, value in {
        "phase": "phase", "last_http_status": "http_status", "reported_finish_reason": "finish_reason",
        "requested_output_token_limit": "requested_output_token_limit",
        "declared_output_token_limit": "declared_output_token_limit",
        "response_choice_count": "response_choice_count",
    }.items()) and diagnostics.get("configured_output_token_cap") == receipt.get("configured_output_token_cap")
