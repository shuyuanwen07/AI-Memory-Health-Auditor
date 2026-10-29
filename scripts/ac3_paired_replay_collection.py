"""Assemble source-bound paired replays without contacting a model.

Inputs are private exports: the collector checks integrity, but does not itself
verify database locks or establish independent human truth.
"""
import hashlib

from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_paired_integrity import validate_paired_records


def collect_paired_replays(frozen, target_export, replays):
    frozen_sha = hashlib.sha256(canonical(frozen)).hexdigest()
    if (target_export.get('format') != 'ac3-paired-target-export-v1'
            or target_export.get('frozen_sha256') != frozen_sha):
        raise ValueError('Target export does not belong to this frozen study')
    variant = frozen['protocol']['scorer']['variant']
    versions = frozen['protocol']['component_sha256']
    answers = target_export.get('answers')
    if not isinstance(answers, list) or not isinstance(replays, list):
        raise ValueError('Answers and paired replays must be lists')
    ids = [item['test_id'] for item in answers]
    if len(ids) != 120 or len(replays) != 120:
        raise ValueError('All 120 frozen questions need paired replays')
    frozen_ids = [test['test_id'] for case in frozen['suite']['cases'] for test in case['tests']]
    if len(frozen_ids) != 120 or set(ids) != set(frozen_ids):
        raise ValueError('Target export does not cover the frozen questions')
    by_id = {}
    for replay in replays:
        if (replay.get('format') != 'ac3-paired-single-replay-v1'
                or replay.get('frozen_sha256') != frozen_sha
                or replay.get('new_scorer_variant') != variant
                or replay.get('model_called') is not False
                or replay.get('human_truth_evaluated') is not False):
            raise ValueError('Replay is not bound to the frozen protocol')
        old, new = replay.get('old'), replay.get('new')
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise ValueError('Replay must contain both grader outcomes')
        ident = old.get('test_id')
        if ident in by_id or ident != new.get('test_id'):
            raise ValueError('Duplicate or mismatched replay question')
        if (old.get('target_answer_sha256') != replay.get('target_answer_sha256')
                or new.get('target_answer_sha256') != replay.get('target_answer_sha256')):
            raise ValueError('Replay outcomes do not share the recorded answer')
        by_id[ident] = (old, new)
    if set(by_id) != set(ids):
        raise ValueError('Replays do not cover the target answers')
    old_records = [by_id[i][0] for i in ids]
    new_records = [by_id[i][1] for i in ids]
    integrity = validate_paired_records(ids, answers, old_records, new_records,
                                        versions['old_evaluator'], versions['new_evaluator'])
    return {'format': 'ac3-paired-replay-collection-v1', 'frozen_sha256': frozen_sha,
            'scope': target_export.get('scope'), 'new_scorer_variant': variant,
            'old_records': old_records, 'new_records': new_records, 'integrity': integrity,
            'model_called': False, 'human_truth_evaluated': False}
