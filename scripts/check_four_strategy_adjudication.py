"""Check a returned sensitivity adjudication against both original reviews.

The file's human-confirmation claim is retained as a claim; this checker does
not establish who performed adjudication or publish a definitive result.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
from scripts.prepare_v7_focused_reviews import ROOT,TEMPLATES,reconcile_returns,queue
from scripts.reconcile_multi_reviewer_json import _validate_v7_queue


def check(raw1,raw2,adjudication_raw):
    _,review=reconcile_returns(raw1,raw2)
    decisions=json.loads(adjudication_raw)
    if decisions.get('format')!='human-confirmed-adjudication-v1':raise ValueError('Unexpected format')
    rows=decisions['decisions'];ref={r['item_id']:r for r in review['items']}
    if len(rows)!=360 or len({r['item_id'] for r in rows})!=360 or {r['item_id'] for r in rows}!=set(ref):
        raise ValueError('Adjudication items are incomplete or duplicated')
    template=json.loads((TEMPLATES/'reviewer-1.json').read_bytes())
    identity=_validate_v7_queue({'four_strategy_v7_answers':queue(template)},TEMPLATES/'PRIVATE-v7-identity-key.json',
        ROOT/'artifacts/local/phase4-c-openrouter-20261028-v7-four-arm',template['evidence_catalog'])
    total=Counter();changes=Counter();by_strategy={}
    for r in rows:
        original=ref[r['item_id']];final=r['final_judgment']
        if ((r.get('reviewer_1'),r.get('reviewer_2'))!=(original['reviewer_1'],original['reviewer_2'])
                or final not in ('Pass','Fail','Uncertain') or type(r.get('eligible_for_definitive_pass_rate')) is not bool
                or r['eligible_for_definitive_pass_rate'] != (final!='Uncertain')
                or not isinstance(r.get('reason'),str) or not r['reason'].strip()):
            raise ValueError('Adjudication differs from review identity or has invalid decision')
        total[final]+=1;changes[(original['status'],final)]+=1
        by_strategy.setdefault(identity[r['item_id']]['strategy'],Counter())[final]+=1
    if dict(total)!=decisions.get('counts'):
        raise ValueError('Adjudication totals disagree with decisions')
    return {'format':'four-strategy-adjudication-intake-v1','adjudication_sha256':hashlib.sha256(adjudication_raw).hexdigest(),
            'review_sha256':review['review_sha256'],'counts':dict(sorted(total.items())),
            'changes':[{'review_consensus':a,'adjudication':b,'count':n} for (a,b),n in sorted(changes.items())],
            'by_strategy':{k:dict(sorted(v.items())) for k,v in sorted(by_strategy.items())},
            'publication_status':'pending confirmation of adjudication scope',
            'limitation':'Preserves original reviews; matching IDs and labels alone do not verify factual correctness or human adjudication.'}


if __name__=='__main__':
    p=ROOT/'output/proposal-delivery/human-return-2026-10-29-ff607492'
    raw=[(p/f'four-reviewer-{i}-user-confirmed.json').read_bytes() for i in (1,2)]
    result=check(*raw,(p/'four-final-adjudication-original.json').read_bytes())
    with (p/'four-adjudication-intake.json').open('x',encoding='utf8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
