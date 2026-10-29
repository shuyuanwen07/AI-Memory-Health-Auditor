"""Retrospective, aggregate-only diagnosis; never calls a model or changes evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def analyze(source, development):
    run, run_sha = read(source / 'heldout-run.json')
    key, key_sha = read(source / 'blind-review/private-key.json')
    marker, _ = read(source / 'latest-review.json')
    root = source / marker['review_directory']
    reviews = [read(root / f'reviewer-{i}.json') for i in (1, 2)]
    plan, plan_sha = read(development / 'plan.json')
    if key['run_sha256'] != run_sha or plan['source_run_sha256'] != run_sha:
        raise ValueError('Run fingerprint mismatch')
    responses = run['responses']
    if len(responses) != 120 or len({r['test_id'] for r in responses}) != 120:
        raise ValueError('Unexpected response set')
    labels = []
    for index, (review, _) in enumerate(reviews, 1):
        if review['run_sha256'] != run_sha or review['reviewer_slot'] != index:
            raise ValueError('Review does not match the saved run')
        mapped = {key['blind_to_test'][r['blind_id']]: r for r in review['decisions']}
        if len(review['decisions']) != 120 or len(mapped) != 120 or set(mapped) != {r['test_id'] for r in responses}:
            raise ValueError('Incomplete or duplicate review')
        labels.append(mapped)
    matrices = {'hybrid': Counter(), 'provider_only': Counter()}
    verdicts = {'hybrid': Counter(), 'provider_only': Counter()}
    transitions = {'hybrid': Counter(), 'provider_only': Counter()}
    skipped = Counter()
    evidence = hashlib.sha256()
    for response in responses:
        ident = response['test_id']
        human = [review[ident] for review in labels]
        if any(h['response_sha256'] != response['response_sha256'] for h in human):
            raise ValueError('Review points to a different response')
        result, result_sha = read(development / f'{ident}.result.json')
        started, _ = read(development / f'{ident}.started.json')
        if (result['status'] != 'completed' or result['test_id'] != ident or result['prompt_sha256'] != started['prompt_sha256']
                or started['source_frozen_sha256'] != plan['source_frozen_sha256']):
            raise ValueError('Development result does not match its start record')
        evidence.update(bytes.fromhex(result_sha))
        if human[0]['verdict'] != human[1]['verdict']:
            skipped['verdict_disagreement'] += 1
            continue
        verdict = human[0]['verdict']
        if verdict not in ('pass', 'fail'):
            skipped['human_uncertain'] += 1
            continue
        judgments = {'hybrid': result['judgment'], 'provider_only': result['validated_provider_judgment']}
        original = response['automatic']['verdict']
        if original not in ('pass', 'fail', 'uncertain'):
            raise ValueError('Invalid saved original verdict')
        for name, judgment in judgments.items():
            passed = judgment['passed']
            if passed is not None and type(passed) is not bool:
                raise ValueError('Invalid automatic verdict')
            automatic = 'uncertain' if passed is None else 'pass' if passed else 'fail'
            verdicts[name][(verdict, automatic)] += 1
            transitions[name][(verdict, original, automatic)] += 1
            if verdict == 'fail' and automatic == 'fail':
                if human[0]['failure_dimension'] != human[1]['failure_dimension'] or not human[0]['failure_dimension']:
                    skipped[name + '_category_unresolved'] += 1
                    continue
                matrices[name][(human[0]['failure_dimension'], judgment.get('failure_type') or 'unclassified')] += 1
    def flatten(counter):
        return [{'reference': a, 'automatic': b, 'count': n} for (a,b), n in sorted(counter.items())]
    def flatten_transitions(counter):
        return [{'reference': a, 'original': b, 'candidate': c, 'count': n} for (a,b,c), n in sorted(counter.items())]
    return {'format':'ac3-category-error-diagnosis-v1', 'status':'retrospective development analysis only',
            'run_sha256':run_sha, 'review_sha256':[x[1] for x in reviews], 'private_key_sha256':key_sha,
            'plan_sha256':plan_sha, 'ordered_result_hashes_sha256':evidence.hexdigest(),
            'cases':len(responses), 'verdicts':{k:flatten(v) for k,v in verdicts.items()},
            'paired_verdict_transitions':{k:flatten_transitions(v) for k,v in transitions.items()},
            'category_matrices':{k:flatten(v) for k,v in matrices.items()}, 'excluded':dict(skipped),
            'limitations':['Same previously observed answers used to develop candidates; no independent validation.',
                'Category matrices contain human-agreed failed answers that the candidate detected; denominators differ.',
                'Human-review independence is user-reported; AI assistance was used.',
                'Counts alone do not identify causes or establish real-world performance.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('development', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = analyze(args.source, args.development)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
