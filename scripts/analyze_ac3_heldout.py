"""Compute a descriptive AC3 comparison from hash-bound future study exports.

No execution or reviewer data is produced by this script. The output is not a
formal pass claim: source-clock integrity, identities and blind independence
must be independently evaluated, and the actual runtime adapter must emit the
specified export format. Expected digests must be retained independently.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.ac3_metrics import calculate, history_bootstrap
from scripts.ac3_fixed_suite_adapter import compile_mock, mock_reservation_for_suite


def _read_bound(path, digest):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Evidence must be an existing regular file')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Evidence digest mismatch')
    return json.loads(raw)


def _time(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return date.astimezone(timezone.utc)


def _declaration(document, slot):
    d = document.get('reviewer_declaration', {})
    name = d.get('reviewer_label')
    if document.get('reviewer_slot') != slot or not isinstance(name, str) or not name.strip():
        raise ValueError('Review slot or reviewer label is missing')
    if d.get('completed_by_human') is not True or d.get('completed_independently') is not True or d.get('has_seen_automatic_results') is not False or not isinstance(d.get('used_ai_assistance'), bool):
        raise ValueError('Each reviewer must explicitly attest to independent blind human review')
    return unicodedata.normalize('NFKC', name).strip().casefold()


def analyze(frozen, frozen_digest, run, blind_key, reviews):
    if run.get('format') != 'ac3-heldout-run-export-v1' or run.get('frozen_sha256') != frozen_digest:
        raise ValueError('Run does not bind to the frozen protocol')
    if _time(run['started_at_utc']) <= _time(frozen['frozen_at_utc']):
        raise ValueError('The recorded run must begin after protocol freeze')
    config = frozen['protocol']
    reservation = mock_reservation_for_suite(frozen)
    stage = compile_mock(Path(run['frozen_path']), frozen_digest, reservation)
    tests = {r['test_id']: r for r in stage['items']}
    eligible = {k for k, v in tests.items() if v['grounding_review'] == 'valid'}
    entries = run.get('responses')
    if not isinstance(entries, list) or len(entries) != len(eligible):
        raise ValueError('Run must contain exactly one response for every eligible test')
    responses = {}
    for row in entries:
        test = row['test_id']
        if test in responses or test not in eligible or row['history_id'] != tests[test]['history_id']:
            raise ValueError('Unknown, duplicate or mismatched response test')
        text = row.get('response')
        if not isinstance(text, str) or not text.strip() or hashlib.sha256(text.encode()).hexdigest() != row.get('response_sha256'):
            raise ValueError('Response content digest mismatch')
        responses[test] = row
    if set(responses) != eligible:
        raise ValueError('Incomplete run coverage')
    if blind_key.get('format') != 'ac3-heldout-blind-key-v1' or blind_key.get('frozen_sha256') != frozen_digest:
        raise ValueError('Blind identity key is not bound to the frozen study')
    mapping = blind_key.get('blind_to_test', {})
    if not isinstance(mapping, dict) or set(mapping.values()) != eligible or len(mapping) != len(eligible) or len(set(mapping.values())) != len(mapping):
        raise ValueError('Blind key must map each eligible test exactly once')
    names, decisions = [], []
    for slot, review in enumerate(reviews, 1):
        if review.get('format') != 'ac3-heldout-human-review-v1' or review.get('run_sha256') != blind_key.get('run_sha256'):
            raise ValueError('Reviewer document is not bound to this run')
        names.append(_declaration(review, slot))
        labels = review.get('decisions', [])
        if not isinstance(labels, list) or len(labels) != len(mapping):
            raise ValueError('Each review must include every blind response')
        by_test = {}
        for label in labels:
            blind = label['blind_id']
            if blind not in mapping or mapping[blind] in by_test:
                raise ValueError('Unknown or duplicate blind answer')
            test = mapping[blind]
            if label.get('response_sha256') != responses[test]['response_sha256']:
                raise ValueError('Review refers to a different answer')
            if not isinstance(label.get('rationale'), str) or not label['rationale'].strip():
                raise ValueError('Each human verdict needs a rationale')
            by_test[test] = {'verdict': label['verdict'], 'failure_dimension': label['failure_dimension']}
        decisions.append(by_test)
    if names[0] == names[1]:
        raise ValueError('Distinct reviewer labels are required')
    rows = [{'test_id': test, 'history_id': tests[test]['history_id'], 'grounding': 'valid',
             'human_1': decisions[0][test], 'human_2': decisions[1][test],
             'automatic': responses[test]['automatic']} for test in sorted(eligible)]
    result = calculate(rows)
    result['history_bootstrap'] = history_bootstrap(rows)
    # Grounding rate also includes excluded candidate questions from the frozen suite.
    result['grounding'] = {'valid': len(eligible), 'invalid': len(tests) - len(eligible), 'uncertain': 0,
                           'validity_conservative': {'numerator': len(eligible), 'denominator': len(tests), 'value': len(eligible) / len(tests)}}
    result['cases'] = len(tests)
    result['source_histories_with_valid_tests'] = len({tests[k]['history_id'] for k in eligible})
    result['thresholds_from_frozen_protocol'] = config['thresholds']
    # Match the documented pilot definitions; the additional conservative
    # measures and coverage remain visible rather than changing that protocol.
    definitions = {
        'failure_detection_recall_min': (result['metrics']['failure_recall_conservative'], 'min'),
        'failure_classification_accuracy_min': (result['metrics']['classification_accuracy_conservative'], 'min'),
        'test_validity_min': (result['grounding']['validity_conservative'], 'min'),
        'false_positive_rate_max': (result['metrics']['false_positive_rate_decided'], 'max'),
    }
    comparisons = {}
    for name, (metric, direction) in definitions.items():
        threshold, value = config['thresholds'].get(name), metric['value']
        comparisons[name] = {'metric': metric, 'threshold': threshold, 'direction': direction,
                             'met_descriptively': None if value is None or threshold is None else (value >= threshold if direction == 'min' else value <= threshold)}
    result['threshold_comparison_descriptive'] = comparisons
    requirements = {
        'decided_coverage': (result['metrics']['decided_coverage']['value'], config.get('minimum_decided_coverage')),
        'human_passes': (result['human_reference']['pass'], config.get('minimum_human_pass_count')),
        'human_failures': (result['human_reference']['fail'], config.get('minimum_human_failure_count')),
        # Historical field name means distinct observed IDs, not statistically independent draws.
        'history_coverage': (result['source_histories_with_agreed_reference'], config.get('minimum_independent_histories')),
    }
    checks = {name: {'observed': observed, 'minimum': minimum,
                     'met': None if observed is None or not isinstance(minimum, (int, float)) or isinstance(minimum, bool)
                     else observed >= minimum} for name, (observed, minimum) in requirements.items()}
    values = [check['met'] for check in checks.values()]
    result['evidence_sufficiency'] = {
        'checks': checks,
        'status': 'insufficient' if False in values else ('unassessed' if None in values else 'minimums_met_descriptively'),
        'notice': 'History count refers to distinct synthetic history IDs, not independent random samples. Meeting minimum counts does not establish population validity.',
    }
    result['protocol_clock_order_self_reported'] = True
    result['reviewer_identity_and_independence_authenticated'] = False
    result['acceptance'] = 'not_assessed_until_provenance_and_independence_are_verified'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('frozen', 'run', 'blind-key', 'review-1', 'review-2'):
        p.add_argument('--' + name, required=True, type=Path)
        p.add_argument('--' + name + '-sha256', required=True)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    paths = [args.frozen, args.run, args.blind_key, args.review_1, args.review_2]
    digests = [args.frozen_sha256, args.run_sha256, args.blind_key_sha256, args.review_1_sha256, args.review_2_sha256]
    frozen, run, key, first, second = [_read_bound(path, digest) for path, digest in zip(paths, digests)]
    if key.get('run_sha256') != args.run_sha256:
        raise ValueError('Blind key does not bind to the supplied run')
    if Path(run.get('frozen_path', '')).resolve() != args.frozen.resolve():
        raise ValueError('Run points to a different frozen source')
    result = analyze(frozen, args.frozen_sha256, run, key, [first, second])
    result['source_sha256'] = dict(zip(('frozen', 'run', 'blind_key', 'review_1', 'review_2'), digests))
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in zip(paths, digests)):
        raise ValueError('Evidence changed during analysis')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'acceptance': result['acceptance']}))


if __name__ == '__main__':
    main()
