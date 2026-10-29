"""Two-answer isolated rehearsal only: frozen reviews are synthetic fixtures."""
from unittest.mock import patch
import pytest
from sqlalchemy import select, text
from app.models import AuditRunModel, TargetResponseModel, EvaluationResultModel
from app.services.ac3_staging import stage_reviewed_suite
from app.services.ac3_fixture_coordinator import FixtureProvider, disabled_live_runner, run_fixture_step
from test_ac3_database_mapping import saved_histories, fake_compile, add_fixture_audits


def fake_hosted_compile(path, expected, reservation, snapshot=None):
    result = fake_compile(path, expected, reservation, snapshot)
    result['model_configuration'].update(target_provider='openrouter', target_model='openai/gpt-6-luna', evaluator_model='rule-based-v4', evaluator_implementation_version='rule-based-v65', pipeline_implementation_version='rule-based-v35')
    return result


@pytest.fixture
def prepared(saved_histories):
    db, frozen, digest, mapping = saved_histories
    add_fixture_audits(db)
    for row in db.scalars(select(AuditRunModel)):
        row.provider = 'openrouter'; row.model = 'openai/gpt-6-luna'; row.evaluator_model = 'rule-based-v4'
    db.commit(); runs = {f'H{i}':f'R{i}' for i in range(8)}
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_hosted_compile):
        stage_reviewed_suite(db, frozen, digest, '0', mapping, runs)
    db.execute(text('CREATE TABLE ac3_attempt_scopes (scope_id TEXT, frozen_sha256 TEXT, status TEXT)'))
    db.execute(text('CREATE TABLE ac3_attempt_receipts (scope_id TEXT, test_id TEXT, status TEXT, response_text TEXT, reported_cost_usd TEXT, request_key TEXT, contract_sha256 TEXT)'))
    db.execute(text("INSERT INTO ac3_attempt_scopes VALUES ('S', :digest, 'active')"), {'digest':digest}); db.commit()
    return db.get_bind(), frozen, digest, mapping, runs


def step(prepared, question, key, provider):
    engine, frozen, digest, mapping, runs = prepared
    with patch('scripts.ac3_database_mapping.compile_mock', side_effect=fake_hosted_compile), patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=fake_hosted_compile), patch('app.services.ac3_fixture_coordinator.compile_mock', side_effect=fake_hosted_compile):
        return run_fixture_step(engine, frozen, digest, '0', mapping, runs, 'S', question, key, provider, request_ceiling_usd='0.01')


def test_two_answers_and_restart_do_not_redo_provider(prepared):
    provider = FixtureProvider()
    assert not step(prepared, 'H0-Q0', 'request-0', provider)['real_provider_called']
    assert not step(prepared, 'H0-Q1', 'request-1', provider)['real_provider_called']
    assert provider.calls == 2
    restarted_provider = FixtureProvider()
    assert step(prepared, 'H0-Q0', 'request-0', restarted_provider)['status'] == 'fixture_completed'
    assert restarted_provider.calls == 0
    with prepared[0].connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM target_responses')).scalar_one() == 2
        assert conn.execute(text('SELECT count(*) FROM evaluation_results')).scalar_one() == 2


def test_billing_mismatch_stops_without_retry(prepared):
    provider = FixtureProvider(reported_cost='0.001', billed_cost='0.002')
    with pytest.raises(ValueError, match='billing mismatch'):
        step(prepared, 'H0-Q0', 'request-0', provider)
    assert provider.calls == 1
    with pytest.raises(ValueError, match='unresolved'):
        step(prepared, 'H0-Q0', 'request-0', provider)
    assert provider.calls == 1


def test_real_entry_disabled():
    with pytest.raises(RuntimeError, match='disabled'):
        disabled_live_runner()


def test_unapproved_fixture_freeze_stops_before_fake_provider(prepared):
    engine, frozen, digest, mapping, runs = prepared
    provider = FixtureProvider()
    with pytest.raises((ValueError, KeyError)):
        run_fixture_step(engine, frozen, digest, '0', mapping, runs, 'S', 'H0-Q0', 'request-0', provider, request_ceiling_usd='0.01')
    assert provider.calls == 0
