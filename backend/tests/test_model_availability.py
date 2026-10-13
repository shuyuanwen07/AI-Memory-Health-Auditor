from datetime import datetime, timezone
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models import ModelAvailabilityModel
from app.services import model_availability as availability


def make_db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


@pytest.mark.parametrize('model', [
    'anthropic/claude-opus-5.5', 'openai/gpt-5.6', 'openai/gpt-5.6-pro',
    'openai/gpt-6.1-sol', 'openai/gpt-6-astra', 'google/gemini-3.1-flash',
])
def test_allowed_families_include_opus_gpt_56_and_6_and_gemini(model):
    assert availability.allowed(model)


@pytest.mark.parametrize('model', [
    'openai/gpt-5.6-batch', 'openai/gpt-6.1-batch', 'openai/gpt-6:batch',
    'openai/gpt-5.6-latest', 'anthropic/claude-sonnet-5.5', 'openai/gpt-5.5',
    'google/gemini-3.1-audio', 'openai/gpt-6-image', 'openrouter/auto',
])
def test_disallowed_families_aliases_and_batch_variants_are_filtered(model):
    assert not availability.allowed(model)


def test_catalog_filters_malformed_modalities_and_uses_friendly_names(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'data': [
            {'id': 'openai/gpt-6.1-sol', 'architecture': None},
            {'id': 'openai/gpt-5.6-batch', 'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']}},
            {'id': 'openai/gpt-6-astra', 'name': 'GPT-6 Astra', 'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']}},
            {'id': 'openai/gpt-6-luna', 'architecture': {'input_modalities': 'text', 'output_modalities': ['text']}},
            None,
        ]}
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-only')
    monkeypatch.setattr(availability, '_CATALOG', None)
    monkeypatch.setattr(availability.httpx, 'get', lambda *args, **kwargs: Response())
    result = availability.catalog()
    assert result == [
        {'value': 'openai/gpt-6.1-sol', 'label': 'GPT 6.1 sol'},
        {'value': 'openai/gpt-6-astra', 'label': 'GPT-6 Astra'},
    ]
    assert 'test-secret-only' not in repr(result)


def test_only_recent_verified_exact_model_is_selectable_and_probe_is_bounded(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'key-one')
    candidate = {'value': 'openai/gpt-6-astra', 'label': 'GPT-6 Astra'}
    monkeypatch.setattr(availability, 'catalog', lambda: [candidate])
    engine = make_db()
    requested = {}

    class Client:
        def __init__(self, provider, model): self.last_execution = None; self.model = model
        def complete_json(self, **kwargs):
            requested.update(kwargs)
            self.last_execution = {'reported_model': self.model, 'status': 'parsed'}
            return {'available': True}

    monkeypatch.setattr(availability, 'PipelineLLMClient', Client)
    with Session(engine) as db:
        assert availability.verified_options(db) == []
        result = availability.check_model(db, candidate['value'])
        assert result['status'] == 'available'
        assert requested['max_output_tokens'] == 64
        assert availability.verified_options(db) == [candidate]
        assert availability.check_model(db, candidate['value'])['status'] == 'available'
    assert requested['prompt'] == 'Return {"available":true}.'


def test_identity_mismatch_is_not_marked_available(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'key-one')
    candidate = {'value': 'openai/gpt-6-astra', 'label': 'GPT-6 Astra'}
    monkeypatch.setattr(availability, 'catalog', lambda: [candidate])
    engine = make_db()

    class Client:
        def __init__(self, provider, model): self.last_execution = {'reported_model': 'openai/gpt-6.1-sol'}
        def complete_json(self, **kwargs): return {'available': True}

    monkeypatch.setattr(availability, 'PipelineLLMClient', Client)
    with Session(engine) as db:
        result = availability.check_model(db, candidate['value'])
        assert result['status'] == 'unavailable'
        assert 'identity' in result['reason']
        assert availability.verified_options(db) == []


