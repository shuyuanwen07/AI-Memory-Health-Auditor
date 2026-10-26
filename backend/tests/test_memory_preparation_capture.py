"""Actual disposable SQLite preparation snapshots; no credentials or providers."""
from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path('/scripts') if Path('/scripts').exists() else Path(__file__).resolve().parents[2] / 'scripts'))
import run_stability_trial as trial
from app.database.session import Base
from app.memory_agent.store import SqlTargetMemoryStore
from app.models import AuditRunModel, ConversationModel
from app.schemas import Conversation, ConversationMessage


@pytest.fixture
def prepared():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(ConversationModel(id='C-SYN', authorised=True))
        db.add(AuditRunModel(id='RUN-SYN', conversation_id='C-SYN', status='CREATED',
            target_configuration='strong', provider='rule_based', model='offline',
            temperature=0, random_seed=42, test_budget=1, prompt_template_version='offline',
            pipeline_provider='rule_based', pipeline_model='offline', evaluator_provider='rule_based',
            evaluator_model='offline', memory_strategy='strong_rule_based'))
        db.commit()
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        conversation = Conversation(conversation_id='C-SYN', authorised=True, created_at=now,
            messages=[ConversationMessage(message_id='MSG001', role='user', timestamp=now,
                content='I used MySQL before. The backend now uses PostgreSQL. I generally prefer Python.')])
        yield SqlTargetMemoryStore(db, max_active_records=1), conversation
    engine.dispose()


def load(directory):
    return json.loads((directory / 'private-memory-preparation-receipts.json').read_text())


def test_actual_snapshot_is_atomic_private_and_precedes_provider(prepared, tmp_path, monkeypatch):
    store, conversation = prepared
    replace = trial.os.replace
    observed = []
    def checked(source, destination):
        assert stat.S_IMODE(Path(source).stat().st_mode) == 0o600
        observed.append(json.loads(Path(source).read_text()))
        return replace(source, destination)
    monkeypatch.setattr(trial.os, 'replace', checked)
    wrapped = trial.memory_preparation_wrapper(SqlTargetMemoryStore.ingest, tmp_path)
    wrapped(store, 'RUN-SYN', conversation)
    # A provider invoked by the caller can already inspect the completed snapshot.
    receipt = load(tmp_path)
    assert receipt['provenance'] == 'actual_runtime_observation' and receipt['reconstructed'] is False
    snapshot = receipt['observations'][0]
    assert snapshot['status'] == 'completed' and snapshot['snapshot_complete']
    assert snapshot['conversation_id'] == 'C-SYN' and snapshot['capacity'] == 1
    assert snapshot['records'] and snapshot['events']
    assert any(event['details'].get('maintenance_action') == 'capacity_evicted_record' for event in snapshot['events'])
    assert all(record['observed_at'].startswith('2026-01-02') for record in snapshot['records'])
    assert [record['write_order'] for record in snapshot['records']] == sorted(record['write_order'] for record in snapshot['records'])
    assert len(observed) == 1
    before = (tmp_path / 'private-memory-preparation-receipts.json').read_bytes()
    wrapped(store, 'RUN-SYN', conversation)
    assert (tmp_path / 'private-memory-preparation-receipts.json').read_bytes() == before
    assert len(observed) == 1 and not list(tmp_path.glob('.memory-preparation-*'))


def test_partial_exception_preserves_original_and_actual_state(prepared, tmp_path):
    store, conversation = prepared
    original = ValueError('SENSITIVE DO NOT LOG')
    def partial(self, run_id, conversation):
        SqlTargetMemoryStore.ingest(self, run_id, conversation)
        raise original
    with pytest.raises(ValueError) as caught:
        trial.memory_preparation_wrapper(partial, tmp_path, required=True)(store, 'RUN-SYN', conversation)
    assert caught.value is original
    snapshot = load(tmp_path)['observations'][0]
    assert snapshot['status'] == 'failed' and snapshot['exception_type'] == 'ValueError'
    assert snapshot['records'] and snapshot['events']
    assert 'SENSITIVE' not in json.dumps(snapshot)


def test_io_failure_logs_type_and_does_not_retry_capture(prepared, tmp_path, monkeypatch, capsys):
    store, conversation = prepared
    calls = []
    def fail(*args):
        calls.append(1)
        raise OSError('SECRET KEY AND CONTENT')
    monkeypatch.setattr(trial.os, 'replace', fail)
    wrapped = trial.memory_preparation_wrapper(SqlTargetMemoryStore.ingest, tmp_path)
    wrapped(store, 'RUN-SYN', conversation)
    wrapped(store, 'RUN-SYN', conversation)
    assert len(calls) == 1 and not list(tmp_path.glob('.memory-preparation-*'))
    stderr = capsys.readouterr().err
    assert 'OSError' in stderr and 'SECRET' not in stderr


