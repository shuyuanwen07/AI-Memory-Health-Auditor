"""Read-only descriptive statistics with source histories as sampling units."""
from collections import defaultdict
from itertools import combinations
from random import Random
from statistics import mean, pstdev, stdev
import hashlib
import json
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.models import AuditRunModel, TestCaseModel, EvaluationResultModel, TargetResponseModel, MessageModel
from app.schemas.domain import Dimension
from app.services.formal_matrix import FormalSyntheticMatrixService
from app.services.formal_freeze import formal_runtime_signature


def snapshot_digest(value):
    """Stable checksums across JSON round trips; not digital signatures."""
    def normalize(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, dict):
            return {key: normalize(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(value) for value in item]
        if isinstance(item, datetime):
            return item.replace(tzinfo=item.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        return item
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def summarize(values, seed):
    """Bootstrap histories, never their individual answers or questions."""
    if not values:
        return {'mean_percent': None, 'standard_deviation': None, 'interval_low': None, 'interval_high': None}
    low = high = None
    if len(values) >= 2:
        random = Random(seed)
        samples = sorted(mean(random.choices(values, k=len(values))) for _ in range(2000))
        low, high = samples[49], samples[1949]
    return {'mean_percent': round(mean(values), 3),
            'standard_deviation': round(stdev(values), 3) if len(values) >= 2 else None,
            'interval_low': round(low, 3) if low is not None else None,
            'interval_high': round(high, 3) if high is not None else None}


def repeat_variability(per_history_scores, repetitions):
    """Summarise within-history run variation, keeping histories as the unit."""
    complete = [values for values in per_history_scores if len(values) == repetitions]
    deviations = [pstdev(values) for values in complete] if repetitions >= 2 else []
    return {
        'complete_repeat_histories': len(complete),
        'mean_within_history_repeat_standard_deviation': round(mean(deviations), 3) if deviations else None,
        'notice': ('Mean population standard deviation across each complete history’s planned repeat scores; '
                   'not estimable with fewer than two repeats or no complete histories.'),
    }


def study_summary(db, run_id):
    plan = FormalSyntheticMatrixService().restore(db, run_id)
    ids = [run for scene in plan.scenarios for run in scene.run_ids]
    runs, tests, evaluations, responses, messages = {}, defaultdict(list), defaultdict(list), {}, defaultdict(list)
    for start in range(0, len(ids), 200):
        batch = ids[start:start + 200]
        runs.update({row.id: row for row in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(batch)))})
        for test in db.scalars(select(TestCaseModel).where(TestCaseModel.run_id.in_(batch))):
            tests[test.run_id].append(test)
        for evaluation in db.scalars(select(EvaluationResultModel).join(TestCaseModel).where(TestCaseModel.run_id.in_(batch))):
            evaluations[evaluation.test_id].append(evaluation)
        responses.update({row.id: row for row in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id.in_(batch)))})
    conversation_ids = list({run.conversation_id for run in runs.values()})
    for start in range(0, len(conversation_ids), 200):
        for row in db.scalars(select(MessageModel).where(MessageModel.conversation_id.in_(conversation_ids[start:start + 200])).order_by(MessageModel.sequence, MessageModel.id)):
            messages[row.conversation_id].append(row)
    # Older exploratory matrices may contain duplicated histories. Refuse to
    # count renamed copies as distinct units in this across-history view.
    fingerprints = []
    for scene in plan.scenarios:
        history = messages[runs[scene.run_ids[0]].conversation_id]
        normalized = [( ' '.join(unicodedata.normalize('NFKC', row.role).casefold().split()),
                        ' '.join(unicodedata.normalize('NFKC', row.content).casefold().split())) for row in history]
        fingerprints.append(hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest())
    if len(set(fingerprints)) != len(fingerprints):
        raise HTTPException(409, 'This plan repeats conversation content. Its results remain available by scene, but copies cannot count as distinct histories.')
    design = plan.acceptance_protocol.study_design
    primary = design.primary_outcome if design else 'overall_memory_health'
    relevant = [dimension.value for dimension in Dimension] if primary == 'overall_memory_health' else [primary]
    condition_rows = []
    per_condition = []
    per_overall_condition = []
    per_dimension_condition: dict[str, list[dict[int, float]]] = {
        dimension.value: [] for dimension in Dimension
    }
    for index in range(plan.condition_count):
        scene_scores, complete_runs, measured_runs, invalid_runs, uncertain_runs = {}, 0, 0, 0, 0
        scene_repeat_values = {}
        overall_scene_scores = {}
        overall_repeat_values = {}
        dimension_scene_scores = {dimension.value: {} for dimension in Dimension}
        dimension_repeat_values = {dimension.value: {} for dimension in Dimension}
        dimension_measured_runs = {dimension.value: 0 for dimension in Dimension}
        dimension_invalid_runs = {dimension.value: 0 for dimension in Dimension}
        dimension_uncertain_runs = {dimension.value: 0 for dimension in Dimension}
        exemplar = runs[plan.scenarios[0].run_ids[index]]
        for scene_index, scene in enumerate(plan.scenarios):
            repeat_scores = []
            overall_repeat_scores = []
            dimension_repeat_scores = {dimension.value: [] for dimension in Dimension}
            canonical_tests = tests[scene.run_ids[0]]
            expected_dimension_counts = {
                dimension.value: sum(test.dimension == dimension.value for test in canonical_tests)
                for dimension in Dimension
            }
            for position in range(index, len(scene.run_ids), plan.condition_count):
                run = runs[scene.run_ids[position]]
                settings = ('provider', 'model', 'memory_strategy', 'temperature', 'random_seed', 'pipeline_provider', 'pipeline_model', 'semantic_review_provider', 'semantic_review_model', 'evaluator_provider', 'evaluator_model', 'retrieval_mode', 'retrieval_provider', 'retrieval_model', 'memory_maintenance_policy', 'target_memory_writer', 'target_memory_capacity', 'prompt_template_version', 'target_system_adapter')
                if tuple(getattr(run, field) for field in settings) != tuple(getattr(exemplar, field) for field in settings):
                    raise HTTPException(409, 'Conditions do not retain the same model and settings across the saved scenes.')
                if run.status != 'COMPLETED':
                    continue
                complete_runs += 1
                scores = defaultdict(list)
                valid = len(tests[run.id]) == scene.test_count
                uncertain = False
                dimension_test_counts = defaultdict(int)
                dimension_invalid = set()
                dimension_uncertain = set()
                for test in tests[run.id]:
                    dimension = test.dimension
                    dimension_test_counts[dimension] += 1
                    entries = evaluations[test.id]
                    if len(entries) != 1:
                        valid = False
                        dimension_invalid.add(dimension)
                        continue
                    evaluation = entries[0]
                    response = responses.get(evaluation.response_id)
                    if response is None or response.test_id != test.id or response.run_id != run.id:
                        valid = False
                        dimension_invalid.add(dimension)
                        continue
                    if evaluation.passed is None:
                        dimension_uncertain.add(dimension)
                        if dimension in relevant:
                            uncertain = True
                    else:
                        scores[dimension].append(100.0 if evaluation.passed else 0.0)
                for dimension in Dimension:
                    key = dimension.value
                    if dimension_test_counts[dimension] != expected_dimension_counts[key]:
                        dimension_invalid.add(dimension)
                    if not dimension_test_counts[dimension]:
                        continue
                    if key in dimension_invalid:
                        dimension_invalid_runs[key] += 1
                    elif key in dimension_uncertain:
                        dimension_uncertain_runs[key] += 1
                    elif scores[dimension]:
                        dimension_repeat_scores[key].append(mean(scores[dimension]))
                        dimension_measured_runs[key] += 1
                run_dimension_scores = {
                    dimension.value: mean(scores[dimension])
                    for dimension in Dimension
                    if dimension_test_counts[dimension]
                    and dimension not in dimension_invalid
                    and dimension not in dimension_uncertain
                    and scores[dimension]
                }
                if all(dimension.value in run_dimension_scores for dimension in Dimension):
                    overall_repeat_scores.append(mean([run_dimension_scores[dimension.value] for dimension in Dimension]))
                if not valid:
                    invalid_runs += 1
                elif uncertain:
                    uncertain_runs += 1
                elif all(scores[dimension] for dimension in relevant):
                    repeat_scores.append(mean(mean(scores[dimension]) for dimension in relevant))
                    measured_runs += 1
            # Do not select just successful/available repetitions of a history.
            if len(repeat_scores) == plan.repetition_count:
                scene_scores[scene_index] = mean(repeat_scores)
                scene_repeat_values[scene_index] = repeat_scores
            if len(overall_repeat_scores) == plan.repetition_count:
                overall_scene_scores[scene_index] = mean(overall_repeat_scores)
                overall_repeat_values[scene_index] = overall_repeat_scores
            for dimension in Dimension:
                key = dimension.value
                if len(dimension_repeat_scores[key]) == plan.repetition_count:
                    dimension_scene_scores[key][scene_index] = mean(dimension_repeat_scores[key])
                    dimension_repeat_values[key][scene_index] = dimension_repeat_scores[key]
        condition_rows.append({'condition_index': index + 1, 'provider': exemplar.provider, 'model': exemplar.model,
                               'memory_strategy': exemplar.memory_strategy, 'planned_runs': plan.scenario_count * plan.repetition_count,
                               'completed_runs': complete_runs, 'measured_runs': measured_runs,
                               'invalid_evidence_runs': invalid_runs, 'uncertain_runs': uncertain_runs,
                               'measured_histories': len(scene_scores), 'missing_histories': plan.scenario_count - len(scene_scores),
                               'primary_repeat_variability': repeat_variability(
                                   list(scene_repeat_values.values()), plan.repetition_count),
                               'overall_memory_health': {
                                   'measured_histories': len(overall_scene_scores),
                                   'missing_histories': plan.scenario_count - len(overall_scene_scores),
                                   'repeat_variability': repeat_variability(
                                       list(overall_repeat_values.values()), plan.repetition_count),
                                   **summarize(
                                       list(overall_scene_scores.values()),
                                       f'{plan.dataset_fingerprint_sha256}:overall_memory_health:{index}',
                                   ),
                               },
                               'dimension_summaries': [{
                                   'dimension': dimension.value,
                                   'planned_runs': plan.scenario_count * plan.repetition_count,
                                   'completed_runs': sum(
                                       runs[run_id].status == 'COMPLETED'
                                       for scene in plan.scenarios
                                       for run_id in scene.run_ids[index::plan.condition_count]
                                   ),
                                   'measured_runs': dimension_measured_runs[dimension.value],
                                   'invalid_evidence_runs': dimension_invalid_runs[dimension.value],
                                   'uncertain_runs': dimension_uncertain_runs[dimension.value],
                                   'measured_histories': len(dimension_scene_scores[dimension.value]),
                                   'missing_histories': plan.scenario_count - len(dimension_scene_scores[dimension.value]),
                                   'repeat_variability': repeat_variability(
                                       list(dimension_repeat_values[dimension.value].values()), plan.repetition_count),
                                   **summarize(
                                       list(dimension_scene_scores[dimension.value].values()),
                                       f'{plan.dataset_fingerprint_sha256}:{dimension.value}:{index}',
                                   ),
                               } for dimension in Dimension],
                               **summarize(list(scene_scores.values()), f'{plan.dataset_fingerprint_sha256}:{primary}:{index}')})
        per_condition.append(scene_scores)
        per_overall_condition.append(overall_scene_scores)
        for dimension in Dimension:
            per_dimension_condition[dimension.value].append(dimension_scene_scores[dimension.value])
    comparisons = []
    for left, right in combinations(range(plan.condition_count), 2):
        shared = sorted(set(per_condition[left]) & set(per_condition[right]))
        differences = [per_condition[right][scene] - per_condition[left][scene] for scene in shared]
        comparisons.append({'reference_condition': left + 1, 'candidate_condition': right + 1,
                            'paired_histories': len(shared), 'missing_pairs': plan.scenario_count - len(shared),
                            **summarize(differences, f'{plan.dataset_fingerprint_sha256}:{primary}:{left}:{right}')})
    overall_comparisons = []
    for left, right in combinations(range(plan.condition_count), 2):
        left_scores = per_overall_condition[left]
        right_scores = per_overall_condition[right]
        shared = sorted(set(left_scores) & set(right_scores))
        differences = [right_scores[scene] - left_scores[scene] for scene in shared]
        overall_comparisons.append({
            'reference_condition': left + 1,
            'candidate_condition': right + 1,
            'paired_histories': len(shared),
            'missing_pairs': plan.scenario_count - len(shared),
            **summarize(differences, f'{plan.dataset_fingerprint_sha256}:overall_memory_health:{left}:{right}'),
        })
    dimension_comparisons = []
    for left, right in combinations(range(plan.condition_count), 2):
        for dimension in Dimension:
            left_scores = per_dimension_condition[dimension.value][left]
            right_scores = per_dimension_condition[dimension.value][right]
            shared = sorted(set(left_scores) & set(right_scores))
            differences = [right_scores[scene] - left_scores[scene] for scene in shared]
            dimension_comparisons.append({
                'dimension': dimension.value,
                'reference_condition': left + 1,
                'candidate_condition': right + 1,
                'paired_histories': len(shared),
                'missing_pairs': plan.scenario_count - len(shared),
                **summarize(differences, f'{plan.dataset_fingerprint_sha256}:{dimension.value}:{left}:{right}'),
            })
    report = {'version': 'source-history-summary-v3', 'primary_outcome': primary, 'analysis_plan_recorded': design is not None,
            'planned_histories': plan.scenario_count, 'repetitions_per_condition': plan.repetition_count,
            'conditions': condition_rows, 'comparisons': comparisons,
            'overall_memory_health_comparisons': overall_comparisons,
            'dimension_comparisons': dimension_comparisons,
            'notice': 'Automated judgments of saved answers. Each history is equally weighted after averaging all planned repeats; incomplete histories are reported without scores. Intervals are descriptive 95% history bootstrap intervals for measured histories only, absent with fewer than two histories. Zero-width intervals do not prove certainty. Distinct text does not prove independent sources. This does not establish auditor validity or independent human agreement.'}
    def row_data(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
    evidence = {
        'runs': [{'run_id': identity, 'status': runs[identity].status,
                  'formal_input_sha256': runs[identity].reproducibility_metadata.get('formal_input_sha256')} for identity in sorted(runs)],
        'responses': [row_data(responses[identity]) for identity in sorted(responses)],
        'assessments': [row_data(row) for row in sorted((row for entries in evaluations.values() for row in entries), key=lambda row: row.id)],
    }
    report['provenance'] = {
        'dataset_fingerprint_sha256': plan.dataset_fingerprint_sha256,
        'frozen_plan_sha256': snapshot_digest(runs[run_id].reproducibility_metadata['formal_matrix_manifest']),
        'evidence_sha256': snapshot_digest(evidence),
        'analysis_runtime_source_sha256': formal_runtime_signature()['source_sha256'],
        'notice': 'Checksums identify saved inputs, recorded answers (including excluded attempts), judgments and analysis software. They do not verify authorship, independent human evidence or authenticity of an externally edited export.',
    }
    report['receipt_sha256'] = snapshot_digest(report)
    return report


def verify_study_export(db, run_id, imported):
    """Compare a self-consistent export with authoritative current saved data."""
    def result(status, message):
        return {'status': status, 'matches_current_snapshot': status == 'matches_current_snapshot', 'message': message}
    provenance = imported.get('provenance')
    receipt = imported.get('receipt_sha256')
    if imported.get('version') not in {'source-history-summary-v2', 'source-history-summary-v3'} or not isinstance(provenance, dict) or not isinstance(receipt, str) or len(receipt) != 64:
        return result('unsupported_file', 'This file has no supported scene-comparison receipt. Download a new scene comparison.')
    content = dict(imported)
    content.pop('receipt_sha256')
    try:
        calculated = snapshot_digest(content)
    except (ValueError, TypeError, RecursionError) as error:
        raise HTTPException(422, 'This comparison file contains unsupported data. Upload the original downloaded JSON.') from error
    if calculated != receipt:
        return result('file_checksum_mismatch', 'The file contents do not match their recorded checksum. Upload the original export or download a new comparison.')
    current = study_summary(db, run_id)
    saved = current['provenance']
    if provenance.get('frozen_plan_sha256') != saved['frozen_plan_sha256']:
        return result('different_plan', 'This file belongs to a different experiment plan. Restore the matching plan or use its own export.')
    if provenance.get('evidence_sha256') != saved['evidence_sha256']:
        return result('saved_evidence_changed', 'The saved answers, judgments or run progress have changed since this export. Refresh and download the current comparison.')
    if provenance.get('analysis_runtime_source_sha256') != saved['analysis_runtime_source_sha256']:
        return result('analysis_changed', 'The installed analysis software differs from the export. Refresh to see the current analysis; the original file remains a historical snapshot.')
    if receipt != current['receipt_sha256']:
        return result('result_values_differ', 'The exported results differ from the current calculation, even though its declared evidence checksums match. Download the current comparison.')
    return result('matches_current_snapshot', 'The file matches the current saved evidence and analysis. This does not certify complete runs, independent human labels or research conclusions.')
