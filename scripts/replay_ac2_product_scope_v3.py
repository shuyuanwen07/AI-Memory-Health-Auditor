"""Replay product v3 on the previously reviewed AC2 development sample.

Do not treat this same-sample comparison as independent validation.  Inputs,
version and the original v2 source are pinned; previous results are preserved.
"""
import hashlib
import json
from pathlib import Path

from scripts import replay_ac2_product_scope_gate as original

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'output/proposal-delivery/ac1-ac2-b-return-20261029-v1'
FROZEN_V2 = ROOT / 'output/proposal-delivery/ac2-product-scope-v3-development-20261029/scope_review_v2_frozen.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if original.VERSION != 'source-scope-review-v3':
        raise ValueError('Product implementation is not v3')
    old = json.loads((DIR / 'product-scope-retrospective-replay-v2.json').read_bytes())
    if digest(FROZEN_V2) != old['scope_implementation_sha256']:
        raise ValueError('Original v2 scope source does not match prior evidence')
    values = {key: json.loads((ROOT / path).read_bytes()) for key, path in original.FILES.items()}
    old_sources = values['adjudication_summary']['source_sha256']
    for name, key in (('adjudication', 'adjudication'), ('confirmation', 'confirmation'),
                      ('packet', 'packet'), ('allocation', 'allocation_key')):
        if digest(ROOT / original.FILES[name]) != old_sources[key]:
            raise ValueError(f'{name} differs from user-confirmed evidence')
    if digest(ROOT / original.FILES['raw_output']) != values['allocation']['raw_output_sha256']:
        raise ValueError('Raw generation differs from the frozen allocation')
    result = original.replay(values)
    if result['unmatched'] or result['matched'] != 228:
        raise ValueError('Not every frozen question could be verified')
    result['source_sha256'] = {key: digest(ROOT / path) for key, path in original.FILES.items()}
    result['scope_implementation_sha256'] = digest(ROOT / 'backend/app/test_generator/scope_review.py')
    result['previous_scope_implementation_sha256'] = digest(FROZEN_V2)
    result['replay_implementation_sha256'] = digest(Path(__file__).resolve())
    result['limitations'].insert(0, 'Product v3 was designed with these adjudicated labels available; this replay is development evidence, not an independent test.')
    out = DIR / 'product-scope-retrospective-replay-v3.json'
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'output': str(out), 'matched': result['matched'], 'arms': result['arms']}))


if __name__ == '__main__':
    main()
