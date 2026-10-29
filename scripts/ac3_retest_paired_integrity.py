"""Validate paired grader records over one immutable set of target responses.

Offline validation only: no database, model, scoring, study freeze or external
calls. Preserve uncertain, errors and absent classifications as outcomes.
"""
import hashlib
import json
import re

HEX = re.compile(r'^[0-9a-f]{64}$')
FAILURE_TYPES = frozenset({'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'})


def validate_paired_records(test_ids, answers, old_records, new_records, old_version, new_version):
    if (not isinstance(test_ids, list) or not test_ids or len(test_ids) != len(set(test_ids)) or
            any(not isinstance(x, str) or not x for x in test_ids)):
        raise ValueError('Expected a unique, nonempty predeclared test ID list.')
    if (not HEX.fullmatch(old_version or '') or not HEX.fullmatch(new_version or '') or old_version == new_version):
        raise ValueError('Old and new evaluator source signatures must be distinct SHA-256 digests.')
    expected = set(test_ids)
    if not isinstance(answers, list) or len(answers) != len(expected):
        raise ValueError('Every predeclared test must have exactly one saved target outcome.')
    target = {}
    for item in answers:
        ident = item.get('test_id'); answer = item.get('answer'); status = item.get('status')
        if ident not in expected or ident in target or status not in ('answered', 'target_error'):
            raise ValueError('Invalid, duplicate or unknown target record.')
        if status == 'answered' and (not isinstance(answer, str) or not answer):
            raise ValueError('Answered target outcomes need their exact answer text.')
        if status == 'target_error' and answer is not None:
            raise ValueError('Target failures have no answer and cannot be silently substituted.')
        target[ident] = hashlib.sha256(answer.encode('utf-8')).hexdigest() if answer is not None else None
    outputs = []
    for records, version in ((old_records, old_version), (new_records, new_version)):
        if not isinstance(records, list) or len(records) != len(expected):
            raise ValueError('Each grader must report every predeclared item, including failures.')
        seen = set()
        for item in records:
            ident = item.get('test_id'); verdict = item.get('verdict'); category = item.get('failure_type')
            if (ident not in expected or ident in seen or item.get('evaluator_version_sha256') != version or
                    item.get('target_answer_sha256') != target[ident] or
                    verdict not in ('pass', 'fail', 'uncertain', 'error')):
                raise ValueError('Grader item identity, evaluator version, answer digest, or verdict is invalid.')
            if target[ident] is None and verdict != 'error':
                raise ValueError('No target answer exists; both scorer outcomes must record error.')
            if category is not None and (category not in FAILURE_TYPES or verdict != 'fail'):
                raise ValueError('Failure type must be a known category on a failed verdict, or null.')
            seen.add(ident)
        outputs.append(len(seen))
    return {'format': 'ac3-paired-grader-integrity-v1', 'predeclared_tests': len(expected),
            'target_answers': sum(x is not None for x in target.values()),
            'target_errors': sum(x is None for x in target.values()),
            'old_grader_records': outputs[0], 'new_grader_records': outputs[1],
            'old_evaluator_sha256': old_version, 'new_evaluator_sha256': new_version,
            'answer_pairing_verified': True, 'human_truth_evaluated': False,
            'model_called': False, 'run_authorized': False}
