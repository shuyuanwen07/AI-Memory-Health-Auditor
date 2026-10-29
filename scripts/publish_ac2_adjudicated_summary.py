"""Aggregate source-bound human-confirmed AC2 adjudication without erasing uncertainty.

The confirmation concerns previously AI-proposed sequential judgments. It is
not a claim of a new independent blind review or a generator retest.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'output/proposal-delivery'
INTAKE = DIR / 'review-package-intake-2026-10-28'
SUMMARY = DIR / 'ac2-generation-reviewed-summary-2026-10-28-v1.json'
USER_COPY = INTAKE / 'user-confirmed/ac2-adjudication.json'
CONFIRM = INTAKE / 'user-confirmed/confirmation.json'
ZIP = INTAKE / 'original.zip'
MEMBER = '审核汇总包/09_AC2结构裁定/结构裁定.json'
OUTPUT = DIR / 'ac2-generation-adjudicated-summary-2026-10-28-v1.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('Evidence must be a regular file')
    return path.read_bytes()


def build(summary_raw, reviews_raw, original_raw, confirmed_raw, confirmation_raw):
    summary, original, confirmed, user = map(json.loads, (summary_raw, original_raw, confirmed_raw, confirmation_raw))
    reviews = [json.loads(raw) for raw in reviews_raw]
    if (summary.get('format') != 'ac2-reference-generation-reviewed-summary-v1' or
        original.get('format') != 'ac2-structural-disagreement-adjudication-v1' or
        original.get('source_summary_sha256') != sha(summary_raw) or
        original.get('review_1_sha256') != sha(reviews_raw[0])):
        raise ValueError('Source summary or original review binding differs')
    evidence = summary.get('evidence_sha256', {})
    for i, raw in enumerate(reviews_raw, 1):
        matching = [value for name, value in evidence.items() if name.endswith(f'/reviewer-{i}-user-confirmed.json')]
        if matching != [sha(raw)]:
            raise ValueError('The two reviews must match the source summary')
    if (user.get('format') != 'review-package-user-confirmation-v1' or
        user.get('user_responses', {}).get('ac2') != '已逐项人工核对并认可'):
        raise ValueError('User confirmation is missing')
    entries = [x for x in user.get('items', []) if x.get('kind') == 'ac2-adjudication']
    if len(entries) != 1 or entries[0].get('original_sha256') != sha(original_raw) or entries[0].get('confirmed_sha256') != sha(confirmed_raw):
        raise ValueError('User confirmation does not bind both versions')
    if (original.get('human_decisions_created') is not False or
        original.get('adjudicator_declaration', {}).get('completed_by_human') is not False or
        original.get('adjudicator_declaration', {}).get('used_ai_assistance') is not True or
        confirmed.get('adjudicator_declaration', {}).get('completed_by_human') is not True or
        confirmed.get('adjudicator_declaration', {}).get('used_ai_assistance') is not True):
        raise ValueError('Original AI and later human confirmation disclosures are required')
    lhs, rhs = copy.deepcopy(original), copy.deepcopy(confirmed)
    lhs.pop('adjudicator_declaration', None); rhs.pop('adjudicator_declaration', None)
    if lhs != rhs:
        raise ValueError('Confirmed file changed decisions or source content')
    unresolved = {(x['history_id'], x['test_id']): x for x in summary['unresolved']}
    adjudicated = {}
    review_histories = [{h['history_id']: h for h in r['histories']} for r in reviews]
    for h in original['histories']:
        hid = h['history_id']
        if hid not in review_histories[0] or hid not in review_histories[1]:
            raise ValueError('Unknown history in adjudication')
        first, second = [r[hid] for r in review_histories]
        if h['source_messages'] != first['source_messages'] or h['reviewed_reference'] != first['reviewed_reference']:
            raise ValueError('Adjudication source or reference differs')
        tests = [{x['test']['test_id']: x for x in history['generated_tests']} for history in (first, second)]
        for c in h['cases']:
            key = (hid, c['test_id'])
            if key in adjudicated or key not in unresolved or c['test_id'] not in tests[0] or c['test_id'] not in tests[1]:
                raise ValueError('Unknown, repeated or already resolved adjudication')
            item = tests[0][c['test_id']]['test']
            if (c['dimension'] != item['dimension'] or c['question'] != item['prompt'] or
                c['expected_behavior'] != item['expected_behavior'] or c['supporting_memory_ids'] != item['supporting_memory_ids'] or
                c['reviewer_1'] != tests[0][c['test_id']]['review'] or c['reviewer_2'] != tests[1][c['test_id']]['review'] or
                c['reviewer_1'] != unresolved[key]['reviewer_1'] or c['reviewer_2'] != unresolved[key]['reviewer_2']):
                raise ValueError('Adjudication did not preserve the exact blind reviews and test')
            baseline_ground = c['reviewer_1']['grounded'] if c['reviewer_1']['grounded'] == c['reviewer_2']['grounded'] and c['reviewer_1']['grounded'] != 'uncertain' else 'unresolved'
            if c['requires_grounding_adjudication'] != (baseline_ground == 'unresolved'):
                raise ValueError('Grounding adjudication scope differs from source judgments')
            decision = c.get('adjudication', {})
            if (decision.get('structurally_executable') not in ('valid', 'invalid', 'uncertain') or
                decision.get('grounded') not in (('valid', 'invalid', 'uncertain') if c['requires_grounding_adjudication'] else ('not_required',)) or
                not isinstance(decision.get('reason'), str) or not decision['reason'].strip()):
                raise ValueError('Missing or malformed adjudication decision')
            adjudicated[key] = decision
    if set(adjudicated) != set(unresolved):
        raise ValueError('Adjudication does not cover every previously unresolved case')
    def base(r1, r2, key):
        a, b = r1[key], r2[key]
        return a if a == b and a != 'uncertain' else 'unresolved'
    result = {field: {'valid':0,'invalid':0,'unresolved':0,'denominator':0} for field in ('grounded','structurally_executable','joint')}
    changed = {'structural_invalid':0,'structural_uncertain':0,'structural_valid':0,'grounding_valid':0,'grounding_invalid':0,'grounding_uncertain':0}
    for first, second in zip(reviews[0]['histories'], reviews[1]['histories']):
        if first['history_id'] != second['history_id'] or len(first['generated_tests']) != len(second['generated_tests']):
            raise ValueError('Original reviews do not align')
        for x, y in zip(first['generated_tests'], second['generated_tests']):
            key = (first['history_id'], x['test']['test_id'])
            if x['test'] != y['test']:
                raise ValueError('Original reviews refer to different tests')
            values = {field:base(x['review'],y['review'],field) for field in ('grounded','structurally_executable')}
            if key in adjudicated:
                a=adjudicated[key]; structural=a['structurally_executable']
                changed['structural_'+structural]+=1
                values['structurally_executable'] = 'unresolved' if structural == 'uncertain' else structural
                if a['grounded'] != 'not_required':
                    changed['grounding_'+a['grounded']]+=1
                    values['grounded'] = 'unresolved' if a['grounded'] == 'uncertain' else a['grounded']
            values['joint'] = 'valid' if values['grounded'] == values['structurally_executable'] == 'valid' else ('invalid' if 'invalid' in (values['grounded'],values['structurally_executable']) else 'unresolved')
            for field,value in values.items():
                result[field][value]+=1; result[field]['denominator']+=1
    if any(x['denominator'] != 120 for x in result.values()):
        raise ValueError('Review count differs from the frozen 120 questions')
    return {'format':'ac2-human-confirmed-adjudication-summary-v1','results':result,'adjudication_counts':changed,
            'prior_review_counts':summary['results'],
            'provenance':'User reports item-by-item human acceptance of a sequential AI adjudication after prior labels were known. This is not independent blind adjudication; identity is not independently authenticated.',
            'limitations':['Uncertain remains unresolved, not pass or fail.', 'Human-confirmed reference memory input; not evidence of automatic memory extraction.', 'The original generated questions were not rerun and the revised candidates are not evaluated here.', 'Synthetic histories do not constitute an independently sampled population.'],
            'source_sha256':{'prior_summary':sha(summary_raw),'review_1':sha(reviews_raw[0]),'review_2':sha(reviews_raw[1]),
                             'original_adjudication':sha(original_raw),'confirmed_adjudication':sha(confirmed_raw),'user_confirmation':sha(confirmation_raw)}}


def main():
    summary_raw = _read(SUMMARY)
    reviews_raw = [_read(DIR / f'ac2-generation-review-intake-2026-10-28/reviewer-{i}-user-confirmed.json') for i in (1,2)]
    with zipfile.ZipFile(ZIP) as archive:
        original_raw=archive.read(MEMBER)
    result=build(summary_raw,reviews_raw,original_raw,_read(USER_COPY),_read(CONFIRM))
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(OUTPUT),'results':result['results'],'adjudication_counts':result['adjudication_counts']}))


if __name__ == '__main__':
    main()
