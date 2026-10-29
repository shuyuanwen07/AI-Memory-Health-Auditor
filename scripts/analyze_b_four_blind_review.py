"""Analyze two independent reviews of the frozen B four-strategy answers."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from scripts.prepare_b_four_blind_review import canonical


def analyze(material,key,reviews):
    sha=hashlib.sha256(canonical(material)).hexdigest()
    if key.get('material_sha256')!=sha or len(reviews)!=2:
        raise ValueError('Material, key or review count differs')
    answers={a['blind_id']:a for a in material['answers']}
    questions={q['question_id']:q for q in material['questions']}
    mapping=key['mapping']
    if len(answers)!=144 or len(questions)!=12 or set(answers)!=set(mapping):
        raise ValueError('Frozen questions or answer identities are incomplete')
    labels=set();answer_tables=[];question_tables=[];decls=[]
    for slot,review in enumerate(reviews,1):
        if (review.get('format')!='b-four-strategy-human-review-v1' or review.get('reviewer_slot')!=slot
                or review.get('material_sha256')!=sha or any(review.get(k)!=material[k] for k in ('histories','questions','answers'))):
            raise ValueError('Reviewer changed source, question or answer material')
        d=review.get('reviewer_declaration',{});label=d.get('reviewer_label')
        if (not isinstance(label,str) or not label.strip() or label.strip().casefold() in labels
                or d.get('completed_by_human') is not True or d.get('completed_independently') is not True
                or type(d.get('seen_current_automatic_results')) is not bool or type(d.get('seen_other_review')) is not bool
                or type(d.get('used_ai_assistance')) is not bool or (d.get('previously_seen_prior_b_results') is not None and type(d.get('previously_seen_prior_b_results')) is not bool)):
            raise ValueError('Two distinct human reviewer declarations are required')
        labels.add(label.strip().casefold());decls.append(d)
        qr=review.get('question_reviews');ar=review.get('answer_reviews')
        if not isinstance(qr,list) or not isinstance(ar,list) or len(qr)!=12 or len(ar)!=144:
            raise ValueError('Complete question and answer reviews are required')
        qt={r['question_id']:r for r in qr};at={r['blind_id']:r for r in ar}
        if len(qt)!=12 or set(qt)!=set(questions) or len(at)!=144 or set(at)!=set(answers):
            raise ValueError('Review IDs differ or are duplicated')
        for row in qr:
            if (type(row.get('valid')) is not bool and row.get('valid')!='uncertain') or not isinstance(row.get('note'),str):
                raise ValueError('Invalid question review')
            if row['valid'] is not True and not row['note'].strip():raise ValueError('Invalid/uncertain question needs a reason')
        for row in ar:
            verdict=row.get('verdict');category=row.get('failure_dimension')
            if (verdict not in ('pass','fail','uncertain') or category not in (None,'accuracy','freshness','conflict_resolution','appropriate_use')
                    or (verdict!='fail' and category is not None) or not isinstance(row.get('note'),str)):
                raise ValueError('Invalid answer judgment')
            if verdict=='uncertain' and not row['note'].strip():raise ValueError('Uncertain answer needs a reason')
        answer_tables.append(at);question_tables.append(qt)
    question_status={qid:'valid' if all(t[qid]['valid'] is True for t in question_tables) else 'unresolved_or_invalid' for qid in questions}
    groups=defaultdict(Counter);dimensions=defaultdict(Counter);unresolved=[]
    for bid,item in answers.items():
        info=mapping[bid]
        if hashlib.sha256(item['answer'].encode()).hexdigest()!=item['answer_sha256'] or item['answer_sha256']!=info['answer_sha256']:
            raise ValueError('Answer fingerprint differs from private identity')
        strategy=info['strategy'];dimension=info['dimension'];group=groups[strategy]
        group['total']+=1
        if question_status[item['question_id']]!='valid':
            group['invalid_or_unresolved_question']+=1;unresolved.append(bid);continue
        left,right=(t[bid]['verdict'] for t in answer_tables)
        if left!=right or left=='uncertain':
            group['unresolved_answer']+=1;unresolved.append(bid);continue
        group[left]+=1;dimensions[(strategy,info['history_id'],dimension)][left]+=1
    output={}
    for strategy,c in sorted(groups.items()):
        per_dimension={};histories=[]
        for dim in ('accuracy','freshness','conflict_resolution','appropriate_use'):
            d=sum((v for (s,h,k),v in dimensions.items() if s==strategy and k==dim),Counter())
            n=d['pass']+d['fail'];per_dimension[dim]={'pass':d['pass'],'fail':d['fail'],'decided':n,'rate':d['pass']/n if n else None}
        for hid in sorted({v['history_id'] for v in mapping.values()}):
            values=[]
            for dim in ('accuracy','freshness','conflict_resolution','appropriate_use'):
                d=dimensions[(strategy,hid,dim)];n=d['pass']+d['fail']
                if n:values.append(d['pass']/n)
            if len(values)==4:histories.append(sum(values)/4)
        n=c['pass']+c['fail']
        output[strategy]={'counts':dict(c),'decided_rate':c['pass']/n if n else None,
            'dimensions':per_dimension,'history_macro_mean':sum(histories)/len(histories) if histories else None,
            'complete_history_macros':len(histories)}
    return {'format':'b-four-strategy-human-summary-v1','material_sha256':sha,'reviewer_declarations':decls,
        'current_results_blinded':all(not d['seen_current_automatic_results'] and not d['seen_other_review'] for d in decls),
        'strategies':output,'unresolved_answer_count':len(unresolved),
        'limitations':['Only three previously observed synthetic histories; repeated answers are correlated.',
            'Question and answer uncertainties are retained and excluded from decided rates.',
            'Reviewer independence and exposure are user reported, not independently authenticated.',
            'Prior exposure to earlier B results can be unknown and is recorded without assumption.',
            'History macro excludes any history missing a decided dimension; compare denominators.']}


def verify_user_confirmation(confirmation, review_paths):
    expected=[hashlib.sha256(path.read_bytes()).hexdigest() for path in review_paths]
    if (confirmation.get('format')!='experiment-b-human-confirmation-v1'
            or confirmation.get('confirmed_by')!='user' or confirmation.get('completed_by_humans') is not True
            or confirmation.get('review_sha256')!=expected):
        raise ValueError('A user-confirmed human review record bound to both returns is required')


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--review-1',type=Path,required=True);p.add_argument('--review-2',type=Path,required=True)
    p.add_argument('--confirmation',type=Path,required=True,help='User confirmation bound to the returned review files')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    confirmation=json.loads(a.confirmation.read_bytes())
    verify_user_confirmation(confirmation, (a.review_1,a.review_2))
    root=Path('output/proposal-delivery/experiment-b-four-strategy-20261029-v1')
    data=analyze(json.loads((root/'private-review-material.json').read_bytes()),json.loads((root/'private-review-key.json').read_bytes()),
                 [json.loads(a.review_1.read_bytes()),json.loads(a.review_2.read_bytes())])
    data['user_confirmation_sha256']=hashlib.sha256(a.confirmation.read_bytes()).hexdigest()
    with a.output.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(a.output),'reviewers':2}))


if __name__=='__main__':main()