def test_failed_check_has_safe_reason_and_cooldown_prevents_repeat_charge(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'key-one')
    candidate = {'value': 'anthropic/claude-opus-5.5', 'label': 'Claude Opus 5.5'}
    monkeypatch.setattr(availability, 'catalog', lambda: [candidate])
    engine = make_db();calls = []

    class Client:
        def __init__(self, provider, model): self.last_execution = None
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            self.last_execution = {'last_http_status': 402, 'status': 'failed'}
            raise RuntimeError('never expose secret or response body')

    monkeypatch.setattr(availability, 'PipelineLLMClient', Client)
    with Session(engine) as db:
        first = availability.check_model(db, candidate['value'])
        second = availability.check_model(db, candidate['value'])
        assert first['status'] == second['status'] == 'unavailable'
        assert first['reason'] == 'The OpenRouter account could not cover this request'
        assert len(calls) == 1
        row = db.query(ModelAvailabilityModel).one()
        assert 'never expose secret' not in repr(row.operations)
        assert 'key-one' not in repr(row.operations)


def test_credential_change_cannot_reuse_an_old_verified_check(monkeypatch):
    model = 'google/gemini-3.1-flash';candidate = {'value': model, 'label': 'Gemini 3.1 Flash'}
    monkeypatch.setattr(availability, 'catalog', lambda: [candidate])
    engine = make_db()

    class Client:
        def __init__(self, provider, model): self.last_execution = {'reported_model': model}
        def complete_json(self, **kwargs): return {'available': True}

    monkeypatch.setattr(availability, 'PipelineLLMClient', Client)
    with Session(engine) as db:
        monkeypatch.setenv('OPENROUTER_API_KEY', 'first-key')
        availability.check_model(db, model)
        assert availability.verified_options(db) == [candidate]
        monkeypatch.setenv('OPENROUTER_API_KEY', 'second-key')
        assert availability.verified_options(db) == []


def test_active_probe_is_reported_as_checking_and_stale_intent_is_unknown(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'key-one')
    candidate = {'value': 'openai/gpt-6-astra', 'label': 'GPT-6 Astra'}
    monkeypatch.setattr(availability, 'catalog', lambda: [candidate])
    engine = make_db()
    with Session(engine) as db:
        row = ModelAvailabilityModel(id='active', model=candidate['value'],
            credential_scope=availability.credential_scope(), status='checking', operations=[], checked_at=None)
        db.add(row); db.commit()
        monkeypatch.setattr(availability, 'database_stage_busy', lambda *_: True)
        assert availability.options_and_checks(db)[0]['status'] == 'checking'
        monkeypatch.setattr(availability, 'database_stage_busy', lambda *_: False)
        assert availability.options_and_checks(db)[0]['status'] == 'not_checked'


def test_operation_receipt_history_is_bounded(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'key-one')
    model = 'openai/gpt-6-astra';candidate = {'value': model, 'label': 'GPT-6 Astra'}
    monkeypatch.setattr(availability, 'catalog', lambda: [candidate])
    engine = make_db()
    old = datetime.now(timezone.utc) - timedelta(days=1)

    class Client:
        def __init__(self, provider, model): self.last_execution = {'reported_model': model}
        def complete_json(self, **kwargs): return {'available': True}

    monkeypatch.setattr(availability, 'PipelineLLMClient', Client)
    with Session(engine) as db:
        identity = __import__('hashlib').sha256((availability.credential_scope() + model).encode()).hexdigest()
        db.add(ModelAvailabilityModel(id=identity, model=model, credential_scope=availability.credential_scope(),
            status='unavailable', operations=[{'reason': 'old'} for _ in range(50)], checked_at=old.replace(tzinfo=None)))
        db.commit()
        availability.check_model(db, model)
        assert len(db.get(ModelAvailabilityModel, identity).operations) == availability.MAX_RETAINED_OPERATIONS
