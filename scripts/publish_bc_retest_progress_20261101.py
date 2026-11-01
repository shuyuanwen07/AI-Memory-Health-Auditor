"""Publish counts from the frozen B/C journals; never dispatch or score an answer."""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'output/proposal-delivery/bc-reader-retest-20261101-v2'
STRATEGIES = ['weak_first_hit', 'strong_rule_based', 'scope_aware', 'temporal_importance']


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def main():
    # Response identities are deduplicated across durable recovery snapshots.
    b_runs = {}
    for path in (STUDY / 'B').rglob('*.json'):
        if 'blind-review' in path.parts or 'raw' in path.parts:
            continue
        obj = read(path)
        if not isinstance(obj, dict) or obj.get('strategy') not in STRATEGIES or not obj.get('run_id'):
            continue
        answers = {}
        attempted_error = False
        for op in obj.get('operations', []):
            if op.get('path', '').endswith(('/execute', '/responses')) and isinstance(op.get('response'), list):
                answers.update({a['response_id']: a for a in op['response'] if isinstance(a, dict) and a.get('response_id')})
            if op.get('path', '').endswith('/execute') and op.get('state') == 'failed_without_retry' and op.get('status') != 409:
                attempted_error = True
        key = obj['run_id']
        prior = b_runs.setdefault(key, {'strategy': obj['strategy'], 'repeat': obj.get('repetition'), 'answers': {}, 'error': False})
        prior['answers'].update(answers)
        prior['error'] |= attempted_error
    observations = {'B': defaultdict(lambda: {'saved': 0, 'errors': 0}), 'C': defaultdict(lambda: {'saved': 0, 'errors': 0})}
    for run in b_runs.values():
        if run['repeat'] not in (1, 2, 3):
            continue
        bucket = observations['B'][(run['strategy'], run['repeat'])]
        bucket['saved'] += len(run['answers'])
        if run['error'] and len(run['answers']) < 4:
            bucket['errors'] += 4 - len(run['answers'])
    for path in (STUDY / 'C/responses').glob('*.json'):
        obj = read(path)
        if not isinstance(obj, dict):
            continue
        job = obj.get('job', {})
        if job.get('strategy') not in STRATEGIES or job.get('repeat') not in (1, 2, 3):
            continue
        bucket = observations['C'][(job['strategy'], job['repeat'])]
        if obj.get('status') == 'completed':
            bucket['saved'] += 1
        elif obj.get('status') in ('failed', 'ambiguous', 'worker_failed', 'failed_without_retry'):
            bucket['errors'] += 1
    consensus = read(STUDY / 'review/consensus.json')
    labels = defaultdict(list)
    safe_counts = Counter()
    if isinstance(consensus, dict):
        for item in consensus.get('items', []):
            if item.get('verdict') in ('pass', 'fail', 'uncertain'):
                labels[(item['study'], item['strategy'], item['repeat'])].append(item['verdict'])
                if item.get('safe_but_incomplete') == [True, True] or item.get('behavior_quality') == ['safe_but_incomplete', 'safe_but_incomplete']:
                    safe_counts[(item['study'], item['strategy'])] += 1
    studies = []
    for sid, name, units in [('B', 'Synthetic histories · shared-reader repair', 4), ('C', 'LongMemEval Oracle · stratified subset', 16)]:
        conditions = []
        for strategy in STRATEGIES:
            repeat_rows = []
            saved = errors = 0
            verdicts = []
            for repetition in (1, 2, 3):
                bucket = observations[sid][(strategy, repetition)]
                saved += bucket['saved']; errors += bucket['errors']
                judged = labels[(sid, strategy, repetition)]
                verdicts.extend(judged)
                repeat_rows.append({'repeat': repetition, 'saved': bucket['saved'], 'pass': judged.count('pass') if judged else None})
            if saved + errors > 48:
                raise ValueError(f'Duplicate or impossible ledger counts for {sid}/{strategy}')
            if len(verdicts) > saved:
                raise ValueError('Review count exceeds returned answers')
            conditions.append({'strategy': strategy, 'planned': 48, 'saved': saved, 'errors': errors,
                'remaining': 48-saved-errors, 'reviewed': len(verdicts),
                'pass': verdicts.count('pass') if verdicts else None,
                'fail': verdicts.count('fail') if verdicts else None,
                'unresolved': verdicts.count('uncertain') if verdicts else None, 'repeats': repeat_rows})
            conditions[-1]['safe_incomplete'] = safe_counts[(sid, strategy)] if verdicts else None
        studies.append({'id': sid, 'label': name, 'source_units': units, 'conditions': conditions})
    report = {'format': 'bc-astra-repeat-retest-v2', 'updated_at': datetime.now(timezone.utc).isoformat(),
        'provider': 'openai', 'model': 'gpt-6-astra', 'reasoning_effort': 'max',
        'questions_per_strategy': 16, 'repetitions': 3, 'planned_per_strategy': 48,
        'review_status': 'human_confirmed' if (consensus or {}).get('human_confirmed') else 'ai_reviewed' if labels else 'pending', 'studies': studies,
        'human_confirmation': (consensus or {}).get('human_confirmation'),
        'review_reasoning_effort': (consensus or {}).get('review_reasoning_effort', 'high'),
        'source_flags': {s: sum(x.get('study') == s and not x.get('accepted_by_both_ai') for x in (consensus or {}).get('sources', [])) for s in ('B', 'C')},
        'protocol_sha256': {s: hashlib.sha256((STUDY/s/'protocol.json').read_bytes()).hexdigest() for s in ('B', 'C')},
        'limitations': ['Different datasets; equal denominators do not equalize difficulty.',
            'Repeated answers share questions and source histories.', 'B is a reader-configuration development repair with the original rule writer.',
            'No automatic lexical score is treated as a source-aware review judgment.']}
    dest = ROOT / 'frontend/public/reports/bc-astra-repeat-retest-v2.json'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=dest.parent, prefix=dest.name+'-', suffix='.tmp', delete=False) as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n'); temp = f.name
    os.replace(temp, dest)
    print(json.dumps({s['id']: {'saved': sum(c['saved'] for c in s['conditions']), 'errors': sum(c['errors'] for c in s['conditions'])} for s in studies}))
    return sum(c['remaining'] for s in studies for c in s['conditions'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        remaining = main()
        if not args.watch or remaining == 0:
            break
        time.sleep(15)
