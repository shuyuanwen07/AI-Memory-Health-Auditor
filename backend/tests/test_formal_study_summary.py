"""Source-level summaries must not count repeats or uncertain evidence as scenes."""
from statistics import mean
from copy import deepcopy

import pytest
from sqlalchemy import select

from app.models import AuditRunModel, TestCaseModel, TargetResponseModel, EvaluationResultModel
from app.services.formal_study_summary import repeat_variability, summarize
from test_reviewed_acceptance import study as reviewed_study

study = reviewed_study


def test_each_history_is_weighted_once_and_one_history_has_no_interval():
    values = [mean([100, 100, 100]), mean([0, 0, 0])]
    assert summarize(values, 'fixed')['mean_percent'] == 50
    single = summarize([75], 'fixed')
    assert single == {'mean_percent': 75, 'standard_deviation': None, 'interval_low': None, 'interval_high': None}
    assert summarize(values, 'fixed') == summarize(values, 'fixed')
    assert summarize([], 'fixed')['mean_percent'] is None


def test_repeat_variability_is_separate_and_uses_complete_history_repeats():
    assert repeat_variability([[0, 100, 0], [50, 50, 50]], 3) == {
        'complete_repeat_histories': 2,
        'mean_within_history_repeat_standard_deviation': 23.57,
        'notice': ('Mean population standard deviation across each complete history’s planned repeat scores; '
                   'not estimable with fewer than two repeats or no complete histories.'),
    }
    assert repeat_variability([[0]], 1)['mean_within_history_repeat_standard_deviation'] is None


def test_partial_repetition_is_unmeasured_until_every_planned_repeat_is_complete(study):
    client, _, run, _ = study
    response = client.get(f'/api/v1/research/formal/{run}/study-summary')
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['planned_histories'] == 5
    assert report['analysis_plan_recorded'] is True
    assert report['repetitions_per_condition'] == 3
    left, right = report['conditions']
    assert left['mean_percent'] is None
    assert left['measured_runs'] == 1
    assert left['measured_histories'] == 0 and left['missing_histories'] == 5
    assert left['interval_low'] is None
    assert right['mean_percent'] is None and right['missing_histories'] == 5
    assert report['comparisons'][0]['paired_histories'] == 0
    assert report['comparisons'][0]['mean_percent'] is None
    assert len(report['dimension_comparisons']) == 4
    for condition in report['conditions']:
        dimensions = {item['dimension']: item for item in condition['dimension_summaries']}
        assert set(dimensions) == {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'}
        assert all(item['mean_percent'] is None and item['measured_histories'] == 0
                   and item['missing_histories'] == 5 for item in dimensions.values())


@pytest.mark.parametrize('corruption', ['duplicate_assessment', 'wrong_run', 'uncertain'])
def test_bad_or_uncertain_assessments_cannot_enter_the_history_mean(study, corruption):
    client, factory, run, _ = study
    with factory() as db:
        evaluation = db.get(EvaluationResultModel, 'NEW-E0')
        if corruption == 'duplicate_assessment':
            db.add(EvaluationResultModel(id='DUPLICATE',test_id=evaluation.test_id,response_id=evaluation.response_id,passed=True,reason='fixture',evaluator='rule_based'))
        elif corruption == 'wrong_run':
            peer = next(row for row in db.scalars(select(AuditRunModel)) if row.id != run)
            db.get(TargetResponseModel, evaluation.response_id).run_id = peer.id
        else:
            evaluation.passed = None
        db.commit()
    report = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    left = report['conditions'][0]
    assert left['mean_percent'] is None and left['measured_histories'] == 0
    assert left['uncertain_runs' if corruption == 'uncertain' else 'invalid_evidence_runs'] == 1


def test_pairing_uses_only_shared_complete_histories_with_candidate_minus_reference(study):
    client, factory, run, _ = study
    plan = client.get(f'/api/v1/research/formal/{run}/plan').json()
    scenario = plan['scenarios'][0]
    with factory() as db:
        for position, run_id in enumerate(scenario['run_ids']):
            # The first Weak run already has a 75% fixture score. Complete the
            # remaining two Weak repeats at 75%, and all three Strong repeats
            # at 100%, so this history is measured only after every repeat.
            if position == 0:
                continue
            is_weak = position % 2 == 0
            for index, test in enumerate(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id))):
                response_id = f'PAIR-R{position}-{index}'
                db.add(TargetResponseModel(id=response_id,test_id=test.id,run_id=run_id,response_text='fixture',model='fixture',temperature=0))
                db.flush()
                passed = not is_weak or index != 0
                db.add(EvaluationResultModel(id=f'PAIR-E{position}-{index}',test_id=test.id,response_id=response_id,passed=passed,reason='fixture',evaluator='rule_based'))
            db.get(AuditRunModel, run_id).status = 'COMPLETED'
        db.commit()
    report = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    comparison = report['comparisons'][0]
    assert comparison['paired_histories'] == 1 and comparison['missing_pairs'] == 4
    assert comparison['mean_percent'] == 25
    assert comparison['interval_low'] is None
    assert [row['overall_memory_health']['mean_percent'] for row in report['conditions']] == [75, 100]
    assert report['overall_memory_health_comparisons'][0]['mean_percent'] == 25
    dimension_comparisons = {row['dimension']: row for row in report['dimension_comparisons']}
    assert set(dimension_comparisons) == {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'}
    assert dimension_comparisons['accuracy']['mean_percent'] == 100
    assert dimension_comparisons['freshness']['mean_percent'] == 0
    assert dimension_comparisons['conflict_resolution']['mean_percent'] == 0
    assert dimension_comparisons['appropriate_use']['mean_percent'] == 0


def test_summary_reports_within_history_repeat_variability_separately(study):
    client, factory, run, _ = study
    plan = client.get(f'/api/v1/research/formal/{run}/plan').json()
    scenario = plan['scenarios'][0]
    with factory() as db:
        for position, run_id in enumerate(scenario['run_ids']):
            if position == 0:
                continue
            is_weak = position % 2 == 0
            for index, test in enumerate(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id))):
                response_id = f'VAR-R{position}-{index}'
                db.add(TargetResponseModel(id=response_id,test_id=test.id,run_id=run_id,response_text='fixture',model='fixture',temperature=0))
                db.flush()
                passed = not is_weak or index != 0 or position == 2
                db.add(EvaluationResultModel(id=f'VAR-E{position}-{index}',test_id=test.id,response_id=response_id,passed=passed,reason='fixture',evaluator='rule_based'))
            db.get(AuditRunModel, run_id).status = 'COMPLETED'
        db.commit()
    report = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    weak = report['conditions'][0]
    accuracy = next(item for item in weak['dimension_summaries'] if item['dimension'] == 'accuracy')
    assert weak['standard_deviation'] is None  # One scene cannot estimate between-history variation.
    assert weak['primary_repeat_variability']['mean_within_history_repeat_standard_deviation'] == 11.785
    assert weak['overall_memory_health']['repeat_variability']['complete_repeat_histories'] == 1
    assert accuracy['repeat_variability']['mean_within_history_repeat_standard_deviation'] == 47.14


