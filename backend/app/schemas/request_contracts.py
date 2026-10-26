"""Typed public shape of credential-free transport contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_serializer


class OpenRouterRequestContract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['openrouter-request-contract-v1']
    role: str
    provider_name: Literal['openrouter']
    endpoint: Literal['/api/v1/chat/completions']
    model: str
    payload_keys: list[str]
    payload_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    messages_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    max_tokens: dict[str, JsonValue]
    reasoning: dict[str, JsonValue]
    provider: dict[str, JsonValue]
    sampling: dict[str, dict[str, JsonValue]]
    response_format: dict[str, JsonValue]


class HTTPRequestAttemptReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['http-request-attempt-receipt-v1']
    role: str
    attempt_index: int = Field(ge=1)
    request_contract: OpenRouterRequestContract
    request_contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['response', 'transport_error']
    http_status: int | None
    error_type: str | None
    observer_error_type: str | None = None

    @model_serializer(mode='wrap')
    def _omit_absent_observer_error(self, handler):
        value = handler(self)
        if value.get('observer_error_type') is None:
            value.pop('observer_error_type', None)
        return value


def wire_metadata(execution):
    """Persist an allowlisted typed contract, never arbitrary caller dictionaries."""
    if not execution.get('request_contract'):
        return {}
    try:
        from app.target_ai.request_contracts import request_contract_sha256
        contract = OpenRouterRequestContract.model_validate(execution['request_contract']).model_dump(mode='json')
        digest = request_contract_sha256(contract)
        if digest != execution.get('request_contract_sha256'):
            return {}
        attempts = [HTTPRequestAttemptReceipt.model_validate(row).model_dump(mode='json')
                    for row in execution.get('request_contract_attempts', [])]
        if any(request_contract_sha256(row['request_contract']) != row['request_contract_sha256'] for row in attempts):
            return {}
        return {'request_contract': contract, 'request_contract_sha256': digest,
                'request_contract_attempts': attempts,
                **({'requested_reasoning_effort': execution['requested_reasoning_effort']}
                   if execution.get('requested_reasoning_effort') in {'low', 'medium'} else {})}
    except (ValueError, TypeError, KeyError):
        return {}
