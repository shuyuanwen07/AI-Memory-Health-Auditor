"""Replay an experimental scope check on existing labelled development data.

This never writes product data, never invokes a model and must not be treated as
an independent estimate: the candidate was developed using these same labels.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

from scripts import replay_ac2_product_scope_gate as saved_replay

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'output/proposal-delivery/ac2-product-scope-v3-development-20261029/scope_candidate.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    values = {name: json.loads((ROOT / path).read_bytes()) for name, path in saved_replay.FILES.items()}
    confirmed = values['adjudication_summary']['source_sha256']
    for name, key in (('adjudication', 'adjudication'), ('confirmation', 'confirmation'),
                      ('packet', 'packet'), ('allocation', 'allocation_key')):
        if sha(ROOT / saved_replay.FILES[name]) != confirmed[key]:
            raise ValueError(f'Frozen {name} differs from confirmed adjudication')
    spec = importlib.util.spec_from_file_location('scope_v3_development', CANDIDATE)
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    saved_warning, saved_version = saved_replay.scope_warning, saved_replay.VERSION
    try:
        saved_replay.scope_warning, saved_replay.VERSION = candidate.scope_warning, candidate.VERSION
        result = saved_replay.replay(values)
    finally:
        saved_replay.scope_warning, saved_replay.VERSION = saved_warning, saved_version
    result['candidate_sha256'] = sha(CANDIDATE)
    result['base_scope_sha256'] = sha(ROOT / 'backend/app/test_generator/scope_review.py')
    result['input_sha256'] = {name: sha(ROOT / path) for name, path in saved_replay.FILES.items()}
    result['limitations'].insert(0, 'Experimental candidate developed after reviewing this same dataset: not independent validation, not installed in the product.')
    out = CANDIDATE.parent / 'development-replay.json'
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'output': str(out), 'matched': result['matched'], 'unmatched': len(result['unmatched']),
                      'arms': result['arms']}))


if __name__ == '__main__':
    main()
