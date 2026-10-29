"""Reconcile one pair of source-bound development-question review forms."""
from collections import Counter
import argparse
import json
from pathlib import Path
try:
    from scripts.reconcile_ac2_four_dimension_human_20261029 import question_decisions, sha
except ModuleNotFoundError as exc:
    if exc.name != 'scripts':raise
    from reconcile_ac2_four_dimension_human_20261029 import question_decisions, sha


def reconcile(templates, returns):
    if len(templates)!=2 or len(returns)!=2:raise ValueError('Two reviewer forms are required')
    for i in range(2):
        if returns[i].get('reviewer_id')!=f'reviewer-{i+1}':raise ValueError('Reviewer slot mismatch')
    decisions=[question_decisions(template,form) for template,form in zip(templates,returns)]
    if decisions[0].keys()!=decisions[1].keys():raise ValueError('Reviewer question sets differ')
    rows=[]
    for identity in decisions[0]:
        a,b=decisions[0][identity],decisions[1][identity]
        consensus={}
        for field in ('source_support','question_clarity','reference_answer_correctness','overall'):
            x,y=a['decisions'][field],b['decisions'][field]
            consensus[field]=x if x==y and x!='uncertain' else 'unresolved'
        rows.append({'id':identity,'history_id':a['history_id'],'reviewer_1':a,'reviewer_2':b,'consensus':consensus})
    return {'questions':len(rows),'overall_consensus':dict(Counter(r['consensus']['overall'] for r in rows)),
            'rows':rows,'provenance':'Submitted labels only; any human review, independence and exposure require separate confirmation.',
            'limitations':['These are development questions from related synthetic histories, not a population estimate.',
                           'Disagreements, missing confirmation and uncertain labels do not become valid by default.']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--template1',type=Path,required=True);parser.add_argument('--template2',type=Path,required=True)
    parser.add_argument('--review1',type=Path,required=True);parser.add_argument('--review2',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();templates=[args.template1,args.template2];returns=[args.review1,args.review2]
    if args.output.exists():raise ValueError('Output already exists; preserve previous intake')
    result=reconcile([json.loads(p.read_text()) for p in templates],[json.loads(p.read_text()) for p in returns]);result['input_sha256']=[sha(p) for p in returns]
    result['template_sha256']=[sha(p) for p in templates];args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('questions','overall_consensus')},ensure_ascii=False))

if __name__=='__main__':main()
