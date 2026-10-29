"""Validate and adapt paired AC2 raw output for the draft blind-review tool.

This adapter is preparation only: it does not freeze a protocol, write packets,
make reviewer decisions, or assert that a study is ready to run.
"""
import hashlib
import json
from pathlib import Path
from scripts.ac2_paired_retest_freeze import frozen_digest


def review_source(source_bytes, plan_bytes, frozen):
    """Attach the exact reviewed facts and relationships to each blind history."""
    if (hashlib.sha256(source_bytes).hexdigest() != frozen.get('source_sha256')
            or hashlib.sha256(plan_bytes).hexdigest() != frozen.get('plan_sha256')):
        raise ValueError('Review source or reference plan differs from frozen inputs')
    source = json.loads(source_bytes)
    references = json.loads(plan_bytes)['histories']
    ids = [case['history_id'] for case in source['cases']]
    if ids != frozen.get('history_ids') or len(set(ids)) != len(ids) or set(ids) != set(references):
        raise ValueError('Reference plan does not cover the frozen histories')
    return {'cases': [{'history_id': case['history_id'], 'source_messages': case['source_messages'],
                       'reviewed_reference': references[case['history_id']]} for case in source['cases']]}


def adapt(source_bytes, frozen, output):
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if (frozen.get('format') != 'ac2-paired-retest-frozen-inputs-v1'
            or output.get('format') != 'ac2-paired-generation-output-v1'
            or frozen.get('source_sha256') != source_sha
            or output.get('source_sha256') != source_sha
            or output.get('frozen_protocol_sha256') != frozen_digest(frozen)
            or output.get('frozen_at_utc') != frozen.get('frozen_at_utc')
            or output.get('baseline_sha256') != frozen.get('baseline_generator_sha256')
            or output.get('candidate_sha256') != frozen.get('candidate_generator_sha256')
            or output.get('model_called') is not False
            or output.get('database_written') is not False):
        raise ValueError('Generation output does not match the frozen inputs')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != frozen.get('adapter_implementation_sha256'):
        raise ValueError('Adapter implementation changed after freeze')
    source = json.loads(source_bytes)
    ids = [case['history_id'] for case in source['cases']]
    if not ids or len(ids) != len(set(ids)) or ids != frozen.get('history_ids'):
        raise ValueError('History set does not match frozen inputs')
    if frozen.get('scheduled_questions_per_history') != 4:
        raise ValueError('Unexpected scheduled question count')
    conditions = output.get('conditions', {})
    if set(conditions) != {'baseline', 'candidate'}:
        raise ValueError('Exactly two conditions are required')
    runs, ledger = {}, {}
    for side in ('baseline', 'candidate'):
        histories = conditions[side]
        if not isinstance(histories, list) or [row.get('history_id') for row in histories] != ids:
            raise ValueError('History coverage or ordering differs from frozen inputs')
        runs[side], ledger[side] = {}, {}
        for row in histories:
            hid, tests = row['history_id'], row.get('tests')
            if not isinstance(tests, list) or len(tests) > 4 or row.get('generated_count') != len(tests) or row.get('missing_slots') != 4-len(tests):
                raise ValueError('Invalid generation count or missing-slot ledger')
            if row.get('status') == 'error':
                if tests or not row.get('error_type'):
                    raise ValueError('Invalid generation error record')
            elif row.get('status') != 'completed':
                raise ValueError('Unknown generation status')
            converted = []
            for item in tests:
                test, quality = item['test'], item['quality_assessment']
                gate = quality.get('quality_status')
                if gate not in ('accepted', 'rejected', 'pending'):
                    raise ValueError('Unknown product gate status')
                converted.append({'prompt': test['prompt'], 'expected_behavior': test['expected_behavior'],
                                  'gate_status': 'uncertain' if gate == 'pending' else gate})
            runs[side][hid] = converted
            ledger[side][hid] = {'status': row['status'], 'generated_count': len(tests),
                                  'missing_slots': row['missing_slots'],
                                  'suite_problem': row.get('suite_problem'),
                                  'suite_validation_error_type': row.get('suite_validation_error_type'),
                                  'error_type': row.get('error_type')}
    return runs, ledger
