"""Read the frozen C ledger and write a score-free collection progress snapshot."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/proposal-delivery/bc-reader-retest-20261101-v2/C'
p=json.loads((OUT/'protocol.json').read_text())
states={}
for file in (OUT/'responses').glob('*.json'):
    try:
        row=json.loads(file.read_text());states[row['job_id']]=row
    except (ValueError,KeyError):
        continue
rows=[]
for strategy in p['strategies']:
    jobs=[j for j in p['jobs'] if j['strategy']==strategy]
    counts=Counter(states.get(j['job_id'],{}).get('status','not_dispatched') for j in jobs)
    rows.append({'strategy':strategy,'planned':48,'completed':counts['completed'],
        'active':counts['dispatched'],'not_dispatched':counts['not_dispatched'],
        'errors':sum(v for k,v in counts.items() if k not in {'completed','dispatched','not_dispatched'}),
        'primary_pass':None,'primary_accuracy':None,'review_status':'not_yet_reviewed',
        'repetitions':[{'repeat':r,'planned':16,
           'completed':sum(states.get(j['job_id'],{}).get('status')=='completed' for j in jobs if j['repeat']==r)}
          for r in range(1,4)]})
counts=Counter(r['status'] for r in states.values())
terminal=sum(v for k,v in counts.items() if k!='dispatched')
report={'format':'bc-c-progress-v2','updated_at_utc':datetime.now(timezone.utc).isoformat(),
    'collection_status':'completed' if terminal==192 else 'running',
    'provider':'openai','model':'gpt-6-astra','reasoning_effort':'max',
    'planned':192,'completed':counts['completed'],'active':counts['dispatched'],
    'errors':sum(v for k,v in counts.items() if k not in {'completed','dispatched'}),
    'not_dispatched':192-len(states),'distinct_questions':16,'repetitions':3,
    'source_version':p['source']['commit'],'source_variant':'LongMemEval Oracle evidence-only',
    'source_license':'MIT per pinned dataset card','category_quotas':p['category_quotas'],
    'by_strategy':rows,'review_status':'pending_independent_AI_reviews_then_human_confirmation',
    'claim':'Collection progress only. No primary correctness score exists until review. Repeats are not additional distinct questions.'}
tmp=OUT/'progress.json.tmp';tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');tmp.replace(OUT/'progress.json')
print(json.dumps({'completed':report['completed'],'active':report['active'],'errors':report['errors'],'planned':192}))
