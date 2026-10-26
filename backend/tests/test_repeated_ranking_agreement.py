"""Simulated analysis contracts; these fixtures are not empirical results."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.research.ranking_agreement import RepeatedRankingService
from app.schemas.ranking_agreement import RepeatedRankingRequest
from test_ranking_agreement import package, ranking  # noqa: F401


@pytest.fixture
def repeats(request, monkeypatch):
    db, runs, comparison, body = request.getfixturevalue('ranking')
    trials, comparisons = [], {}
    for index in range(3):
        left_id, right_id = f'before-{index}', f'after-{index}'
        runs.extend([SimpleNamespace(**{**deepcopy(runs[0].__dict__), 'id':left_id}),
                     SimpleNamespace(**{**deepcopy(runs[1].__dict__), 'id':right_id})])
        item = deepcopy(body)
        item.update(reference_run_id=left_id, candidate_run_id=right_id)
        for side in ('reference_benchmark', 'candidate_benchmark'):
            item[side]['evidence']['run_id'] = f'benchmark-repeat-{index}'
        trials.append({'trial_id':f'trial-{index}', 'comparison':item})
        comparisons[left_id] = deepcopy(comparison)
    monkeypatch.setattr('app.research.ranking_agreement.compare_audit_evidence', lambda _db, before, _after: comparisons[before.id])
    return db, {'planned_trial_ids':[row['trial_id'] for row in trials], 'trials':trials}, comparisons


def analyse(repeats):
    return RepeatedRankingService().analyse(repeats[0], RepeatedRankingRequest(**repeats[1]))


def test_complete_repeats_report_agreement_equal_weight_scores_and_variability(repeats):
    report = analyse(repeats)
    assert report.status == 'complete'
    assert (report.planned_trials, report.measured_trials, report.directional_trials) == (3,3,3)
    assert report.ranking_agreement_percentage == 100
    audit, benchmark = report.suites
    assert audit.score_basis == 'dimension_macro_average'
    assert (audit.reference_mean_percentage, audit.candidate_mean_percentage) == (25,50)
    assert audit.reference_standard_deviation == 0
    assert (benchmark.reference_mean_percentage, benchmark.candidate_mean_percentage) == (50,100)
    assert report.plan_provenance == 'caller_declared_analysis_plan'
    assert 'not a verified pre-registration' in report.notice
    repeats[0].add.assert_not_called()
    repeats[0].commit.assert_not_called()


def test_reversed_trials_and_ties_are_not_hidden_in_the_directional_denominator(repeats):
    second = repeats[2]['before-1']['paired_tests']
    for index, pair in enumerate(second):
        pair['before']['passed'] = index < 3
        pair['after']['passed'] = index == 0
    third = repeats[2]['before-2']['paired_tests']
    for index, pair in enumerate(third):
        pair['before']['passed'] = pair['after']['passed'] = index == 0
    repeats[1]['trials'][2]['comparison']['candidate_benchmark']['rows'][1]['autoeval_label']['label'] = False
    report = analyse(repeats)
    assert (report.consistent_trials, report.reversed_trials, report.both_tied_trials) == (1,1,1)
    assert report.directional_trials == 2 and report.ranking_agreement_percentage == 50
    assert report.suites[0].reference_mean_percentage == pytest.approx(41.667)
    assert report.suites[0].candidate_mean_percentage == pytest.approx(33.333)
    assert report.suites[0].reference_standard_deviation > 0


def test_missing_planned_trial_prevents_aggregate_claims_without_discarding_valid_reports(repeats):
    repeats[1]['trials'].pop()
    report = analyse(repeats)
    assert report.status == 'partial'
    assert (report.measured_trials, report.missing_trials) == (2,1)
    assert report.ranking_agreement_percentage is None
    assert all(row.reference_mean_percentage is None and row.ordering == 'unmeasured' for row in report.suites)
    assert report.trials[-1].trial_id == 'trial-2' and report.trials[-1].status == 'missing'
    assert report.trials[0].report is not None


def test_invalid_planned_trial_keeps_error_and_source_run_ids(repeats):
    repeats[1]['trials'][1]['comparison']['candidate_benchmark']['rows'].pop()
    report = analyse(repeats)
    assert report.status == 'partial' and report.invalid_trials == 1
    assert report.ranking_agreement_percentage is None
    failure = report.trials[1]
    assert failure.status == 'invalid' and 'Complete semantic' in failure.reason
    assert failure.reference_run_id == 'before-1'


@pytest.mark.parametrize('change', ['evaluator', 'audit_suite', 'benchmark_settings'])
def test_repeats_with_different_frozen_inputs_cannot_be_combined(repeats, change):
    if change == 'audit_suite':
        repeats[2]['before-1']['paired_tests'][0]['prompt'] = 'A different frozen question.'
    else:
        for side in ('reference_benchmark','candidate_benchmark'):
            item = repeats[1]['trials'][1]['comparison'][side]
            if change == 'evaluator':
                item['evaluator_revision'] = '1'*40
            else:
                item['evidence']['configuration_fingerprint_sha256'] = '1'*64
    report = analyse(repeats)
    assert report.invalid_trials == 1
    assert 'same frozen audit suite' in report.trials[1].reason


def test_declared_plan_fingerprint_binds_execution_ids_but_not_outcome_labels(repeats):
    original = analyse(repeats).plan_fingerprint_sha256
    repeats[1]['trials'][1]['comparison']['candidate_benchmark']['rows'][1]['autoeval_label']['label'] = False
    assert analyse(repeats).plan_fingerprint_sha256 == original
    repeats[1]['trials'][1]['comparison']['reference_run_id'] = 'missing-run'
    changed = analyse(repeats)
    assert changed.plan_fingerprint_sha256 != original and changed.invalid_trials == 1


def test_all_unmeasured_trials_remain_unmeasured(repeats):
    for comparison in repeats[2].values():
        comparison['paired_tests'][-1]['dimension'] = 'accuracy'
    report = analyse(repeats)
    assert report.unmeasured_trials == 3 and report.measured_trials == 0
    assert report.ranking_agreement_percentage is None and report.suites == []
    assert all(row.report.suites[0].dimensions[-1].reference_percentage is None for row in report.trials)


def test_reused_audit_or_benchmark_execution_cannot_inflate_repeat_count(repeats):
    repeats[1]['trials'][1]['comparison']['reference_run_id'] = 'before-0'
    with pytest.raises(ValueError, match='more than one repeated trial'):
        RepeatedRankingRequest(**repeats[1])
    repeats[1]['trials'][1]['comparison']['reference_run_id'] = 'before-1'
    for side in ('reference_benchmark','candidate_benchmark'):
        repeats[1]['trials'][1]['comparison'][side]['evidence']['run_id'] = 'benchmark-repeat-0'
    with pytest.raises(ValueError, match='benchmark execution'):
        analyse(repeats)
    repeats[0].get.assert_not_called()


def test_any_revoked_source_authorisation_prevents_all_analysis(repeats):
    repeats[1]['trials'][2]['comparison']['reference_benchmark']['source_authorised'] = False
    with pytest.raises(ValueError, match='source authorisation'):
        analyse(repeats)
    repeats[0].get.assert_not_called()


def test_empty_plan_evidence_has_only_missing_trials_and_reads_no_saved_data():
    db = Mock()
    report = RepeatedRankingService().analyse(db, RepeatedRankingRequest(
        planned_trial_ids=['t1','t2','t3'],
        trials=[{'trial_id':'t2','unavailable_reason':'No permitted benchmark subset supplied.'}],
    ))
    assert report.missing_trials == 3 and report.status == 'partial'
    assert report.ranking_agreement_percentage is None and report.suites == []
    assert report.model is None
    assert report.trials[1].reason == 'No permitted benchmark subset supplied.'
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_repeated_route_is_read_only_and_returns_missing_trials(repeats):
    from fastapi.testclient import TestClient
    from app.database.session import get_db
    from app.main import app
    repeats[1]['trials'].pop()
    app.dependency_overrides[get_db] = lambda: repeats[0]
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/research/benchmarks/longmemeval/ranking-agreement/repeated',json=repeats[1])
        assert response.status_code == 200
        assert response.json()['missing_trials'] == 1
        assert response.json()['ranking_agreement_percentage'] is None
        repeats[0].commit.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db,None)
