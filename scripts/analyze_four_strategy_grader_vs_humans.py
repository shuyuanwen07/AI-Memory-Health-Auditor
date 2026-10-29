"""Compare the saved benchmark grader with blinded human answer reviews.

This is not a comparison of the product Auditor's four-dimensional judgment.
The grader and human reviewers saw source/reference material and may share AI
influence; the historical run and both reviews remain unchanged.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path
from scripts.prepare_v7_focused_reviews import ROOT, TEMPLATES, reconcile_returns, queue
from scripts.reconcile_multi_reviewer_json import _validate_v7_queue


def analyze(raw1, raw2):
    _, reviewed = reconcile_returns(raw1, raw2)
    template=json.loads((TEMPLATES/'reviewer-1.json').read_bytes())
    run_dir=ROOT/'artifacts/local/phase4-c-openrouter-20261028-v7-four-arm'
    identity=_validate_v7_queue({'four_strategy_v7_answers':queue(template)},
        TEMPLATES/'PRIVATE-v7-identity-key.json',run_dir,template['evidence_catalog'])
    run_raw=(run_dir/'C-live.json').read_bytes();run=json.loads(run_raw)
    grades={}
    for g in run['grades']:
        key=(g['repetition'],g['strategy'],g['question_id'])
        if key in grades:raise ValueError('Duplicate saved grade')
        grades[key]=g
    if len(grades)!=360 or len(identity)!=360:raise ValueError('Incomplete saved results')
    combined=Counter();by_strategy={}
    for row in reviewed['items']:
        ident=identity[row['item_id']]; key=(ident['repetition'],ident['strategy'],ident['question_id'])
        grade=grades.get(key)
        if not grade or grade.get('target_response_sha256')!=ident['response_sha256']:
            raise ValueError('Grade does not bind the reviewed answer')
        group=by_strategy.setdefault(ident['strategy'],Counter())
        if row['status'] in ('uncertain','disagreement'):
            outcome='human_'+row['status']
        elif grade.get('verdict_usable') is not True or type(grade.get('correct')) is not bool:
            outcome='automatic_unusable'
        else:
            truth=row['status']=='agreed_pass'; auto=grade['correct']
            outcome=('both_pass' if truth and auto else 'both_fail' if not truth and not auto
                     else 'automatic_pass_human_fail' if auto else 'automatic_fail_human_pass')
        group[outcome]+=1;combined[outcome]+=1
    if sum(combined.values())!=360:raise ValueError('Incomplete comparisons')
    return {'format':'four-strategy-grader-human-comparison-v1',
            'run_sha256':hashlib.sha256(run_raw).hexdigest(),'review_sha256':reviewed['review_sha256'],
            'counts':dict(sorted(combined.items())),
            'by_strategy':{k:dict(sorted(v.items())) for k,v in sorted(by_strategy.items())},
            'limitations':['The saved LongMemEval benchmark grader is not the product Auditor.',
                           'Only human-agreed pass/fail answers enter the 2x2 comparison; uncertainties and disagreements are reported separately.',
                           'The 360 answers reuse 30 cases and three repetitions; they are not 360 independent cases.',
                           'Both reviewers used AI assistance; shared AI influence and user-reported independence limit inference.',
                           'Timing could not be verified; results are descriptive and do not establish formal acceptance.']}


if __name__=='__main__':
    source=ROOT/'output/proposal-delivery/human-return-2026-10-29-ff607492'
    result=analyze(*[(source/f'four-reviewer-{i}-user-confirmed.json').read_bytes() for i in (1,2)])
    with (ROOT/'output/proposal-delivery/four-strategy-grader-human-comparison-2026-10-29.json').open('x',encoding='utf8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
