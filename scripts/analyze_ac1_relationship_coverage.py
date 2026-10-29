"""Break down existing AC1 reference-edge matches without changing the reviews."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def analyze(summary_path):
    summary_raw = summary_path.read_bytes()
    summary = json.loads(summary_raw)
    files = summary['review_and_manifest_sha256']
    paths = [next(Path(p) for p in files if p.endswith(f'reviewer-{i}-user-confirmed.json')) for i in (1, 2)]
    reviews = []
    for path in paths:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != files[str(path)]:
            raise ValueError('Review digest mismatch')
        reviews.append(json.loads(raw))
    grouped = Counter()
    unmatched_reasons = Counter()
    unmatched_candidate_status = Counter()
    endpoint_separation = Counter()
    complete_ids = {h['history_id'] for h in summary['histories']['completed']}
    histories = [{h['history_id']:h for h in r['histories']} for r in reviews]
    if not complete_ids.issubset(histories[0]) or not complete_ids.issubset(histories[1]):
        raise ValueError('Reviewed histories missing')
    for hid in sorted(complete_ids):
        a,b = (h[hid] for h in histories)
        if a['extraction_status'] != 'completed' or b['extraction_status'] != 'completed':
            raise ValueError('History is not complete')
        ca,cb = ({x['candidate']['candidate_id']:x for x in h['candidates']} for h in (a,b))
        ra,rb = ({x['relationship']['relationship_id']:x for x in h['relationships']} for h in (a,b))
        if set(ca)!=set(cb) or set(ra)!=set(rb) or a['reviewed_reference_relationships']!=b['reviewed_reference_relationships']:
            raise ValueError('Review packet contents differ')
        mappings={}
        for ident in ca:
            x,y=ca[ident],cb[ident]
            if x['candidate']!=y['candidate']:
                raise ValueError('Candidate contents differ')
            u,v=x['review'],y['review']
            if u['supported']==v['supported']=='valid' and set(u['matched_reference_fact_ids'])==set(v['matched_reference_fact_ids']):
                mappings[ident]=set(u['matched_reference_fact_ids'])
        edges=[]
        for ident in ra:
            x,y=ra[ident],rb[ident]
            if x['relationship']!=y['relationship']:
                raise ValueError('Relationship contents differ')
            if x['review']['correct']==y['review']['correct']=='valid':edges.append(x['relationship'])
        for item in a['reviewed_reference_relationships']:
            if item['reference_status']!='reviewed':continue
            ref=item['relationship'];kind=ref['relationship_type']
            def matches(edge):
                if edge['relationship_type']!=kind:return False
                left=mappings.get(edge['from_candidate_id'],set());right=mappings.get(edge['to_candidate_id'],set())
                return (ref['memory_id'] in left and ref['target_memory_id'] in right) or (kind=='CONFLICT' and ref['memory_id'] in right and ref['target_memory_id'] in left)
            is_matched=any(matches(edge) for edge in edges)
            grouped[(kind,'matched' if is_matched else 'unmatched')]+=1
            if not is_matched:
                mapped_facts=set().union(*mappings.values()) if mappings else set()
                endpoints_present=ref['memory_id'] in mapped_facts and ref['target_memory_id'] in mapped_facts
                unmatched_reasons[(kind,'both_endpoints_mapped' if endpoints_present else 'endpoint_not_mapped')]+=1
                if endpoints_present:
                    left_ids={cid for cid, facts in mappings.items() if ref['memory_id'] in facts}
                    right_ids={cid for cid, facts in mappings.items() if ref['target_memory_id'] in facts}
                    distinct=any(left != right for left in left_ids for right in right_ids)
                    endpoint_separation[(kind,'distinct_candidates' if distinct else 'same_candidate_only')]+=1
                proposals=[ra[ident] for ident in ra if matches(ra[ident]['relationship'])]
                if not endpoints_present:
                    status='endpoint_not_mapped'
                elif proposals:
                    status='matching_proposal_not_jointly_valid'
                else:
                    status='no_matching_proposal'
                unmatched_candidate_status[(kind,status)]+=1
    matched=sum(n for (kind,status),n in grouped.items() if status=='matched')
    total=sum(grouped.values())
    expected=summary['reference_relationship_coverage_conservative']
    if (matched,total)!=(expected['numerator'],expected['denominator']):
        raise ValueError('Breakdown differs from published total')
    return {'format':'ac1-relationship-coverage-breakdown-v1','source_summary_sha256':hashlib.sha256(summary_raw).hexdigest(),
            'review_sha256':[files[str(p)] for p in paths], 'complete_histories':len(complete_ids),
            'types':[{'relationship_type':kind,'matched':grouped[(kind,'matched')],
                      'unmatched':grouped[(kind,'unmatched')]} for kind in sorted({k for k,s in grouped})],
            'unmatched_endpoint_status':[{'relationship_type':kind,'status':status,'count':n}
                                         for (kind,status),n in sorted(unmatched_reasons.items())],
            'unmatched_proposal_status':[{'relationship_type':kind,'status':status,'count':n}
                                         for (kind,status),n in sorted(unmatched_candidate_status.items())],
            'unmatched_endpoint_separation':[{'relationship_type':kind,'status':status,'count':n}
                                              for (kind,status),n in sorted(endpoint_separation.items())],
            'matched':matched,'total':total,
            'limitations':['Unmatched references may reflect partial endpoint mappings or review uncertainty, not necessarily model omissions.',
                           'Reviewed synthetic references are not exhaustive or population-representative.',
                           'Human review and independence are user-reported; AI assistance was used.']}


if __name__=='__main__':
    result=analyze(Path('output/proposal-delivery/ac1-extraction-reviewed-summary-2026-10-28-v2.json'))
    with Path('output/proposal-delivery/ac1-relationship-breakdown-2026-10-29.json').open('x',encoding='utf8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
