"""Re-score preserved model answers separately; never replace recorded verdicts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Memory, TargetResponse, TestCase
from run_repair_study import ident


def rescore(study, results):
    output = []
    judge = RuleBasedBehaviourEvaluator()
    scenarios = {ident('CS', results['dataset_fingerprint_sha256'], s['conversation_id'], False): s for s in study['scenarios']}
    for item in results['runs']:
        run = item['run']
        if 'evaluations' not in item:
            continue
        source = scenarios[run['conversation_id']]
        memories = [Memory(**{**m, 'memory_id': ident('M', run['conversation_id'], m['memory_id']),
            'conversation_id': run['conversation_id'], 'status': 'confirmed'}) for m in source['gold_memories']]
        records = {r['memory_id']: r['canonical_value'] for r in item['trace']['records']}
        for row in item['evaluations']:
            case = TestCase(**row['test'])
            response = TargetResponse(**row['response'])
            evaluation = judge.evaluate(case, response, memories)
            receipt = row['response']['execution_metadata']['memory_input']
            output.append({'run_id': run['run_id'], 'test_id': case.test_id, 'strategy': run['memory_strategy'],
                'dimension': case.dimension.value, 'prompt': case.prompt, 'expected': case.expected_behavior,
                'response': response.response_text, 'actual_supplied_memory': [records[m] for m in receipt['sent_memory_ids']],
                'original_evaluator': row['automated']['evaluator'], 'original_passed': row['automated']['passed'],
                'common_evaluator': judge.VERSION, 'common_passed': evaluation.passed, 'common_reason': evaluation.reason})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--reference-review', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = rescore(json.loads(args.study.read_text()), json.loads(args.results.read_text()))
    payload = {'evaluator': RuleBasedBehaviourEvaluator.VERSION, 'new_model_calls': 0,
               'human_validation': 'pending', 'rows': rows,
               'notice': 'Separate re-scoring of saved responses; original results unchanged.'}
    if args.reference_review:
        review = json.loads(args.reference_review.read_text())
        labels = {(i['run_id'], i['test_id']): g['ai_semantic_passed'] for g in review['groups'] for i in g['instances']}
        counts = {key: 0 for key in ['tp', 'tn', 'fp', 'fn', 'ambiguous']}
        original_errors = 0
        for row in rows:
            label = labels[(row['run_id'], row['test_id'])]
            if label is None:
                counts['ambiguous'] += 1
                continue
            counts['tp' if label and row['common_passed'] else 'fn' if label else 'fp' if row['common_passed'] else 'tn'] += 1
            original_errors += row['original_passed'] != label
        payload['AI_reference_calibration'] = {**counts, 'original_disagreements': original_errors,
            'current_disagreements': counts['fp'] + counts['fn'],
            'notice': 'Development examples previously inspected; AI reference, not blind human evaluator validity.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in payload.items() if key != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
