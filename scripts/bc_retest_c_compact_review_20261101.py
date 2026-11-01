"""Produce an immutable sources-once C review snapshot, without policy/score labels."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2/C'
SEED=20261101
def digest(s):return hashlib.sha256(s.encode()).hexdigest()[:16]
def read(p):return json.loads(p.read_text())
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--name',required=True)
p.add_argument('--exclude-packed',action='store_true',help='Include only answer IDs absent from earlier snapshot keys.')
a=p.parse_args()
if not a.name.replace('-','').replace('_','').isalnum():raise SystemExit('Use a plain snapshot name.')
directory=OUT/'compact-review';directory.mkdir(exist_ok=True)
source=read(OUT/'selected-source.json')
source_groups=[]
for raw in source:
    messages=[]
    for si,session in enumerate(raw['haystack_sessions']):
        for mi,message in enumerate(session):
            messages.append({'message_id':f'S{si+1}-M{mi+1}','source_session_date':raw['haystack_dates'][si],
                             'role':message.get('role'),'content':message.get('content')})
    source_groups.append({'source_handle':digest('source:'+raw['question_id']),
        'source_messages':messages,'question':raw['question'],'question_date':raw.get('question_date'),
        'benchmark_reference':str(raw['answer']),'question_validity':None,'reference_validity':None,
        'review_reason':None,'supporting_message_ids':[],
        'human_confirmation':{'completed':False,'note':None}})
prior=set()
if a.exclude_packed:
    for path in directory.glob('*.private-key.json'):
        prior.update(r['review_id'] for r in read(path)['mapping'])
items=[];keys=[]
for path in sorted((OUT/'responses').glob('*.json')):
    state=read(path)
    if state['status']!='completed':continue
    job=state['job'];rid=digest(str(SEED)+':blind:'+job['job_id'])
    if rid in prior:continue
    case=state['result']['conditions'][0]['cases'][0]
    items.append({'review_id':rid,'source_handle':digest('source:'+job['case_id']),
        'answer':case['response_text'],'answer_verdict':None,
        'behavior_quality':None,'review_reason':None,'supporting_message_ids':[],
        'human_confirmation':{'completed':False,'note':None}})
    keys.append({'review_id':rid,**job,'response_path':str(path.relative_to(ROOT))})
random.Random(SEED+3).shuffle(items)
payload={'format':'bc-c-compact-blind-review-v2','created_at_utc':datetime.now(timezone.utc).isoformat(),
    'source_note':'Pinned official LongMemEval Oracle evidence-only subset. All source text is shown; source_has_answer flags and condition identity are hidden.',
    'instructions':['Work independently without reading another reviewer or automatic metrics.',
        'First review question/reference validity against the source. Official references may be ambiguous or invalid; preserve such findings.',
        'Then judge answer correctness relative to the actual question and original source, accepting semantic equivalence rather than exact word overlap.',
        'Pass requires sufficient correct information for the question, with no material unsupported definite claim. A source-supported answer may differ in wording from the reference.',
        'A safe clarification or abstention can still be incomplete when the original source contains the requested fact. Record behavior_quality=safe_but_incomplete separately from answer_verdict.',
        'For a genuinely unanswerable question, a justified abstention is correct; do not invent a reference fact.',
        'Use valid/invalid/uncertain for source/question validity, pass/fail/uncertain for answers, and a short source-cited reason. Do not mark any new judgment as human-confirmed.'],
    'reviewer_declaration':{'reviewer':None,'reviewer_kind':'ai','completed_independently':None,
        'has_seen_other_reviewer_or_automatic_scores':False,'completed_by_human':False},
    'source_count':len(source_groups),'answer_count':len(items),'sources':source_groups,'items':items}
dest=directory/(a.name+'.json')
with dest.open('x') as f:json.dump(payload,f,ensure_ascii=False,indent=2);f.write('\n')
key=directory/(a.name+'.private-key.json')
with key.open('x') as f:json.dump({'format':'bc-c-compact-review-key-v2','mapping':keys},f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'review_material':str(dest),'source_count':len(source_groups),'answer_count':len(items),'bytes':dest.stat().st_size}))
