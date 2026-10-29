"""Compare two human reviews against preserved AC2 revised-question templates."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

FIELDS = ('question_validity', 'expected_behavior_supported', 'source_ids_sufficient')
VALUES = {'valid', 'invalid', 'uncertain'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(template, returned, slot):
    if template.get('format') != 'ac2-revised-question-human-review-v1' or template.get('reviewer_slot') != slot:
        raise ValueError('Unexpected template format or reviewer slot')
    if len(template.get('items', [])) != 13 or len(returned.get('items', [])) != 13:
        raise ValueError('Expected 13 items')
    base = copy.deepcopy(returned)
    base['reviewer_declaration'] = template['reviewer_declaration']
    for original, current in zip(template['items'], base['items']):
        current['review'] = original['review']
    if base != template:
        raise ValueError('Source, question, order, or non-review fields changed')
    declarations = returned['reviewer_declaration']
    for key in ('completed_by_human', 'completed_independently', 'has_seen_other_review', 'used_ai_assistance'):
        if declarations.get(key) not in (True, False, None):
            raise ValueError('Invalid reviewer declaration')
    for item in returned['items']:
        review = item['review']
        if set(review) != set(FIELDS) | {'rationale'} or not isinstance(review['rationale'], str):
            raise ValueError('Invalid review fields')
        if any(review[field] not in VALUES | {None} for field in FIELDS):
            raise ValueError('Invalid review judgment')


def reconcile(template_paths, return_paths, output, manifest_path=None):
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite output')
    manifest_path = manifest_path or template_paths[0].parent.parent / 'template-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('format') != 'ac2-revised-review-template-manifest-v1':
        raise ValueError('Invalid template manifest')
    for path in template_paths:
        if manifest.get('template_sha256', {}).get(path.name) != digest(path):
            raise ValueError('Template does not match its preserved manifest')
    templates = [json.loads(p.read_text()) for p in template_paths]
    returns = [json.loads(p.read_text()) for p in return_paths]
    for index in range(2):
        validate(templates[index], returns[index], index + 1)
    if [x['revised_item_id'] for x in templates[0]['items']] != [x['revised_item_id'] for x in templates[1]['items']]:
        raise ValueError('Reviewer templates do not have the same item IDs')
    items = []
    for a, b in zip(returns[0]['items'], returns[1]['items']):
        comparisons = {}
        for field in FIELDS:
            x, y = a['review'][field], b['review'][field]
            comparisons[field] = {'reviewer_1': x, 'reviewer_2': y,
                                  'status': 'unresolved' if x in (None, 'uncertain') or y in (None, 'uncertain') else 'agree' if x == y else 'disagree'}
        items.append({'revised_item_id': a['revised_item_id'], 'fields': comparisons,
                      'rationales': [a['review']['rationale'], b['review']['rationale']],
                      'adjudicated_decision': None})
    summary = {'format': 'ac2-revised-question-reconciliation-v1', 'source_sha256': [digest(p) for p in template_paths + return_paths], 'manifest_sha256': digest(manifest_path),
               'declarations': [x['reviewer_declaration'] for x in returns], 'items': items,
               'notice': 'Agreement is not adjudication. Reviewer identity and independence are self-declared; uncertain is not a pass.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('template-1', 'template-2', 'return-1', 'return-2', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    result = reconcile([args.template_1, args.template_2], [args.return_1, args.return_2], args.output, args.manifest)
    print(json.dumps({'items': len(result['items']), 'output': str(args.output)}))
