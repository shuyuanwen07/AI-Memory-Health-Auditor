"""Describe frozen paired repair results without inflating repeated sample size."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


def mean_present(values):
    present = [value for value in values if value is not None]
    return statistics.mean(present) if present else None


def analyse(study, results):
    rows = []
    for item in results['runs']:
        if 'result' not in item:
            continue
        run = item['run']
        records = {r['memory_id']: r['canonical_value'] for r in item['trace']['records']}
        for evaluation in item['evaluations']:
            test, response = evaluation['test'], evaluation['response']
            metadata = response['execution_metadata']
            receipt = metadata.get('memory_input') or {}
            rows.append({
                'group': item['group'], 'run_id': run['run_id'], 'model': run['model'],
                'strategy': run['memory_strategy'], 'dimension': test['dimension'],
                'test_id': test['test_id'], 'question': test['prompt'],
                'expected': test['expected_behavior'], 'response': response['response_text'],
                'passed': evaluation['automated']['passed'],
                'reason': evaluation['automated']['reason'],
                'supplied_memory': [records[m] for m in receipt.get('sent_memory_ids', []) if m in records],
                'supplied_record_count': receipt.get('record_count'),
                'latency_ms': metadata.get('latency_ms'),
                'total_tokens': metadata.get('total_tokens'),
                'response_source': metadata.get('response_source'),
            })
    summaries = []
    for strategy in study['strategies']:
        all_selected = [r for r in rows if r['strategy'] == strategy]
        selected = [r for r in all_selected if r['passed'] is not None]
        dimensions = {}
        for dimension in ['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use']:
            values = [r for r in selected if r['dimension'] == dimension]
            dimensions[dimension] = {'passed': sum(r['passed'] for r in values), 'total': len(values),
                'percentage': 100 * sum(r['passed'] for r in values) / len(values) if values else None}
        run_scores = [item['result']['overall_score'] for item in results['runs']
                      if item['run']['memory_strategy'] == strategy and 'result' in item and item['result']['overall_score'] is not None]
        summaries.append({'strategy': strategy, 'passed': sum(r['passed'] for r in selected),
            'total': len(selected), 'uncertain': len(all_selected) - len(selected), 'percentage': 100 * sum(r['passed'] for r in selected) / len(selected) if selected else None,
            'dimensions': dimensions, 'mean_run_score': statistics.mean(run_scores) if run_scores else None,
            'run_score_sd': statistics.pstdev(run_scores) if run_scores else None,
            'mean_latency_ms': mean_present(r['latency_ms'] for r in all_selected),
            'total_tokens': sum(r['total_tokens'] or 0 for r in selected),
            'mean_supplied_records': mean_present(r['supplied_record_count'] for r in all_selected)})
    comparisons = []
    names = sorted({c.get('comparison_name', 'primary') for c in results['before_after_comparisons']})
    for name in names:
        pairs = [p for p in results['before_after_comparisons'] if p.get('comparison_name', 'primary') == name]
        by_source = defaultdict(list)
        counts = {k: 0 for k in ['fixed', 'regressed', 'still_failed', 'still_passed']}
        for p in pairs:
            before = next(r for r in results['runs'] if r['run']['run_id'] == p['before'])
            if p['paired_delta_percentage_points'] is not None:
                by_source[before['group']].append(p['paired_delta_percentage_points'])
            for key in counts:
                counts[key] += p['counts'][key]
        source_deltas = [statistics.mean(values) for values in by_source.values()]
        if source_deltas:
            rng = random.Random(42)
            draws = sorted(statistics.mean(rng.choices(source_deltas, k=len(source_deltas))) for _ in range(10000))
            interval = [draws[249], draws[9749]]
        else:
            interval = None
        comparisons.append({'name': name, 'paired_audits': len(pairs), 'source_histories': len(source_deltas),
            'outcomes_across_repetitions': counts, 'source_mean_deltas_pp': source_deltas,
            'mean_delta_pp': statistics.mean(source_deltas) if source_deltas else None,
            'descriptive_source_cluster_bootstrap_95_interval_pp': interval,
            'notice': 'Synthetic source histories; repeats are nested, not independent samples. Interval is descriptive pilot evidence, not a generalisation guarantee.'})
    unique = {}
    for row in rows:
        key = json.dumps([row['group'], row['strategy'], row['question'], row['expected'], row['response'], row['supplied_memory']], sort_keys=True)
        if key not in unique:
            unique[key] = {**row, 'instances': [], 'ai_semantic_review': 'pending', 'human_review': 'pending'}
        unique[key]['instances'].append({'run_id': row['run_id'], 'test_id': row['test_id']})
    return {'protocol_id': study['protocol_id'], 'source_histories': len(study['scenarios']),
        'unique_test_instances': sum(len(s['gold_tests']) for s in study['scenarios']),
        'completed_responses': len(rows), 'human_validation': 'pending',
        'condition_summary': summaries, 'comparisons': comparisons,
        'review_groups': list(unique.values()), 'notice': study['notice']}, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    study = json.loads(args.study.read_text())
    results = json.loads(args.results.read_text())
    if hashlib.sha256(args.study.read_bytes()).hexdigest() != results['dataset_fingerprint_sha256']:
        raise SystemExit('Dataset differs from the executed frozen suite.')
    if study.get('expected_implementation_fingerprint_sha256') != results['implementation_fingerprint_sha256']:
        raise SystemExit('Executed implementation differs from the declared freeze.')
    payload, rows = analyse(study, results)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'validation-analysis.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    with (args.output / 'response-results.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / 'paper-export.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['record_type', 'condition', 'dimension', 'metric', 'value'])
        writer.writeheader()
        for condition in payload['condition_summary']:
            writer.writerow({'record_type': 'condition', 'condition': condition['strategy'], 'metric': 'overall_mean', 'value': condition['percentage']})
            for dimension, score in condition['dimensions'].items():
                writer.writerow({'record_type': 'dimension', 'condition': condition['strategy'], 'dimension': dimension, 'metric': 'mean_percentage', 'value': score['percentage']})
    print(json.dumps({'responses': len(rows), 'review_groups': len(payload['review_groups']), 'conditions': payload['condition_summary'], 'comparisons': payload['comparisons']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
