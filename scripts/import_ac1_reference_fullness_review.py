#!/usr/bin/env python3
"""Reconcile two source-bound AC1 fullness reviews without treating uncertainty as failure."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'output/proposal-delivery/ac1-reference-fullness-followup-2026-10-28-v1'
SUMMARY=ROOT/'output/proposal-delivery/ac1-extraction-reviewed-summary-2026-10-28-v2.json'
PRIOR=[ROOT/f'output/proposal-delivery/ac1-extraction-review-intake-2026-10-28/reviewer-{i}-user-confirmed.json' for i in (1,2)]
RESULTS=ROOT/'output/ac3-generated/AC1-1a74cc906df755f6fc2a4855'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def context_sha(doc):
    d=copy.deepcopy(doc); d.pop('reviewer_declaration')
    for h in d['histories']:
        for x in h['matched_reference_items']: x.pop('review')
    return sha(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())

def load_review(path,slot,manifest):
    raw=path.read_bytes(); doc=json.loads(raw)
    if doc['format']!='ac1-reference-fullness-human-review-v1' or doc['reviewer_slot']!=slot: raise ValueError('Wrong reviewer slot or format')
    if context_sha(doc)!=manifest['reviewer_context_sha256'][slot-1]: raise ValueError('Frozen question, source, candidate, or prior-review context changed')
    if doc['source_summary_sha256']!=manifest['summary_sha256'] or doc['prior_review_sha256']!=manifest['prior_review_sha256'][slot-1]: raise ValueError('Incorrect source binding')
    d=doc['reviewer_declaration']
    if d['completed_by_human'] is not True or d['completed_independently'] is not True or not isinstance(d['used_ai_assistance'],bool): raise ValueError('Human, independent and AI-assistance declarations must be filled')
    if not isinstance(d['reviewer_label'],str) or not d['reviewer_label'].strip(): raise ValueError('Reviewer label missing')
    result={}
    for h in doc['histories']:
        for item in h['matched_reference_items']:
            decision=item['review']; value=decision['fullness']
            if value not in ('full','partial','none','uncertain') or not isinstance(decision['note'],str): raise ValueError('Each matched fact requires a valid fullness and note field')
            key=(h['history_id'],item['reference_fact']['memory_id'])
            if key in result: raise ValueError('Duplicate matched reference')
            result[key]={'status':h['extraction_status'],'fullness':value,'note':decision['note']}
    return doc,result,sha(raw)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewer-1',type=Path,required=True);parser.add_argument('--reviewer-2',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args(); manifest=json.loads((PACK/'manifest.json').read_bytes())
    if sha(SUMMARY.read_bytes())!=manifest['summary_sha256'] or [sha(p.read_bytes()) for p in PRIOR]!=manifest['prior_review_sha256']: raise ValueError('Previously reviewed source evidence changed')
    summary=json.loads(SUMMARY.read_bytes())
    for h in summary['histories']['completed']+summary['histories']['partial']:
        key=h['history_id']+'.result'; file=RESULTS/(key+'.json')
        if sha(file.read_bytes())!=summary['source_hashes'][key]: raise ValueError('Extraction receipt changed: '+key)
    d1,r1,sha1=load_review(a.reviewer_1,1,manifest); d2,r2,sha2=load_review(a.reviewer_2,2,manifest)
    if r1.keys()!=r2.keys() or len(r1)!=236: raise ValueError('Reviewer item sets do not match')
    if d1['reviewer_declaration']['reviewer_label'].strip()==d2['reviewer_declaration']['reviewer_label'].strip(): raise ValueError('Reviewer labels must differ')
    rows=[]
    for key,v1 in sorted(r1.items()):
        v2=r2[key]
        if v1['status']!=v2['status']: raise ValueError('History statuses differ')
        x,y=v1['fullness'],v2['fullness']
        decision=x if x==y and x!='uncertain' else 'unresolved'
        rows.append({'history_id':key[0],'reference_fact_id':key[1],'extraction_status':v1['status'],'reviewer_1':x,'reviewer_2':y,'consensus':decision})
    def totals(statuses):
        eligible=[r for r in rows if r['extraction_status'] in statuses]; counts=Counter(r['consensus'] for r in eligible)
        return {'matched_references':len(eligible),'full':counts['full'],'partial':counts['partial'],'none':counts['none'],'unresolved':counts['unresolved'],'unmatched_prior_references':3,'unmatched_note':'No mutual prior mapping; not independently adjudicated as absent.'}
    out={'format':'ac1-reference-fullness-reviewed-summary-v1','review_sha256':[sha1,sha2],'source_summary_sha256':manifest['summary_sha256'],'user_reported_independent_human_review':True,'identity_independence_independently_verified':False,'ai_assistance':[d1['reviewer_declaration']['used_ai_assistance'],d2['reviewer_declaration']['used_ai_assistance']],'complete_29_histories':totals({'completed'}),'including_partial_observed_output':totals({'completed','partial'}),'items':rows,'limitations':['Reviewed references are not exhaustive.','Unmatched prior references were not re-reviewed; no mutual mapping is not a definitive omission.','H04 missing output is unknown, not a confirmed omission.','Uncertain judgments and disagreements remain unresolved.']}
    with a.output.open('x',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':str(a.output),'complete_29_histories':out['complete_29_histories'],'including_partial_observed_output':out['including_partial_observed_output']},ensure_ascii=False))

if __name__=='__main__': main()
