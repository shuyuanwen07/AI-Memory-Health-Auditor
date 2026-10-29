"""Reconcile the submitted AI-only return without changing prior judgments."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from scripts.check_review_return_20261030 import PACKET, validate

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'output/proposal-delivery/ai-review-return-20261030-v1'
PRIOR = ROOT/'output/proposal-delivery/ac2-fact-slots-product-nine-development-20261029-v1/blind-review'
FRESH = ROOT/'output/ac3-generated/b-candidate-fresh-history-pilot-20261030-v1/private-review-mapping.json'
EXISTING = ROOT/'output/ac3-generated/b-candidate-answer-development-20261029-v1/private-review-mapping.json'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    packet = RUN/'review-entries.zip'
    integrity = validate(PACKET,packet)
    groups=('01-AC2题目','02-B已有案例回答','03-B新案例回答')
    with ZipFile(packet) as z:
        reviews={group:[json.loads(z.read(f'{group}/reviewer-{i}.json')) for i in (1,2)] for group in groups}
    results={}
    for group in groups:
        left,right=reviews[group]
        assert left['completed_by_human'] is False and right['completed_by_human'] is False
        assert [x['review_item_id'] for x in left['items']]==[x['review_item_id'] for x in right['items']]
        field='overall' if group==groups[0] else 'verdict'
        counts=Counter(x['review'][field] for x in left['items'])
        results[group]={'counts':dict(counts),'total':len(left['items'])}
    old=[json.loads((PRIOR/f'ai-review-{i}.json').read_text()) for i in (1,2)]
    before=[{x['review_item_id']:x for x in review['items']} for review in old]
    changes=[]
    for item in reviews[groups[0]][0]['items']:
        ident=item['review_item_id']; a,b=(r[ident]['review']['overall'] for r in before)
        prior=a if a==b and a in ('valid','invalid') else 'unresolved'
        latest=item['review']['overall']
        if prior != latest: changes.append({'review_item_id':ident,'prior_ai_consensus':prior,'new_ai_consensus':latest})
    for group,mapping_path in ((groups[1],EXISTING),(groups[2],FRESH)):
        mapping=json.loads(mapping_path.read_text());counts={}
        for item in reviews[group][0]['items']:
            key=mapping[item['review_item_id']]
            arm=key['arm']; label=(key['type']+'_'+arm) if 'type' in key else arm
            counts.setdefault(label,Counter())[item['review']['verdict']]+=1
        results[group]['by_condition']={k:dict(v) for k,v in sorted(counts.items())}
    result={'original_zip_sha256':sha(RUN/'original.zip'),'integrity':integrity,'groups':results,
        'previous_ai_reviews_sha256':[sha(PRIOR/f'ai-review-{i}.json') for i in (1,2)],
        'ac2_differences_from_prior_ai_consensus':changes,
        'provenance':'Submitted reports describe two AI reviewers; both JSONs explicitly say completed_by_human=false. The first uses independent_review=false while separately reporting independent AI work; the second uses independent_review=true. This is not evidence of human independence. User has not yet provided an item-specific human confirmation for this return.',
        'limitations':'Repeated and related synthetic cases; AI consensus is not human gold. Prior reviewer disagreements and judgments remain intact. The retrospective 10-item wording recheck is separate and is not in this archive.'}
    (RUN/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'groups':results,'ac2_prior_differences':changes},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
