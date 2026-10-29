"""Analyze a frozen, user-confirmed independent blind review of scope guard v2."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT/'output/proposal-delivery/ac2-scope-v2-independent-review-20261029-v1'


def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def analyze(material, key, protocol, reviews, confirmation):
    material_hash = sha(canonical(material))
    if (key.get('material_sha256') != material_hash or len(reviews) != 2
            or confirmation.get('format') != 'ac2-scope-v2-human-confirmation-v1'
            or confirmation.get('confirmed_by') != 'user' or confirmation.get('completed_by_humans') is not True):
        raise ValueError('Missing source binding or user-confirmed human reviews')
    questions = {q['blind_id']: q for q in material['questions']}
    if len(questions) != len(material['questions']) or set(questions) != set(key['identity']):
        raise ValueError('Question IDs do not match private identity key')
    labels, tables, declarations = set(), [], []
    for slot, review in enumerate(reviews, 1):
        declaration = review.get('reviewer_declaration', {})
        label = declaration.get('reviewer_label')
        if (review.get('format') != 'ac2-scope-v2-human-review-v1'
                or review.get('reviewer_slot') != slot or review.get('material_sha256') != material_hash
                or any(review.get(k) != material[k] for k in ('histories', 'questions'))):
            raise ValueError('Reviewer modified source material')
        if (not isinstance(label, str) or not label.strip() or label.casefold().strip() in labels
                or declaration.get('completed_by_human') is not True
                or declaration.get('completed_independently') is not True
                or declaration.get('seen_other_review') is not False
                or declaration.get('seen_guard_flags') is not False
                or type(declaration.get('used_ai_assistance')) is not bool
                or (declaration.get('prior_exposure_to_sources') is not None
                    and type(declaration.get('prior_exposure_to_sources')) is not bool)):
            raise ValueError('Reviewer independence and blindness need explicit declarations')
        labels.add(label.casefold().strip())
        declarations.append(declaration)
        decisions = review.get('decisions', [])
        table = {d.get('blind_id'): d for d in decisions}
        if len(table) != len(decisions) or set(table) != set(questions):
            raise ValueError('Missing, duplicate, or unexpected question decisions')
        for item in decisions:
            if (set(item) != {'blind_id','grounded','structurally_executable','reason'}
                    or item['grounded'] not in ('valid','invalid','uncertain')
                    or item['structurally_executable'] not in ('valid','invalid','uncertain')
                    or not isinstance(item['reason'], str)
                    or ((item['grounded'] != 'valid' or item['structurally_executable'] != 'valid')
                        and not item['reason'].strip())):
                raise ValueError('Invalid judgment or missing explanation')
        tables.append(table)
    counts, excluded = Counter(), []
    for bid in questions:
        a,b = tables[0][bid],tables[1][bid]
        if a['grounded'] != 'valid' or b['grounded'] != 'valid':
            counts['source_invalid_or_unresolved'] += 1
            excluded.append({'blind_id': bid, 'reason': 'grounding not agreed valid'})
            continue
        if a['structurally_executable'] != b['structurally_executable'] or a['structurally_executable'] == 'uncertain':
            counts['structural_disagreement_or_uncertain'] += 1
            excluded.append({'blind_id': bid, 'reason': 'structural judgment unresolved'})
            continue
        verdict = a['structurally_executable']
        flag = key['identity'][bid].get('flag') is not None
        counts[f'{verdict}_{"flagged" if flag else "not_flagged"}'] += 1
    ratio = lambda n,d: {'numerator': n, 'denominator': d, 'value': n/d if d else None}
    invalid = counts['invalid_flagged'] + counts['invalid_not_flagged']
    valid = counts['valid_flagged'] + counts['valid_not_flagged']
    return {'format':'ac2-scope-v2-blind-analysis-v1', 'material_sha256':material_hash,
            'reviewer_declarations':declarations, 'counts':dict(counts), 'excluded':excluded,
            'invalid_flag_rate':ratio(counts['invalid_flagged'],invalid),
            'valid_flag_rate':ratio(counts['valid_flagged'],valid),
            'source_histories':len(material['histories']), 'generated_questions':len(questions),
            'unused_budget_slots':sum(x['missing'] for x in key['ledger']),
            'limitations':['Ten selected synthetic sources are not a random sample and prior novelty is unverified.',
                'Four questions per history is a maximum budget, not a required count. Only generated questions have a reviewable judgment; unused budget slots are not questions or failures.',
                'The small number of cases may make both rates imprecise or undefined.',
                'Relationship types are provisional automatically extracted inputs, not human gold.',
                'User-reported reviewer independence and blindness are not independently authenticated.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--review-1',type=Path,required=True);parser.add_argument('--review-2',type=Path,required=True)
    parser.add_argument('--confirmation',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a = parser.parse_args()
    raw = [p.read_bytes() for p in (a.review_1,a.review_2)]
    confirmation_raw = a.confirmation.read_bytes(); confirmation = json.loads(confirmation_raw)
    if confirmation.get('review_sha256') != [sha(x) for x in raw]:
        raise ValueError('User confirmation must bind both exact review files')
    protocol_raw=(STUDY/'protocol.json').read_bytes();protocol=json.loads(protocol_raw)
    key=json.loads((STUDY/'private/key.json').read_bytes())
    if key.get('protocol_sha256') != sha(protocol_raw):
        raise ValueError('Frozen protocol differs from the generated key')
    guard=ROOT/'output/proposal-delivery/ac2-scope-guard-development-20261029/scope_guard_candidate_v2.py'
    if protocol.get('guard_sha256') != sha(guard.read_bytes()):
        raise ValueError('Scope guard changed since freeze')
    result=analyze(json.loads((STUDY/'private/material.json').read_bytes()),key,protocol,[json.loads(x) for x in raw],confirmation)
    result['review_sha256']=[sha(x) for x in raw];result['user_confirmation_sha256']=sha(confirmation_raw)
    with a.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(a.output),'generated_questions':result['generated_questions']}))


if __name__ == '__main__':main()
