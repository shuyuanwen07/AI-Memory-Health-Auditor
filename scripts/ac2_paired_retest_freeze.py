"""Prepare a reviewed AC2 paired-generator protocol without generating questions.

This is offline preparation only. Two human source reviews are required; the
result does not itself run either generator or validate human identity.
"""
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.prepare_ac3_retest_review_intake import inspect

BASELINE_SOURCE_SHA = '19f96dd187af3fe2c0ab0402279d5eec24468715c85a4336e92f3cba514e2029'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def frozen_digest(frozen):
    return sha(json.dumps(frozen, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())


def prepare(source, plan, reviews, archive, candidate, validator, runtime_signature):
    review = inspect(source, plan, reviews)
    if review.get('all_items_valid_in_both_reviews') is not True:
        raise ValueError('Both source reviews must resolve every item before freeze.')
    if not isinstance(runtime_signature, str) or len(runtime_signature) != 64 or any(c not in '0123456789abcdef' for c in runtime_signature):
        raise ValueError('The shared application runtime signature is required.')
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        matches = [entry for entry in bundle.infolist() if entry.filename == 'app/test_generator/rule_based.py']
        if len(matches) != 1 or matches[0].file_size > 2_000_000:
            raise ValueError('Baseline generator archive member is missing or duplicated.')
        baseline = bundle.read(matches[0])
    if sha(baseline) != BASELINE_SOURCE_SHA or b'VERSION = "rule-based-v35"' not in baseline:
        raise ValueError('Baseline does not match the original v35 source.')
    if b'VERSION = "rule-based-v36"' not in candidate or sha(candidate) == sha(baseline):
        raise ValueError('Candidate must be the distinct v36 generator source.')
    if not validator:
        raise ValueError('The shared quality validator source is required.')
    cases = json.loads(source)['cases']
    return {'format':'ac2-paired-retest-frozen-inputs-v1',
            'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_sha256':sha(source), 'plan_sha256':sha(plan), 'review_sha256':[sha(x) for x in reviews],
            'baseline_archive_sha256':sha(archive), 'baseline_generator_sha256':sha(baseline),
            'candidate_generator_sha256':sha(candidate), 'validator_sha256':sha(validator),
            'freeze_implementation_sha256':sha(Path(__file__).read_bytes()),
            'generation_implementation_sha256':sha(Path(__file__).with_name('ac2_paired_retest_run.py').read_bytes()),
            'adapter_implementation_sha256':sha(Path(__file__).with_name('ac2_paired_retest_adapter.py').read_bytes()),
            'blind_pairing_implementation_sha256':sha((Path(__file__).resolve().parents[1] / 'output/proposal-delivery/ac2-prospective-retest-draft-2026-10-28/blind_pairing.py').read_bytes()),
            'shared_runtime_sha256':runtime_signature,
            'history_ids':[case['history_id'] for case in cases], 'scheduled_questions_per_history':4,
            'selection_policy':'Use all reviewed histories, one deterministic generation per version; retain all missing outputs, exceptions and gate outcomes.',
            'review_policy':'Two independent reviewers judge all generated items blind to version and gate. Preserve uncertain and disagreement.',
            'limitations':'Same current environment for both archived v35 and v36; not a replay of the historical v35 container. Human identity and independence not independently authenticated.',
            'generation_supported':False, 'model_called':False, 'questions_generated':False}
