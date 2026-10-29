"""Create smaller standalone JSON reviews for the four-strategy study.

No human labels are inferred. A return can be merged into the original review
template only after all source text and identities are checked byte-for-byte
at the JSON value level. Previous review files are never overwritten.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile
from scripts.run_ac1_extraction import exclusive_json, read_regular

ROOT=Path(__file__).resolve().parents[1]
TEMPLATES=ROOT/'output/proposal-delivery/multi-review-complete-2026-10-28'


def digest(raw): return hashlib.sha256(raw).hexdigest()


def queue(doc):
    rows=[x for x in doc['queues'] if x['queue_id']=='four_strategy_v7_answers']
    if len(rows)!=1 or len(rows[0]['items'])!=360 or len({x['item_id'] for x in rows[0]['items']})!=360:
        raise ValueError('Expected all 360 unique blinded answers')
    return rows[0]


def make(slot):
    raw=read_regular(TEMPLATES/f'reviewer-{slot}.json'); original=json.loads(raw); q=queue(original)
    return {'format':'four-strategy-focused-review-v1','reviewer_slot':slot,'template_sha256':digest(raw),
            'instructions_zh':['请独立逐题依据问题、参考答案和来源判断被测回答。',
                '将 answer_judgment 填为 Pass、Fail 或 Uncertain；在 rationale 中写明依据。',
                '无法确定时保留 Uncertain；不要修改题目、回答、来源或编号。',
                '请如实填写审核者声明，不要查看另一位审核者的判断。'],
            'reviewer_declaration':original['reviewer_declaration'],
            'label_definitions_zh':{'answer_judgment':original['label_definitions_zh']['answer_judgment']},
            'queue':q}


def merge(slot, returned):
    expected=make(slot)
    if any(returned.get(k)!=expected[k] for k in ('format','reviewer_slot','template_sha256','instructions_zh','label_definitions_zh')):
        raise ValueError('Review identity or instructions changed')
    proposed=returned.get('queue',{})
    if {k:v for k,v in proposed.items() if k!='items'} != {k:v for k,v in expected['queue'].items() if k!='items'}:
        raise ValueError('Queue metadata changed')
    items=proposed.get('items')
    if not isinstance(items,list) or len(items)!=360:
        raise ValueError('Every blinded item must be retained')
    for item,original in zip(items,expected['queue']['items']):
        if {k:v for k,v in item.items() if k!='review'} != {k:v for k,v in original.items() if k!='review'}:
            raise ValueError('An item, ordering, response or evidence changed')
        review=item.get('review',{})
        if set(review)!={'answer_judgment','rationale'} or review['answer_judgment'] not in ('Pass','Fail','Uncertain') or not isinstance(review['rationale'],str) or not review['rationale'].strip():
            raise ValueError('Each item needs a judgment and rationale')
    declaration=returned.get('reviewer_declaration',{})
    if set(declaration)!=set(expected['reviewer_declaration']) or declaration.get('completed_by_human') is not True:
        raise ValueError('A completed human-review declaration is required')
    if not isinstance(declaration.get('reviewer_label'),str) or not declaration['reviewer_label'].strip():
        raise ValueError('Reviewer label is required')
    for field in ('used_ai_assistance','has_seen_automated_or_aggregate_results','completed_independently'):
        if not isinstance(declaration.get(field),bool): raise ValueError('Reviewer procedure must be recorded')
    progress_raw=read_regular(TEMPLATES/f'reviewer-{slot}-with-previous-progress.json')
    provenance=json.loads(read_regular(TEMPLATES/f'reviewer-{slot}-with-previous-progress.json.provenance.json'))
    if (provenance.get('reviewer_slot')!=slot or provenance.get('output_sha256')!=digest(progress_raw)
            or provenance.get('combined_packet',{}).get('template_sha256')!=expected['template_sha256']
            or provenance.get('v7_decisions_left_as_template') is not True):
        raise ValueError('Prior progress provenance does not match the review template')
    original=json.loads(progress_raw)
    if queue(original)!=expected['queue']:
        raise ValueError('Prior progress contains different or prefilled v7 items')
    # The returned declaration describes this new v7 review; the old file and
    # its separately stored declaration/provenance remain unchanged.
    original['reviewer_declaration']=copy.deepcopy(declaration)
    queue(original)['items']=copy.deepcopy(items)
    return original


def reconcile_returns(raw1, raw2):
    """Check both returns and count agreements; do not create an adjudication."""
    docs=[json.loads(raw1),json.loads(raw2)]
    # merge performs the full template, item, source and completeness checks.
    merged=[merge(1,docs[0]),merge(2,docs[1])]
    labels=[doc['reviewer_declaration']['reviewer_label'].strip() for doc in docs]
    if labels[0].casefold()==labels[1].casefold():
        raise ValueError('Two different reviewer labels are required')
    rows=[]
    for left,right in zip(docs[0]['queue']['items'],docs[1]['queue']['items']):
        if left['item_id']!=right['item_id']:
            raise ValueError('Reviewer item order differs')
        a,b=left['review']['answer_judgment'],right['review']['answer_judgment']
        status=('agreed_pass' if a==b=='Pass' else 'agreed_fail' if a==b=='Fail'
                else 'uncertain' if 'Uncertain' in (a,b) else 'disagreement')
        rows.append({'item_id':left['item_id'],'reviewer_1':a,'reviewer_2':b,'status':status})
    counts={kind:sum(row['status']==kind for row in rows) for kind in ('agreed_pass','agreed_fail','uncertain','disagreement')}
    return merged,{'format':'four-strategy-focused-reconciliation-v1','review_sha256':[digest(raw1),digest(raw2)],
                   'reviewer_declarations':[copy.deepcopy(doc['reviewer_declaration']) for doc in docs],
                   'counts':counts,'items':rows,'adjudicated':False,'automatic_scores_replaced':False,
                   'limitation':'Review identities and declared independence are not externally authenticated.'}


def strategy_summary(raw1, raw2, private_key_path, run_dir):
    """Reveal strategy only after both full returns and source binding validate."""
    from scripts.reconcile_multi_reviewer_json import _validate_v7_queue
    _,summary=reconcile_returns(raw1,raw2)
    template=json.loads(read_regular(TEMPLATES/'reviewer-1.json'))
    identity=_validate_v7_queue({'four_strategy_v7_answers':queue(template)},private_key_path,run_dir,
                                template['evidence_catalog'])
    by_strategy={}
    for item in summary['items']:
        match=identity.get(item['item_id'])
        if not match: raise ValueError('Missing frozen strategy identity')
        group=by_strategy.setdefault(match['strategy'],{'agreed_pass':0,'agreed_fail':0,'uncertain':0,'disagreement':0,'question_ids':set()})
        group[item['status']]+=1
        group['question_ids'].add(match['question_id'])
    expected={'weak_first_hit','strong_rule_based','scope_aware','temporal_importance'}
    if set(by_strategy)!=expected:
        raise ValueError('Frozen strategy set differs from expected four-arm study')
    for group in by_strategy.values():
        group['distinct_questions']=len(group.pop('question_ids'))
        group['total']=sum(group[k] for k in ('agreed_pass','agreed_fail','uncertain','disagreement'))
        if group['total']!=90 or group['distinct_questions']!=30:
            raise ValueError('Frozen strategy group is incomplete')
    return {'format':'four-strategy-human-review-summary-v1','review_sha256':summary['review_sha256'],
            'source_run_sha256':json.loads(read_regular(private_key_path))['source_run_sha256'],
            'private_key_sha256':digest(read_regular(private_key_path)),
            'reviewer_declarations':summary['reviewer_declarations'],'overall_counts':summary['counts'],
            'strategies':by_strategy,'adjudicated':False,'automatic_scores_replaced':False,
            'limitations':['Repeated answers share 30 histories; do not treat them as 90 independent histories.',
                           'Uncertain and disagreement are not failures or passes.',
                           'Reviewer identities and declared independence are not externally authenticated.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    g=sub.add_parser('prepare');g.add_argument('--output-dir',required=True)
    m=sub.add_parser('merge');m.add_argument('--slot',type=int,choices=(1,2),required=True);m.add_argument('--return-file',required=True);m.add_argument('--output',required=True)
    r=sub.add_parser('reconcile');r.add_argument('--return-1',required=True);r.add_argument('--return-2',required=True);r.add_argument('--output-dir',required=True)
    a=p.parse_args()
    if a.action=='prepare':
        out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=False,mode=0o700)
        for slot in (1,2):
            target=out/f'reviewer-{slot}.json';exclusive_json(target,make(slot))
            with zipfile.ZipFile(out/f'reviewer-{slot}.zip','x',zipfile.ZIP_DEFLATED) as z:z.write(target,target.name)
    elif a.action=='merge':exclusive_json(a.output,merge(a.slot,json.loads(read_regular(a.return_file))))
    else:
        raw1,raw2=read_regular(a.return_1),read_regular(a.return_2)
        merged,summary=reconcile_returns(raw1,raw2)
        grouped=strategy_summary(raw1,raw2,TEMPLATES/'PRIVATE-v7-identity-key.json',
            ROOT/'artifacts/local/phase4-c-openrouter-20261028-v7-four-arm')
        out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=False,mode=0o700)
        for slot,document in enumerate(merged,1):exclusive_json(out/f'merged-reviewer-{slot}.json',document)
        exclusive_json(out/'reconciliation.json',summary)
        exclusive_json(out/'strategy-summary.json',grouped)


if __name__=='__main__':main()
