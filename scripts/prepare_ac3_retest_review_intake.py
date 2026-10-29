"""Check two source-bound AC3 retest reviews; never freeze or run the study.

The result preserves disagreements and uncertainty. Fully valid returns can be
projected to the existing fact-plan validator, but this is not a formal-run
adapter: the current prospective freezer hard-codes earlier review protocols.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ac3_reviewed_fact_map import validate_fact_plan

PACKET = ROOT / 'output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj):
    return sha(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def inspect(source_raw, plan_raw, review_raws):
    """Reject changed evidence; preserve original human labels without adjudication."""
    if len(review_raws) != 2:
        raise ValueError('Exactly two source-bound review files are required.')
    suite, plan = json.loads(source_raw), json.loads(plan_raw)
    cases = suite.get('cases')
    if not isinstance(cases, list) or len(cases) != 30:
        raise ValueError('Expected exactly 30 candidate histories.')
    histories = [c['history_id'] for c in cases]
    if len(set(histories)) != 30 or set(histories) != set(plan['histories']):
        raise ValueError('Source and plan history IDs must match uniquely.')
    if sum(len(c['tests']) for c in cases) != 120:
        raise ValueError('Expected exactly 120 questions.')
    source_hash, plan_hash = sha(source_raw), sha(plan_raw)
    if source_hash != '3960b87c5375615c4cfed4f7dff53de2a1099cfc64ea77322ef52da448c29c78' or plan_hash != '836f707194222aaae33adc0fa676ae1ce12eed7cce13ac9a61f2292429fec03d':
        raise ValueError('Candidate source or plan differs from the prepared v6 packet.')
    results, declarations = [], []
    names = set()
    for slot, data in enumerate(review_raws, 1):
        review = json.loads(data)
        if (review.get('format') != 'ac3-retest-candidate-review-v6' or review.get('reviewer_slot') != slot or
                review.get('source_sha256') != source_hash or review.get('plan_sha256') != plan_hash):
            raise ValueError('Review slot, version, or evidence digest does not match the candidate.')
        dec = review.get('reviewer_declaration', {})
        label = dec.get('reviewer_label')
        norm = unicodedata.normalize('NFKC', label).strip().casefold() if isinstance(label, str) else ''
        if (not norm or dec.get('completed_by_human') is not True or dec.get('completed_independently') is not True
                or type(dec.get('used_ai_assistance')) is not bool):
            raise ValueError('Human completion, independence, reviewer label, and AI-assistance declarations are required.')
        if norm in names:
            raise ValueError('The two reviewer labels must differ.')
        names.add(norm)
        reviewed = review.get('cases')
        if not isinstance(reviewed, list) or len(reviewed) != len(cases):
            raise ValueError('Review cases are missing or duplicated.')
        decisions = {}
        for original, case in zip(cases, reviewed):
            h = original['history_id']
            if (case.get('history_id') != h or case.get('scenario_title') != original['scenario_title'] or
                    case.get('design_family') != original['design_family'] or case.get('source_messages') != original['source_messages']):
                raise ValueError('History identity, source, design, or order differs from candidate.')
            for kind, ref_items, items, payload_key, decision_key in (
                ('question', original['tests'], case.get('questions'), 'test', 'validity'),
                ('fact', plan['histories'][h]['facts'], case.get('facts'), 'fact', 'support'),
                ('relationship', plan['histories'][h]['relationships'], case.get('relationships'), 'relationship', 'validity')):
                if not isinstance(items, list) or len(items) != len(ref_items):
                    raise ValueError('An item is missing or duplicated.')
                for i, (reference, item) in enumerate(zip(ref_items, items), 1):
                    if item.get(payload_key) != reference:
                        raise ValueError('Reviewed item changed, was reordered, or does not match the original.')
                    assessment = item.get('review')
                    if not isinstance(assessment, dict) or set(assessment) != {decision_key, 'note'}:
                        raise ValueError('Review decision shape changed.')
                    verdict, note = assessment[decision_key], assessment['note']
                    if verdict not in ('valid', 'invalid', 'uncertain', None) or not isinstance(note, str):
                        raise ValueError('Decision must be valid, invalid, uncertain, or null with a text note.')
                    if verdict in ('invalid', 'uncertain') and not note.strip():
                        raise ValueError('Invalid or uncertain decisions require an explanation.')
                    key = reference.get('test_id') or reference.get('memory_id') if kind != 'relationship' else f'{h}-REL-{i}'
                    if key in decisions:
                        raise ValueError('Item IDs are duplicated.')
                    decisions[key] = {'history_id': h, 'kind': kind, 'verdict': verdict, 'note': note}
            extra = case.get('additional_source_facts_missing')
            if not isinstance(extra, list):
                raise ValueError('Missing-fact suggestions must be an array.')
            for i, value in enumerate(extra, 1):
                if not isinstance(value, (str, dict)) or not value:
                    raise ValueError('Missing-fact suggestions must be meaningful text or an object.')
                decisions[f'{h}-MISSING-{i}'] = {'history_id': h, 'kind': 'missing_fact', 'verdict': 'uncertain', 'note': value}
        declarations.append(dec)
        results.append(decisions)
    ids = set(results[0]) | set(results[1]); summary = []; all_valid = True
    for key in sorted(ids):
        a, b = results[0].get(key), results[1].get(key)
        va, vb = a['verdict'] if a else None, b['verdict'] if b else None
        state = 'both_valid' if va == vb == 'valid' else ('disagreement' if va != vb and va is not None and vb is not None else 'unresolved')
        if state != 'both_valid':
            all_valid = False
            summary.append({'item_id': key, 'history_id': (a or b)['history_id'], 'kind': (a or b)['kind'],
                            'reviewer_1': a, 'reviewer_2': b, 'status': state})
    projection = None
    if all_valid:
        canonical = canonical_sha(plan)
        fact_reviews = [{'reviewer_label': d['reviewer_label'], 'completed_by_human': True,
                         'completed_independently': True, 'reviewed_fact_and_relation_semantics': True,
                         'fact_plan_sha256': canonical, 'used_ai_assistance': d['used_ai_assistance']}
                        for d in declarations]
        verification = validate_fact_plan(suite, plan, fact_reviews)
        projection = {'fact_plan_sha256_canonical': canonical, 'fact_reviews': fact_reviews,
                      'fact_plan_validation': verification}
    return {'format': 'ac3-retest-review-intake-v1', 'source_sha256': source_hash, 'plan_sha256': plan_hash,
            'review_sha256': [sha(raw) for raw in review_raws], 'histories': 30, 'questions': 120,
            'reviewed_items_per_reviewer': [len(x) for x in results], 'declared_reviewers': declarations,
            'identity_independently_authenticated': False, 'unresolved': summary,
            'all_items_valid_in_both_reviews': all_valid, 'existing_fact_validator_projection': projection,
            'protocol_frozen': False, 'model_called': False, 'database_written': False,
            'run_authorized': False,
            'limitations': ['Reviewer declarations and identities are not independently authenticated.',
                            'This is an intake projection only; the existing frozen-study gate does not accept this new candidate without additional integration and protocol checks.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=PACKET / 'candidate-inputs.json')
    parser.add_argument('--plan', type=Path, default=PACKET / 'proposed-fact-plan.json')
    parser.add_argument('--review-1', type=Path, required=True)
    parser.add_argument('--review-2', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.source, args.plan, args.review_1, args.review_2]
    if any(path.is_symlink() or not path.is_file() for path in inputs):
        raise ValueError('All inputs must be existing regular, non-symlink files.')
    result = inspect(args.source.read_bytes(), args.plan.read_bytes(), [args.review_1.read_bytes(), args.review_2.read_bytes()])
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(json.dumps({'output': str(args.output), 'all_items_valid_in_both_reviews': result['all_items_valid_in_both_reviews'],
                      'unresolved': len(result['unresolved']), 'run_authorized': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
