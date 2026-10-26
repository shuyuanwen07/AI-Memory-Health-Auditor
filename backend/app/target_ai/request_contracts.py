"""Credential-free contracts captured at each actual OpenRouter HTTP attempt."""
from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from urllib.parse import urlsplit

_OBSERVER = ContextVar('openrouter_request_contract_observer', default=None)
VERSION = 'openrouter-request-contract-v1'


def request_contract_sha256(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _field(payload, key):
    return {'present': True, 'value': copy.deepcopy(payload[key])} if key in payload else {'present': False}


def build_openrouter_request_contract(*, url, payload, role):
    """Hash the exact payload, exposing only fixed safe control fields."""
    endpoint = urlsplit(url)
    if endpoint.scheme != 'https' or endpoint.netloc != 'openrouter.ai' or endpoint.path != '/api/v1/chat/completions' or endpoint.query or endpoint.fragment:
        raise ValueError('Unsupported OpenRouter request endpoint.')
    routing = payload.get('provider')
    if routing is not None and (not isinstance(routing, dict) or set(routing) - {'require_parameters', 'allow_fallbacks', 'only'}):
        raise ValueError('Unsupported routing controls.')
    reasoning = payload.get('reasoning')
    if reasoning is not None and (not isinstance(reasoning, dict)
            or set(reasoning) != {'effort'} or reasoning['effort'] not in {'low', 'medium'}):
        raise ValueError('Unsupported reasoning controls.')
    for key in ('temperature', 'top_p', 'seed', 'frequency_penalty', 'presence_penalty'):
        value = payload.get(key)
        if value is not None and (type(value) not in (int, float)):
            raise ValueError('Invalid sampling controls.')
    fmt = payload.get('response_format')
    schema = (fmt.get('json_schema') or {}).get('schema') if isinstance(fmt, dict) else None
    return {'version': VERSION, 'role': role, 'provider_name': 'openrouter',
            'endpoint': endpoint.path, 'model': payload.get('model'),
            'payload_keys': sorted(payload), 'payload_sha256': request_contract_sha256(payload),
            'messages_sha256': request_contract_sha256(payload.get('messages')),
            'max_tokens': _field(payload, 'max_tokens'), 'reasoning': _field(payload, 'reasoning'),
            'provider': _field(payload, 'provider'),
            'sampling': {key: _field(payload, key) for key in ('temperature', 'top_p', 'seed', 'frequency_penalty', 'presence_penalty')},
            'response_format': {'present': 'response_format' in payload,
                                'type': fmt.get('type') if isinstance(fmt, dict) else None,
                                'sha256': request_contract_sha256(fmt) if 'response_format' in payload else None,
                                'schema_sha256': request_contract_sha256(schema) if schema is not None else None}}


@contextmanager
def observe_request_contracts(observer):
    """before_send may veto; after_send errors cannot replace provider outcomes."""
    token = _OBSERVER.set(observer)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def send_with_request_contract(*, url, payload, role, attempt_index, collector, send):
    if url != 'https://openrouter.ai/api/v1/chat/completions':
        return send()
    contract = build_openrouter_request_contract(url=url, payload=payload, role=role)
    receipt = {'version': 'http-request-attempt-receipt-v1', 'role': role,
               'attempt_index': attempt_index, 'request_contract': contract,
               'request_contract_sha256': request_contract_sha256(contract), 'status': 'prepared',
               'http_status': None, 'error_type': None}
    observer = _OBSERVER.get()
    if observer:
        observer({**copy.deepcopy(receipt), 'phase': 'before_send'})
    try:
        response = send()
        receipt.update(status='response', http_status=response.status_code)
        return response
    except BaseException as exc:
        receipt.update(status='transport_error', error_type=type(exc).__name__)
        raise
    finally:
        collector.append(receipt)
        if observer:
            try:
                observer({**copy.deepcopy(receipt), 'phase': 'after_send'})
            except Exception as exc:
                receipt['observer_error_type'] = type(exc).__name__


def request_contract_metadata(attempts):
    if not attempts:
        return {}
    latest = attempts[-1]
    result = {'request_contract': latest['request_contract'],
              'request_contract_sha256': latest['request_contract_sha256'],
              'request_contract_attempts': copy.deepcopy(attempts)}
    reasoning = latest['request_contract']['reasoning']
    if reasoning.get('present') and isinstance(reasoning.get('value'), dict) and reasoning['value'].get('effort') in {'low', 'medium'}:
        result['requested_reasoning_effort'] = reasoning['value']['effort']
    return result
