"""Export blind review materials from an independently hash-bound AC3 run.

This exporter never executes a model, reads the production DB or creates human
judgments. Its run export is an explicit prerequisite, not proof that a real
provider execution exists. Private answer/run files and the identity key must
not be shared with reviewers. The run export itself must be retained unchanged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_ac3_heldout import _read_bound, _time
from scripts.ac3_fixed_suite_adapter import compile_mock, mock_reservation_for_suite


def make_materials(frozen_path, frozen_digest, run_path, run_digest):
    frozen = _read_bound(frozen_path, frozen_digest)
    run = _read_bound(run_path, run_digest)
    if run.get('format') != 'ac3-heldout-run-export-v1' or run.get('frozen_sha256') != frozen_digest:
        raise ValueError('Run does not bind to the frozen protocol')
    if Path(run.get('frozen_path', '')).resolve() != Path(frozen_path).resolve():
        raise ValueError('Run points to a different frozen source')
    if _time(run['started_at_utc']) <= _time(frozen['frozen_at_utc']):
        raise ValueError('The recorded run must begin after protocol freeze')
    reservation = mock_reservation_for_suite(frozen)
    stage = compile_mock(Path(frozen_path), frozen_digest, reservation)
    eligible = {row['test_id']: row for row in stage['items'] if row['grounding_review'] == 'valid'}
    source_histories = {case['history_id']: [message['text'] for message in case['source_messages']]
                        for case in frozen['suite']['cases']}
    responses = run.get('responses')
    if not isinstance(responses, list) or len(responses) != len(eligible):
        raise ValueError('Exactly one saved answer per valid question is required')
    key, cases, seen = {}, [], set()
    for row in responses:
        test_id = row['test_id']
        if test_id in seen or test_id not in eligible or row['history_id'] != eligible[test_id]['history_id']:
            raise ValueError('Unknown, duplicate or mismatched saved answer')
        response = row.get('response')
        if not isinstance(response, str) or not response.strip() or hashlib.sha256(response.encode()).hexdigest() != row.get('response_sha256'):
            raise ValueError('Response content digest mismatch')
        seen.add(test_id)
        blind = secrets.token_hex(16)
        while blind in key: blind = secrets.token_hex(16)
        key[blind] = test_id
        test = eligible[test_id]
        cases.append({'blind_id': blind, 'question': test['question'],
                      'source_history': source_histories[test['history_id']],
                      'expected_behavior': test['expected_behavior'], 'answer': response,
                      'response_sha256': row['response_sha256']})
    if seen != set(eligible): raise ValueError('Incomplete run coverage')
    # Random ordering and random IDs conceal original test order and identity.
    secrets.SystemRandom().shuffle(cases)
    private = {'format': 'ac3-heldout-blind-key-v1', 'frozen_sha256': frozen_digest,
               'run_sha256': run_digest, 'blind_to_test': key}
    packet = {'format': 'ac3-heldout-blind-packet-v1', 'run_sha256': run_digest,
              'instructions': 'Review independently without seeing automated scores or the other review. Do not infer a score from labels. Record uncertain when judgment is not possible.',
              'cases': cases}
    templates = []
    for slot in (1, 2):
        templates.append({'format': 'ac3-heldout-human-review-v1', 'reviewer_slot': slot,
          'run_sha256': run_digest, 'reviewer_declaration': {'reviewer_label': '', 'completed_by_human': False,
          'completed_independently': False, 'has_seen_automatic_results': None, 'used_ai_assistance': None},
          'decisions': [{'blind_id': c['blind_id'], 'response_sha256': c['response_sha256'],
                         'verdict': None, 'failure_dimension': None, 'rationale': ''} for c in cases]})
    return private, packet, *templates


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('frozen', 'run'):
        p.add_argument('--' + name, type=Path, required=True)
        p.add_argument('--' + name + '-sha256', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    materials = make_materials(a.frozen, a.frozen_sha256, a.run, a.run_sha256)
    if a.output_dir.exists(): raise FileExistsError('Refusing to overwrite existing review materials')
    a.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.ac3-review-', dir=a.output_dir.parent))
    try:
        for name, data in zip(('private-key.json', 'blind-packet.json', 'reviewer-1.json', 'reviewer-2.json'), materials):
            path = temp / name
            with path.open('x') as stream:
                os.chmod(path, 0o600)
                json.dump(data, stream, ensure_ascii=False, indent=2); stream.write('\n')
        # Recheck inputs before releasing review materials.
        _read_bound(a.frozen, a.frozen_sha256); _read_bound(a.run, a.run_sha256)
        os.rename(temp, a.output_dir)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    print(json.dumps({'status': 'awaiting_independent_human_reviews', 'directory': str(a.output_dir),
                      'notice': 'Keep private-key.json and run export private; distribute only blind packet and respective blank template.'}))


if __name__ == '__main__': main()
