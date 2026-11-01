"""Validate blinded AI reviews and separate paired cases from incomplete runs."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/proposal-delivery/b-astra-four-strategy-20261101-v1'
blank=json.loads((OUT/'ai-reviewer-1-blank.json').read_text()); reviews=[json.loads((OUT/f'ai-reviewer-{n}-completed.json').read_text()) for n in (1,2)]
key=json.loads((OUT/'private-review-key.json').read_text())['mapping']; protocol=json.loads((OUT/'protocol.json').read_text())
if len(blank['items'])!=52 or any(len(x['items'])!=52 for x in reviews):raise SystemExit('Expected 52 saved answers')
rows=[]
for orig,a,b in zip(blank['items'],*(r['items'] for r in reviews)):
    for x in (a,b):
        for k in ('review_id','source_messages','question','expected_behavior','target_answer'):
            if x[k]!=orig[k]:raise ValueError('Original review content changed')
        if x['question_validity'] not in ('valid','invalid','uncertain') or x['answer_verdict'] not in ('pass','fail','uncertain') or x['failure_category'] not in ('accuracy','freshness','conflict','conflict_resolution','appropriate_use','none','uncertain'):
            raise ValueError('Invalid or missing review field')
    meta=key[orig['review_id']]
    verdict=a['answer_verdict'] if a['answer_verdict']==b['answer_verdict'] and a['question_validity']==b['question_validity']=='valid' else 'unresolved'
    if verdict=='uncertain':verdict='unresolved'
    rows.append({'review_id':orig['review_id'],**meta,'reviewer_1':a['answer_verdict'],'reviewer_2':b['answer_verdict'],
                 'question_validity_1':a['question_validity'],'question_validity_2':b['question_validity'],'consensus':verdict})
if len({x['review_id'] for x in rows})!=52:raise ValueError('Duplicate review IDs')
strategies=protocol['strategies'];groups=collections.defaultdict(list)
for row in rows:groups[(row['history_id'],row['source_test_id'])].append(row)
paired={k for k,v in groups.items() if len(v)==4 and {x['strategy'] for x in v}==set(strategies)}
if len(paired)!=12:raise ValueError('Unexpected complete paired question count')
def table(selected):
    out={}
    for strategy in strategies:
        subset=[x for x in selected if x['strategy']==strategy];counts=collections.Counter(x['consensus'] for x in subset)
        out[strategy]={'saved':len(subset),'pass':counts['pass'],'fail':counts['fail'],'unresolved':counts['unresolved']}
    return out
summary={'format':'b-astra-four-strategy-ai-review-v1','status':'ai_only_human_confirmation_pending',
 'planned_answers':64,'saved_answers':52,'not_completed':12,'complete_paired_questions':len(paired),
 'all_saved':table(rows),'complete_paired_only':table([x for x in rows if (x['history_id'],x['source_test_id']) in paired]),
 'review_files_sha256':{f'reviewer_{n}':hashlib.sha256((OUT/f'ai-reviewer-{n}-completed.json').read_bytes()).hexdigest() for n in (1,2)},
 'limitations':['AI preliminary decisions are not human reviews.','Four related synthetic histories, with only three complete four-strategy histories.',
                'One repetition per strategy; no repeat-run stability estimate.','One strategy failed with HTTP 502, so 12 planned answers are missing.','Source questions were previously observed.'],
 'items':rows}
(OUT/'ai-review-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='items'},ensure_ascii=False))
