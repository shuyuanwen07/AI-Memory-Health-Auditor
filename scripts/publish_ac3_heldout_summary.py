"""Publish aggregate held-out AC3 results only after rechecking all evidence.

This does not collect answers or review them. No source text, answers, labels,
reviewer identity, or blind mapping is copied into the public dashboard file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_ac3_heldout import _read_bound, analyze


def build_summary(paths, digests):
    names = ('frozen', 'run', 'blind_key', 'review_1', 'review_2')
    if set(paths) != set(names) or set(digests) != set(names):
        raise ValueError('Exactly five bound evidence files are required')
    docs = {name: _read_bound(paths[name], digests[name]) for name in names}
    if docs['blind_key'].get('run_sha256') != digests['run']:
        raise ValueError('Blind key is not bound to this run')
    if Path(docs['run'].get('frozen_path', '')).resolve() != Path(paths['frozen']).resolve():
        raise ValueError('Run points to a different frozen suite')
    result = analyze(docs['frozen'], digests['frozen'], docs['run'], docs['blind_key'],
                     [docs['review_1'], docs['review_2']])
    if any(hashlib.sha256(Path(paths[name]).read_bytes()).hexdigest() != digests[name] for name in names):
        raise ValueError('Evidence changed during analysis')
    return {
        'format': 'ac3-heldout-public-summary-v1',
        'cases': result['cases'],
        'histories': result['source_histories_with_valid_tests'],
        'grounding': result['grounding'],
        'human_reference': result['human_reference'],
        'automatic': result['automatic'],
        'metrics': result['metrics'],
        'history_bootstrap': result['history_bootstrap'],
        'evidence_sufficiency': result['evidence_sufficiency'],
        'threshold_comparison_descriptive': result['threshold_comparison_descriptive'],
        'acceptance': result['acceptance'],
        'limitations': 'Descriptive held-out comparison on synthetic histories; identity, independence and clock are user-reported or unverified. Abstentions and human disagreements remain visible.',
        'source_sha256': {name: digests[name] for name in names},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    names = ('frozen', 'run', 'blind-key', 'review-1', 'review-2')
    for name in names:
        parser.add_argument('--' + name, required=True, type=Path)
        parser.add_argument('--' + name + '-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    keys = [name.replace('-', '_') for name in names]
    paths = {key: getattr(args, key) for key in keys}
    digests = {key: getattr(args, key + '_sha256') for key in keys}
    result = build_summary(paths, digests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'cases': result['cases'], 'acceptance': result['acceptance']}))


if __name__ == '__main__':
    main()
