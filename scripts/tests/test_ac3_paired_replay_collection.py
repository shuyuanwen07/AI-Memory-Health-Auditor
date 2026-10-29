"""Synthetic pairing checks; these are not experimental observations."""
import copy
import hashlib
import pytest

from scripts.ac3_paired_replay_collection import collect_paired_replays
from scripts.ac3_retest_paired_freeze import canonical


@pytest.fixture
def documents():
    ids = [f'q{i}' for i in range(120)]
    frozen = {'suite': {'cases': [{'tests': [{'test_id': i} for i in ids]}]},
              'protocol': {'scorer': {'variant': 'hybrid'},
                           'component_sha256': {'old_evaluator': 'a' * 64, 'new_evaluator': 'b' * 64}}}
    frozen_sha = hashlib.sha256(canonical(frozen)).hexdigest()
    answers, replays = [], []
    for ident in ids:
        answer = f'answer {ident}'
        digest = hashlib.sha256(answer.encode()).hexdigest()
        answers.append({'test_id': ident, 'status': 'answered', 'answer': answer})
        old = {'test_id': ident, 'target_answer_sha256': digest, 'evaluator_version_sha256': 'a' * 64,
               'verdict': 'fail', 'failure_type': None}
        new = {**old, 'evaluator_version_sha256': 'b' * 64, 'verdict': 'uncertain'}
        replays.append({'format': 'ac3-paired-single-replay-v1', 'frozen_sha256': frozen_sha,
                        'new_scorer_variant': 'hybrid', 'target_answer_sha256': digest,
                        'old': old, 'new': new, 'model_called': False, 'human_truth_evaluated': False})
    export = {'format': 'ac3-paired-target-export-v1', 'frozen_sha256': frozen_sha,
              'scope': 'synthetic', 'answers': answers}
    return frozen, export, replays


def test_complete_paired_collection(documents):
    result = collect_paired_replays(*documents)
    assert result['integrity']['answer_pairing_verified']
    assert result['integrity']['target_answers'] == 120
    assert result['model_called'] is False


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'answer', 'version', 'variant', 'private_label'])
def test_rejects_incomplete_or_changed_evidence(documents, change):
    frozen, export, replays = copy.deepcopy(documents)
    if change == 'missing': replays.pop()
    elif change == 'duplicate': replays[-1] = copy.deepcopy(replays[0])
    elif change == 'answer': export['answers'][0]['answer'] = 'different'
    elif change == 'version': replays[0]['new']['evaluator_version_sha256'] = 'c' * 64
    elif change == 'variant': replays[0]['new_scorer_variant'] = 'provider_only'
    else: replays[0]['human_truth_evaluated'] = True
    with pytest.raises(ValueError): collect_paired_replays(frozen, export, replays)