def test_two_repeat_formal_b_plan_is_rejected_even_if_inputs_are_resigned(study):
    from app.services.formal_freeze import formal_input_signature
    client, factory, run, _ = study
    # Keep a self-consistent formal manifest and re-sign its selected inputs;
    # the formal repeat-count rule itself must reject it.
    with factory() as db:
        original = db.get(AuditRunModel, run)
        manifest = deepcopy(original.reproducibility_metadata['formal_matrix_manifest'])
        for scene in manifest['scenarios']:
            scene['run_ids'] = scene['run_ids'][:manifest['condition_count'] * 2]
        manifest['repetition_count'] = 2
        manifest['total_audit_runs'] = sum(len(scene['run_ids']) for scene in manifest['scenarios'])
        manifest['total_target_calls'] = sum(scene['test_count'] * len(scene['run_ids']) for scene in manifest['scenarios'])
        db.flush()
        for scene in manifest['scenarios']:
            for run_id in scene['run_ids']:
                row = db.get(AuditRunModel, run_id)
                metadata = {**row.reproducibility_metadata,
                            'formal_repetition_count': 2,
                            'formal_matrix_manifest': manifest}
                row.reproducibility_metadata = metadata
        db.flush()
        for scene in manifest['scenarios']:
            for run_id in scene['run_ids']:
                row = db.get(AuditRunModel, run_id)
                row.reproducibility_metadata = {**row.reproducibility_metadata,
                                                'formal_input_sha256': formal_input_signature(db, row)}
        db.commit()
    response = client.get(f'/api/v1/research/formal/{run}/study-summary')
    assert response.status_code == 409, response.text
    assert 'at least three repetitions' in response.text


def test_receipt_is_stable_and_survives_export_json_roundtrip(study):
    import json
    from app.services.formal_study_summary import snapshot_digest
    client, _, run, _ = study
    first = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    second = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    assert first == second
    receipt = first.pop('receipt_sha256')
    assert snapshot_digest(json.loads(json.dumps(first))) == receipt
    assert all(len(value) == 64 for key, value in first['provenance'].items() if key.endswith('sha256'))
    assert 'Actual new answer' not in json.dumps(first)


def test_changed_answer_updates_receipt_even_when_score_is_unchanged(study):
    client, factory, run, _ = study
    before = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    with factory() as db:
        db.get(TargetResponseModel, 'NEW-R0').response_text += ' Updated saved evidence.'
        db.commit()
    after = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    assert before['conditions'] == after['conditions']
    assert before['provenance']['frozen_plan_sha256'] == after['provenance']['frozen_plan_sha256']
    assert before['provenance']['evidence_sha256'] != after['provenance']['evidence_sha256']
    assert before['receipt_sha256'] != after['receipt_sha256']


def test_unassessed_attempt_is_bound_without_replacing_the_assessed_answer(study):
    client, factory, run, _ = study
    before = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    with factory() as db:
        original = db.get(TargetResponseModel, 'NEW-R0')
        db.add(TargetResponseModel(id='UNASSESSED',test_id=original.test_id,run_id=run,response_text='Unassessed extra attempt.',model='fixture',temperature=0))
        db.commit()
    after = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    assert before['conditions'] == after['conditions']
    assert before['receipt_sha256'] != after['receipt_sha256']


def test_changed_excluded_assessment_is_still_bound_to_the_receipt(study):
    client, factory, run, _ = study
    with factory() as db:
        original = db.get(EvaluationResultModel, 'NEW-E0')
        db.add(EvaluationResultModel(id='EXCLUDED',test_id=original.test_id,response_id=original.response_id,passed=True,reason='First duplicate decision.',evaluator='rule_based'))
        db.commit()
    before = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    with factory() as db:
        db.get(EvaluationResultModel,'EXCLUDED').reason = 'Changed duplicate decision.'
        db.commit()
    after = client.get(f'/api/v1/research/formal/{run}/study-summary').json()
    assert before['conditions'] == after['conditions']
    assert after['conditions'][0]['invalid_evidence_runs'] == 1
    assert before['receipt_sha256'] != after['receipt_sha256']
