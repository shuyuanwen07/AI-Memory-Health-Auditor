"""Synthetic cost accounting only: no provider, database, ledger or grader calls."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.schemas import AuditRun
from app.schemas.target_profile import TargetMemoryProfile
from app.services.experiment_analytics import ExperimentAnalyticsService, _target_chain_costs


def profile(**kwargs):
    return TargetMemoryProfile(**kwargs)


def primary(**kwargs):
    return {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15, 'latency_ms': 100, **kwargs}


def stage(**kwargs):
    return {'request_attempts': 1, 'reported_input_tokens': 4, 'reported_output_tokens': 2,
            'reported_total_tokens': 6, 'elapsed_ms': 30, **kwargs}


def summarize(rows, selected_profile=None):
    run = AuditRun(run_id='R-COST', conversation_id='C-COST', status='COMPLETED',
        target_configuration='strong', provider='openrouter', model='openai/gpt-6-luna',
        temperature=0, random_seed=42, test_budget=1, prompt_template_version='cost-test',
        created_at=datetime(2027, 1, 1, tzinfo=timezone.utc), memory_strategy='strong_rule_based',
        target_memory_profile=selected_profile or profile())
    result = SimpleNamespace(dimensions=[], overall_score=100, tests_passed=1, tests_total=1, failures=[])
    return ExperimentAnalyticsService().condition_summaries([run], {run.run_id: result}, {run.run_id: rows})[0]


def test_primary_identity_and_validation_count_each_actual_role_once_not_ledger_copies():
    row = primary(identity_analysis={'status': 'analyzed', 'execution': stage()},
                  answer_validation={'decision': 'corrected', 'execution': stage()},
                  target_answer_draft={'execution': stage(reported_total_tokens=99999)})
    costs = _target_chain_costs(row, profile(identity_analysis='evidence_links', answer_validation='source_grounding'))
    assert costs == {'has_additional_stage': True, 'input_tokens': 18, 'output_tokens': 9,
                     'total_tokens': 27, 'latency_ms': 160}
    summary = summarize([row], profile(identity_analysis='evidence_links', answer_validation='source_grounding'))
    assert (summary.total_input_tokens, summary.total_output_tokens, summary.total_tokens) == (18, 9, 27)
    assert summary.mean_latency_ms == 160


def test_failed_identity_continuation_still_counts_reported_usage_and_actual_retries_once():
    row = primary(identity_analysis={'status': 'degraded_without_advisory',
                  'execution': stage(status='failed', request_attempts=2, failed_http_attempts=1)})
    costs = _target_chain_costs(row, profile(identity_analysis='evidence_links'))
    assert costs['total_tokens'] == 21  # receipt totals already represent this role; don't multiply attempts
    assert costs['latency_ms'] == 130


@pytest.mark.parametrize('key', ['input_tokens', 'output_tokens', 'total_tokens'])
def test_missing_required_stage_usage_is_unknown_for_that_metric(key):
    execution = stage()
    execution.pop('reported_' + key)
    row = primary(answer_validation={'decision': 'supported', 'execution': execution})
    summary = summarize([row], profile(answer_validation='source_grounding'))
    field = {'input_tokens': 'total_input_tokens', 'output_tokens': 'total_output_tokens', 'total_tokens': 'total_tokens'}[key]
    assert getattr(summary, field) is None
    assert summary.mean_latency_ms == 130


@pytest.mark.parametrize('metadata', [None, {}, {'decision': 'supported'}, {'execution': None}])
def test_required_validation_missing_receipt_is_unknown_not_free(metadata):
    row = primary(answer_validation=metadata)
    summary = summarize([row], profile(answer_validation='source_grounding'))
    assert summary.total_tokens is None and summary.mean_latency_ms is None


def test_identity_legal_skip_has_zero_additional_cost_but_not_unknown_missing_identity():
    row = primary(identity_analysis={'status': 'skipped_not_applicable', 'request_attempts': 0})
    summary = summarize([row], profile(identity_analysis='evidence_links'))
    assert summary.total_tokens == 15 and summary.mean_latency_ms == 100
    assert summarize([primary()], profile(identity_analysis='evidence_links')).total_tokens is None


@pytest.mark.parametrize('metadata', [
    {'status': 'skipped_not_applicable'},
    {'status': 'skipped_not_applicable', 'request_attempts': 1},
    {'status': 'skipped_not_applicable', 'request_attempts': False},
    {'status': 'unknown'},
])
def test_unproven_skip_never_becomes_zero(metadata):
    summary = summarize([primary(identity_analysis=metadata)], profile(identity_analysis='evidence_links'))
    assert summary.total_tokens is None and summary.mean_latency_ms is None


@pytest.mark.parametrize('elapsed', [None, float('nan'), -1, True])
def test_missing_or_invalid_aux_latency_makes_pipeline_latency_unknown(elapsed):
    row = primary(answer_validation={'execution': stage(elapsed_ms=elapsed)})
    summary = summarize([primary(answer_validation={'execution': stage()}), row],
                        profile(answer_validation='source_grounding'))
    assert summary.total_tokens == 42
    assert summary.mean_latency_ms is None


def test_legacy_primary_only_original_summaries_preserved():
    rows = [primary(), primary(input_tokens=20, total_tokens=25, latency_ms=None)]
    summary = summarize(rows)
    assert summary.total_input_tokens == 30 and summary.total_output_tokens == 10 and summary.total_tokens == 40
    assert summary.mean_latency_ms == 100  # original available-primary averaging
    assert summarize([primary(total_tokens=None)]).total_tokens is None


def test_observed_additional_receipt_counts_even_if_profile_no_longer_requires_it():
    summary = summarize([primary(answer_validation={'execution': stage()})])
    assert summary.total_tokens == 21 and summary.mean_latency_ms == 130


def test_known_zero_provider_reported_usage_not_confused_with_missing():
    summary = summarize([primary(answer_validation={'execution': stage(reported_input_tokens=0,
        reported_output_tokens=0, reported_total_tokens=0, elapsed_ms=0)})], profile(answer_validation='source_grounding'))
    assert summary.total_tokens == 15 and summary.mean_latency_ms == 100


def test_scope_excludes_auditor_and_generation_and_states_draft_deduplication():
    scope = ExperimentAnalyticsService.analysis_metadata()['cost_scope']
    assert 'Excludes auditor' in scope and 'copied draft ledger' in scope
    summary = summarize([primary(grader={'execution': stage()}, generator={'execution': stage()})])
    assert summary.total_tokens == 15
