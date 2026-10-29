"""Pair two scorer callbacks over the exact same saved target answers.

This is a scoring primitive, not an authorized live runner. Its caller must
verify frozen inputs, isolate scorer implementations, enforce any provider
budget and persist all inputs and outputs before drawing conclusions.
"""
import copy
import hashlib
from scripts.ac3_retest_paired_integrity import FAILURE_TYPES, validate_paired_records


def score_saved_answers(items, answers, old_version, new_version, old_score, new_score):
    ids = [item['test_id'] for item in items]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError('Expected a unique, nonempty frozen question list')
    if not isinstance(answers, list) or len(answers) != len(ids):
        raise ValueError('One saved target outcome is required per question')
    answer_map = {}
    for row in answers:
        ident, status, answer = row.get('test_id'), row.get('status'), row.get('answer')
        if ident not in ids or ident in answer_map or status not in ('answered', 'target_error'):
            raise ValueError('Duplicate or invalid saved target outcome')
        if (status == 'answered' and (not isinstance(answer, str) or not answer)) or (status == 'target_error' and answer is not None):
            raise ValueError('Target status and answer disagree')
        answer_map[ident] = answer
    # Reject malformed input or version signatures before invoking any scorer.
    def preflight(version):
        return [{'test_id': ident,
                 'target_answer_sha256': hashlib.sha256(answer_map[ident].encode('utf-8')).hexdigest() if answer_map[ident] is not None else None,
                 'evaluator_version_sha256': version, 'verdict': 'error', 'failure_type': None} for ident in ids]
    validate_paired_records(ids, answers, preflight(old_version), preflight(new_version), old_version, new_version)
    old, new = [], []
    halted_at = None
    for item in items:
        ident = item['test_id']
        answer = answer_map[ident]
        answer_sha = hashlib.sha256(answer.encode('utf-8')).hexdigest() if answer is not None else None
        for side, output, version, scorer in (('old',old,old_version,old_score), ('new',new,new_version,new_score)):
            row = {'test_id': ident, 'target_answer_sha256': answer_sha,
                   'evaluator_version_sha256': version, 'verdict': 'error', 'failure_type': None}
            if halted_at is not None:
                row['error_type'] = 'SkippedAfterPriorScoringError'
            elif answer is None:
                row['error_type'] = 'TargetAnswerMissing'
            else:
                try:
                    result = scorer(copy.deepcopy(item), answer)
                    if not isinstance(result, dict) or result.get('verdict') not in ('pass', 'fail', 'uncertain'):
                        raise ValueError('Scorer returned an invalid result')
                    category=result.get('failure_type')
                    if category is not None and (result['verdict'] != 'fail' or category not in FAILURE_TYPES):
                        raise ValueError('Scorer returned an invalid failure type')
                    row.update(verdict=result['verdict'], failure_type=result.get('failure_type'))
                except Exception as exc:
                    row['error_type'] = type(exc).__name__
                    halted_at = {'test_id':ident,'scorer':side,'error_type':type(exc).__name__}
            output.append(row)
    integrity = validate_paired_records(ids, answers, old, new, old_version, new_version)
    return {'format': 'ac3-paired-saved-answer-scores-v1', 'old': old, 'new': new,
            'integrity': integrity, 'halted_at':halted_at, 'human_truth_evaluated': False,
            'live_runner_authorized': False}