def test_required_snapshot_failure_stops_before_ingest_returns(prepared, tmp_path, monkeypatch):
    store, conversation = prepared
    monkeypatch.setattr(trial, '_validate_memory_preparation', lambda *args: {'passed': False})
    wrapped = trial.memory_preparation_wrapper(SqlTargetMemoryStore.ingest, tmp_path, required=True, protocol={})
    with pytest.raises(RuntimeError, match='missing or incomplete'):
        wrapped(store, 'RUN-SYN', conversation)
    assert load(tmp_path)['observations'][0]['status'] == 'completed'
    with pytest.raises(RuntimeError, match='remains invalid'):
        wrapped(store, 'RUN-SYN', conversation)


def test_builder_does_not_read_credentials_or_mutate_store(prepared, monkeypatch):
    store, conversation = prepared
    store.ingest('RUN-SYN', conversation)
    def forbidden(*args, **kwargs):
        raise AssertionError('Environment must not be read')
    monkeypatch.setattr(trial.os, 'getenv', forbidden)
    monkeypatch.setattr(store.db, 'flush', forbidden)
    first = trial.build_memory_preparation_observation(store, 'RUN-SYN', conversation, status='completed')
    second = trial.build_memory_preparation_observation(store, 'RUN-SYN', conversation, status='completed')
    assert first == second and first['snapshot_complete']


def test_required_receipt_real_validator_accepts_actual_store(prepared, tmp_path):
    store, conversation = prepared
    protocol = {'target_memory_profile': store.profile.model_dump(mode='json'), 'target_memory_capacity': 1}
    trial.memory_preparation_wrapper(SqlTargetMemoryStore.ingest, tmp_path, required=True, protocol=protocol)(store, 'RUN-SYN', conversation)
    assert trial._validate_memory_preparation(tmp_path / 'private-memory-preparation-receipts.json', protocol)['passed']


def test_failed_capture_cannot_mask_original_ingest_exception(prepared, tmp_path, monkeypatch, capsys):
    store, conversation = prepared
    original = LookupError('PRIVATE ORIGINAL')
    def failed(*args):
        raise original
    def io_failed(*args):
        raise OSError('PRIVATE IO')
    monkeypatch.setattr(trial.os, 'replace', io_failed)
    with pytest.raises(LookupError) as caught:
        trial.memory_preparation_wrapper(failed, tmp_path, required=True)(store, 'RUN-SYN', conversation)
    assert caught.value is original
    assert 'PRIVATE' not in capsys.readouterr().err


def test_main_restores_ingest_after_original_pipeline_exception(tmp_path, monkeypatch):
    from app.target_ai.providers import HttpTargetAIConnector
    from app.extraction.llm import PipelineLLMClient
    from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
    # main's older observer patches are outside this capture change; keep test isolated.
    for cls, name in ((HttpTargetAIConnector, '_execute_provider'), (HttpTargetAIConnector, 'execute'),
                      (PipelineLLMClient, 'complete_json'), (TargetIdentityEvidenceAnalyzer, 'analyze')):
        monkeypatch.setattr(cls, name, getattr(cls, name))
    protocol = {'strategies': ['strong_rule_based'], 'model': 'openai/gpt-6-luna', 'provider': 'openrouter',
        'grading_output_token_limit': 4096, 'target_memory_profile': {}, 'output_token_limit': 8192}
    (tmp_path / 'pilot-protocol.json').write_text(json.dumps(protocol))
    monkeypatch.setattr(trial, 'preflight_grader_budget', lambda *args: {'passed': True})
    monkeypatch.setattr(trial, 'preflight_all_roles', lambda *args: {'passed': True})
    monkeypatch.setattr(trial, 'trial_grader_cap', lambda *args: 4096)
    monkeypatch.setattr(trial, 'wire_required', lambda *args: False)
    monkeypatch.setattr(sys, 'argv', ['trial', '--directory', str(tmp_path)])
    original = SqlTargetMemoryStore.ingest
    error = ArithmeticError('original pipeline failure')
    def run(*args, **kwargs):
        assert SqlTargetMemoryStore.ingest is not original
        raise error
    monkeypatch.setattr(trial.runpy, 'run_path', run)
    with pytest.raises(ArithmeticError) as caught:
        trial.main()
    assert caught.value is error and SqlTargetMemoryStore.ingest is original
