"""Compare two human-reviewed AC1 extractions on the same complete histories.

The reference catalogue is not necessarily exhaustive and fact-ID coverage
may include partial matches; this comparison is not strict recall.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path


def compare(old_raw,new_raw,*,iterations=2000,seed=5623):
    old,new=json.loads(old_raw),json.loads(new_raw)
    for summary in (old,new):
        if summary.get('format')!='ac1-extraction-reviewed-summary-v1':
            raise ValueError('Two reviewed extraction summaries are required')
        if len(summary.get('reviewer_labels',[]))!=2:
            raise ValueError('Two human reviewer declarations are required')
    if old['source_hashes']['source']!=new['source_hashes']['source']:
        raise ValueError('Retest and baseline use different reviewed sources')
    before={h['history_id']:h for h in old['histories']['completed']}
    after={h['history_id']:h for h in new['histories']['completed']}
    if len(before)!=len(old['histories']['completed']) or len(after)!=len(new['histories']['completed']):
        raise ValueError('Duplicate completed history')
    ids=sorted(set(before)&set(after))
    if not ids:raise ValueError('No paired complete histories')
    for ident in ids:
        if any(before[ident][key]!=after[ident][key] for key in ('reviewed_reference_facts','reference_edges')):
            raise ValueError('Reference denominators differ within a matched history')
    def summarize(rows):
        total=lambda key:sum(row[key] for row in rows)
        def metric(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None}
        return {'supported_candidate_precision_decided':metric(total('supported'),total('supported')+total('invalid')),
                'reference_fact_id_matched_coverage':metric(total('covered_reference_facts'),total('reviewed_reference_facts')),
                'relationship_precision_decided':metric(total('valid_edges'),total('valid_edges')+total('invalid_edges')),
                'reference_relationship_coverage':metric(total('matched_reference_edges'),total('reference_edges')),
                'undecided_candidates':total('undecided'),'undecided_relationships':total('undecided_edges')}
    old_metrics=summarize([before[i] for i in ids]);new_metrics=summarize([after[i] for i in ids])
    if type(iterations) is not int or iterations<100:raise ValueError('At least 100 bootstrap iterations required')
    rng=random.Random(seed); keys=list(old_metrics)[:4];samples={k:[] for k in keys}
    for _ in range(iterations):
        draw=[rng.choice(ids) for _ in ids]
        a=summarize([before[i] for i in draw]);b=summarize([after[i] for i in draw])
        for key in keys:
            if a[key]['value'] is not None and b[key]['value'] is not None:
                samples[key].append(b[key]['value']-a[key]['value'])
    intervals={}
    for key,vals in samples.items():
        vals.sort();n=len(vals)
        intervals[key]={'valid_iterations':n,'lower':vals[int((n-1)*.025)] if n>=iterations*.9 else None,
                        'upper':vals[int((n-1)*.975)] if n>=iterations*.9 else None}
    return {'format':'ac1-reviewed-paired-comparison-v1',
            'old_summary_sha256':hashlib.sha256(old_raw).hexdigest(),
            'new_summary_sha256':hashlib.sha256(new_raw).hexdigest(),
            'source_sha256':old['source_hashes']['source'],'paired_complete_histories':len(ids),
            'paired_history_ids':ids,'old':old_metrics,'new':new_metrics,
            'excluded_old_incomplete':[h['history_id'] for group in ('partial','other') for h in old['histories'][group]],
            'excluded_new_incomplete':[h['history_id'] for group in ('partial','other') for h in new['histories'][group]],
            'bootstrap_new_minus_old':intervals,'bootstrap_iterations':iterations,'bootstrap_seed':seed,
            'limitations':['Source is a selected synthetic catalogue, not a random population sample.',
                'Fact-ID matched coverage can reflect partial fact matches and is not strict recall.',
                'Partial and failed histories are excluded from the matched comparison; they remain separately reported.',
                'Review identity and independence are user reported and not independently authenticated.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=compare(args.old.read_bytes(),args.new.read_bytes())
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'paired_complete_histories':result['paired_complete_histories'],'output':str(args.output)}))


if __name__=='__main__':main()
