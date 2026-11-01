"""Validate both independent AI review returns and report agreement, not human gold."""
import collections
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/astra-ac1-reference-pilot-20261101-v2'
V1=ROOT/'output/proposal-delivery/astra-ac1-reference-pilot-20261101-v1'
blank=json.loads((OUT/'extraction-reviewer-1-blank.json').read_text())
returns=[json.loads((OUT/f'extraction-reviewer-{n}-completed.json').read_text()) for n in (1,2)]
refreturns=[json.loads((V1/f'reference-reviewer-{n}-completed.json').read_text()) for n in (1,2)]
counts=collections.defaultdict(collections.Counter)
def bykey(rows,key):
    result={key(row):row for row in rows}
    if len(result)!=len(rows): raise ValueError('Duplicate review entry')
    return result
for index,original in enumerate(blank['histories']):
    outputs=[]
    for ret in returns:
        h=ret['histories'][index]
        for field in ('history_id','source_messages','reviewed_reference','extracted_candidates','extraction_sha256'):
            if h[field]!=original[field]: raise ValueError(f'Altered input: {field}')
        outputs.append(h['review'])
    for ret in refreturns:
        h=ret['histories'][index]
        for field in ('history_id','source_messages','reviewed_reference'):
            if h[field]!=original[field]: raise ValueError('Source completeness review input mismatch')
        if h['review']['completeness'] not in ('complete','incomplete','uncertain'): raise ValueError('Invalid completeness judgment')
    cids={x['memory_id'] for x in original['extracted_candidates']}
    fids={x['memory_id'] for x in original['reviewed_reference']['facts']}
    es={(x['memory_id'],r['target_memory_id'],r['type']) for x in original['extracted_candidates'] for r in x['relationships']}
    rs={(x['memory_id'],x['target_memory_id'],x['relationship_type']) for x in original['reviewed_reference']['relationships']}
    categories=[('candidates',lambda x:x['memory_id'],cids,{'supported','partial','unsupported','uncertain'}),
        ('reference_facts',lambda x:x['memory_id'],fids,{'full','partial','missing','uncertain'}),
        ('extracted_relationships',lambda x:(x['source_candidate_id'],x['target_candidate_id'],x['type']),es,{'correct','incorrect','uncertain'}),
        ('reference_relationships',lambda x:(x['source_reference_id'],x['target_reference_id'],x['type']),rs,{'full','partial','missing','uncertain'})]
    for name,key,expected,allowed in categories:
        a,b=(bykey(x[name],key) for x in outputs)
        if set(a)!=expected or set(b)!=expected: raise ValueError(f'Missing or extra review item: {name}')
        for item in expected:
            x,y=a[item],b[item]
            if x['verdict'] not in allowed or y['verdict'] not in allowed: raise ValueError('Invalid verdict')
            if name=='reference_facts':
                for r in (x,y):
                    if not set(r['matched_candidate_ids'])<=cids: raise ValueError('Unknown matched candidate')
                    if r['verdict']=='full' and not r['matched_candidate_ids']: raise ValueError('Full coverage without candidate')
            counts[name][x['verdict'] if x['verdict']==y['verdict'] else 'disagreement']+=1
    a,b=(x['histories'][index]['review'] for x in refreturns)
    counts['reference_completeness'][a['completeness'] if a['completeness']==b['completeness'] else 'disagreement']+=1
summary={'review_status':'two_ai_reviews_only_human_confirmation_pending','histories':len(blank['histories']),
 'counts':{k:dict(v) for k,v in counts.items()},
 'scope':'Related, previously studied synthetic histories. Reference coverage allows multiple candidates to cover one compound reference; not strict atomic recall.',
 'limitations':['Source-reference completeness and extraction judgments are AI preliminary reviews pending human confirmation.',
   'Results are selected-sample counts, not general population estimates.',
   'Overlap between candidate records means candidate support is not one-to-one fact precision.'],
 'review_sha256':{f'extraction-reviewer-{n}':hashlib.sha256((OUT/f'extraction-reviewer-{n}-completed.json').read_bytes()).hexdigest() for n in (1,2)}}
(OUT/'ai-review-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False))
