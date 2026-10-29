"""Verify two completed AC1 reviews against the frozen extraction and aggregate them.

No result is written until both reviewers provide independent decisions. Counts
are descriptive, source-bound, and exclude partially extracted histories from
primary metrics; uncertain and disagreements remain explicitly unresolved.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from prepare_ac1_extraction_review import make_packets, read, sha


def ratio(n, d):
    return {'numerator': n, 'denominator': d, 'value': n / d if d else None}


def ingest(expected, reviews, hashes, manifest):
    if manifest != {'format':'ac1-extraction-review-manifest-v1','source_hashes':hashes,'human_decisions_created':False}:
        raise ValueError('Review manifest does not match original frozen extraction evidence.')
    if len(reviews) != 2:
        raise ValueError('Two independent reviews are required.')
    labels=[]
    for packet, original in zip(reviews, expected):
        declaration=packet.get('reviewer_declaration',{})
        label=declaration.get('reviewer_label')
        if (not isinstance(label,str) or not label.strip() or declaration.get('completed_by_human') is not True or
                declaration.get('completed_independently') is not True or type(declaration.get('used_ai_assistance')) is not bool):
            raise ValueError('Each reviewer must explicitly declare their identity label, independent human completion and AI assistance.')
        labels.append(label.strip().casefold())
        clean=copy.deepcopy(packet)
        for key in ('status','human_review_confirmation','ai_reviewer_declaration'):
            clean.pop(key,None)
        clean['reviewer_declaration']=original['reviewer_declaration']
        for history in clean.get('histories',[]):
            for candidate in history.get('candidates',[]):candidate['review']={'supported':None,'matched_reference_fact_ids':[],'note':''}
            for relation in history.get('relationships',[]):relation['review']={'correct':None,'note':''}
        if clean != original:
            raise ValueError('Review changed source, candidates, reference, IDs, slot or evidence; use the original packet.')
        for history in packet['histories']:
            fact_ids={x['fact']['memory_id'] for x in history['reviewed_reference_facts'] if x['reference_status']=='reviewed'}
            for item in history['candidates']:
                r=item['review']; ids=r.get('matched_reference_fact_ids')
                if set(r) != {'supported','matched_reference_fact_ids','note'} or r['supported'] not in ('valid','invalid','uncertain') or not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(x not in fact_ids for x in ids) or not isinstance(r['note'],str):
                    raise ValueError('Invalid candidate review or unreviewed fact mapping.')
                if r['supported'] != 'valid' and (ids or not r['note'].strip()):raise ValueError('Invalid/uncertain candidates require a note and no matched facts.')
            for item in history['relationships']:
                r=item['review']
                if set(r)!={'correct','note'} or r['correct'] not in ('valid','invalid','uncertain') or not isinstance(r['note'],str) or (r['correct']!='valid' and not r['note'].strip()):
                    raise ValueError('Invalid relationship review or missing note.')
    if labels[0]==labels[1]:raise ValueError('Reviewer labels must be different; identity is not independently authenticated.')
    groups={'completed':[], 'partial':[], 'other':[]}
    unresolved=[]
    for h1,h2 in zip(reviews[0]['histories'],reviews[1]['histories']):
        status=h1['extraction_status']; group=status if status in ('completed','partial') else 'other'
        facts={x['fact']['memory_id'] for x in h1['reviewed_reference_facts'] if x['reference_status']=='reviewed'}
        candidates={}; supported=invalid=undecided=0
        for a,b in zip(h1['candidates'],h2['candidates']):
            ra,rb=a['review'],b['review']; cid=a['candidate']['candidate_id']
            if ra['supported']==rb['supported']=='valid' and set(ra['matched_reference_fact_ids'])==set(rb['matched_reference_fact_ids']):
                supported+=1;candidates[cid]=set(ra['matched_reference_fact_ids'])
            elif ra['supported']==rb['supported']=='invalid':invalid+=1
            else:
                undecided+=1;unresolved.append({'history_id':h1['history_id'],'kind':'candidate','id':cid,'reviews':[ra,rb]})
        covered=set().union(*candidates.values()) if candidates else set()
        edges=[]; valid_edges=invalid_edges=undecided_edges=0
        for a,b in zip(h1['relationships'],h2['relationships']):
            ra,rb=a['review'],b['review']; edge=a['relationship']
            if ra['correct']==rb['correct']=='valid':valid_edges+=1;edges.append(edge)
            elif ra['correct']==rb['correct']=='invalid':invalid_edges+=1
            else:undecided_edges+=1;unresolved.append({'history_id':h1['history_id'],'kind':'relationship','id':edge['relationship_id'],'reviews':[ra,rb]})
        references=[x['relationship'] for x in h1['reviewed_reference_relationships'] if x['reference_status']=='reviewed']
        matched=0
        for ref in references:
            def matches(e):
                if e['relationship_type']!=ref['relationship_type']:return False
                a=candidates.get(e['from_candidate_id'],set());b=candidates.get(e['to_candidate_id'],set())
                direct=ref['memory_id'] in a and ref['target_memory_id'] in b
                reverse=ref['relationship_type']=='CONFLICT' and ref['memory_id'] in b and ref['target_memory_id'] in a
                return direct or reverse
            matched+=any(matches(e) for e in edges)
        groups[group].append({'history_id':h1['history_id'],'status':status,'supported':supported,'invalid':invalid,'undecided':undecided,
            'reviewed_reference_facts':len(facts),'covered_reference_facts':len(facts & covered),'valid_edges':valid_edges,'invalid_edges':invalid_edges,
            'undecided_edges':undecided_edges,'reference_edges':len(references),'matched_reference_edges':matched})
    complete=groups['completed']; total=lambda k:sum(h[k] for h in complete)
    observed=complete+groups['partial']
    observed_total=lambda k:sum(h[k] for h in observed)
    sensitivity={
        'included_completed_histories':len(complete), 'included_partial_histories':len(groups['partial']),
        'excluded_not_completed_or_partial_histories':len(groups['other']),
        'supported_candidate_precision_decided':ratio(observed_total('supported'),observed_total('supported')+observed_total('invalid')),
        'candidate_counts':{'supported':observed_total('supported'), 'invalid':observed_total('invalid'), 'undecided':observed_total('undecided')},
        'reference_fact_id_matched_coverage':ratio(observed_total('covered_reference_facts'),observed_total('reviewed_reference_facts')),
        'relationship_precision_decided':ratio(observed_total('valid_edges'),observed_total('valid_edges')+observed_total('invalid_edges')),
        'reference_relationship_coverage_conservative':ratio(observed_total('matched_reference_edges'),observed_total('reference_edges')),
        'undecided_relationships':observed_total('undecided_edges'),
        'interpretation':'Includes existing partial-history candidates, but missing extraction output is unknown, not a confirmed missing fact or edge. Reference-ID mapping can include partial matches and missing output is unknown; it is not strict recall or a definitive omission rate.'}
    return {'format':'ac1-extraction-reviewed-summary-v1','human_review_declarations':'Two different self-reported independent human reviewers; identity and independence not independently authenticated.',
        'reviewer_labels':[p['reviewer_declaration']['reviewer_label'] for p in reviews],
        'ai_assistance':[p['reviewer_declaration']['used_ai_assistance'] for p in reviews],
        'original_ai_declarations':[p.get('ai_reviewer_declaration') for p in reviews],
        'primary_complete_histories':len(complete),'partial_histories':len(groups['partial']),'other_histories':len(groups['other']),
        'supported_candidate_precision_decided':ratio(total('supported'),total('supported')+total('invalid')),
        'reference_fact_id_matched_coverage':ratio(total('covered_reference_facts'),total('reviewed_reference_facts')),
        'relationship_precision_decided':ratio(total('valid_edges'),total('valid_edges')+total('invalid_edges')),
        'reference_relationship_coverage_conservative':ratio(total('matched_reference_edges'),total('reference_edges')),
        'undecided_candidates':total('undecided'),'undecided_relationships':total('undecided_edges'),
        'histories':groups,'unresolved':unresolved,'sensitivity_including_partial':sensitivity,
        'limitations':['Reviewed reference facts are not necessarily exhaustive. Reference fact ID coverage measures whether any candidate was mapped to an ID; a partial match may not cover the entire reference fact, so it is not a strict fact recall or lower bound.','Relationship coverage uses mutually agreed mappings and can be affected by partial endpoint matches, uncertain reviews and disagreements; it is not a definitive omission rate.','Partial and failed histories are shown separately and excluded from primary metrics; the sensitivity analysis includes observed partial output with explicit denominators.','Self-reported independence and identities are not independently authenticated.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('frozen','frozen-sha256','source','journal-dir','manifest','review-1','review-2','output'):p.add_argument('--'+arg,required=True)
    a=p.parse_args()
    expected,hashes=make_packets(a.frozen,a.frozen_sha256,a.source,a.journal_dir,allow_partial=True)
    inputs=[Path(a.manifest),Path(a.review_1),Path(a.review_2)]
    raw=[read(x) for x in inputs]; manifest,r1,r2=map(json.loads,raw)
    result=ingest(expected,[r1,r2],hashes,manifest)
    result['source_hashes']=hashes;result['review_and_manifest_sha256']={str(x):sha(b) for x,b in zip(inputs,raw)}
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'output':a.output,'completed_histories':result['primary_complete_histories'],'unresolved_items':len(result['unresolved'])}))

if __name__=='__main__':main()
