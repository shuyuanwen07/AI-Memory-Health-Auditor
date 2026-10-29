"""Validate two readable A reviews and restore the archived analysis format."""
import argparse
import json
import hashlib
from pathlib import Path
from scripts.analyse_phase4_a_reviews import analyse


def convert(review, template, material):
    keys={'format','reviewer_slot','material_sha256','reviewer_id','independently_completed',
          'has_seen_automated_A_results','used_ai_assistance','instructions_zh','items'}
    if set(review)!=keys or any(review.get(k)!=template.get(k) for k in
            ('format','reviewer_slot','material_sha256','instructions_zh')):
        raise ValueError('Review does not match the original template')
    if (not isinstance(review['reviewer_id'],str) or not review['reviewer_id'].strip()
            or review['independently_completed'] is not True
            or type(review['has_seen_automated_A_results']) is not bool
            or type(review['used_ai_assistance']) is not bool):
        raise ValueError('Complete the reviewer and exposure declarations')
    original={x['item_id']:x for x in material['items']}
    items=review['items']
    if len(items)!=36 or len({x.get('item_id') for x in items})!=36 or {x['item_id'] for x in items}!=set(original):
        raise ValueError('Review items are incomplete or duplicated')
    labels=[]
    for row in items:
        identity=row['item_id'];decision=row.get('review')
        if {k:v for k,v in row.items() if k!='review'}!=original[identity] or not isinstance(decision,dict):
            raise ValueError('Source, question, answer or frozen defect was changed')
        if set(decision)!={'verdict','failure_dimension','source_message_ids','defect_ids','note'}:
            raise ValueError('Review fields differ from the template')
        if not isinstance(decision.get('note'),str) or (decision.get('verdict')=='uncertain' and not decision['note'].strip()):
            raise ValueError('Uncertain decisions need a reason')
        labels.append({'item_id':identity,**decision})
    return {'schema_version':'phase4-A-response-labels-v1','material_sha256':review['material_sha256'],
            'reviewer_id':review['reviewer_id'],'independently_completed':True,
            'has_seen_automated_A_results':review['has_seen_automated_A_results'],'labels':labels}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review-1',type=Path,required=True);p.add_argument('--review-2',type=Path,required=True)
    p.add_argument('--confirmation',type=Path,required=True,help='User-confirmed human review record bound to these returns')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    confirmation=json.loads(args.confirmation.read_bytes())
    expected_hashes=[hashlib.sha256(path.read_bytes()).hexdigest() for path in (args.review_1,args.review_2)]
    if (confirmation.get('format')!='experiment-a-human-confirmation-v1'
            or confirmation.get('confirmed_by')!='user' or confirmation.get('completed_by_humans') is not True
            or confirmation.get('review_sha256')!=expected_hashes):
        raise ValueError('A user-confirmed human review record bound to both returns is required')
    source=Path('artifacts/local/phase4-20261027/A-blind-review')
    templates=Path('output/proposal-delivery/experiment-a-answer-review-2026-10-29-v1')
    reviews=[]
    for i,path in enumerate((args.review_1,args.review_2),1):
        reviews.append(convert(json.loads(path.read_bytes()),json.loads((templates/f'reviewer-{i}.json').read_bytes()),
                               json.loads((source/f'reviewer-{i}/materials.json').read_bytes())))
    private=Path('artifacts/local/phase4-20261027/private')
    result=analyse(json.loads((private/'A-review-manifest.json').read_bytes()),
                   json.loads((private/'A-identity-key.json').read_bytes()),reviews)
    result['ai_assistance']=[json.loads(p.read_bytes())['used_ai_assistance'] for p in (args.review_1,args.review_2)]
    result['user_confirmation_sha256']=hashlib.sha256(args.confirmation.read_bytes()).hexdigest()
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(args.output),'reviews':2}))


if __name__=='__main__':main()
