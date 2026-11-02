import json,hashlib,datetime
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'output/proposal-delivery/ac3-astra-max-retest-20261101-v2'
OUT=ROOT/'output/ac3-generated/four-evaluator-matched-20261102-v1'
source=json.loads((OLD/'analysis.json').read_text())['items']
assert len(source)==120
results={}
for model in ('rule','qwen','luna','astra'):
 counts=Counter(); failures=[]
 for x in source:
  ref=x['reference']['answer_verdict']; assert ref in ('pass','fail')
  if model in ('rule','astra'):
   saved=x['baseline' if model=='rule' else 'candidate'];verdict=saved.get('verdict');state=saved.get('request_state')
  else:
   f=OUT/model/(str(x['test_id'])+'.json')
   if f.exists():
    r=json.loads(f.read_text());state=r['state'];passed=r.get('judgment',{}).get('passed');verdict='pass' if passed is True else 'fail' if passed is False else 'uncertain'
   else:state='missing';verdict='uncertain'
  counts['reference_'+ref]+=1;counts['total']+=1;counts['state_'+str(state)]+=1
  if verdict not in ('pass','fail'):counts['uncertain_or_error']+=1;counts['unresolved_'+ref]+=1
  else:
   counts['decided']+=1
   if ref=='fail' and verdict=='fail':counts['tp']+=1
   elif ref=='fail' and verdict=='pass':counts['fn']+=1
   elif ref=='pass' and verdict=='fail':counts['fp']+=1
   else:counts['tn']+=1
  if state not in ('returned','offline_replayed'):failures.append({'test_id':x['test_id'],'state':state})
 assert counts['reference_fail']==69 and counts['reference_pass']==51
 results[model]={'counts':dict(counts),'detected_failures':f"{counts['tp']}/69",'recall':counts['tp']/69,'false_alarms':f"{counts['fp']}/51",'coverage':f"{counts['decided']}/120",'unresolved':counts['uncertain_or_error'],'nonterminal_or_failed':failures}
complete=all(len(list((OUT/m).glob('*.json')))==120 and not any(json.loads(f.read_text()).get('state')=='started' for f in (OUT/m).glob('*.json')) for m in ('qwen','luna'))
output={'format':'matched-four-evaluators-v1','computed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'complete':complete,'reference_fail':69,'reference_pass':51,'cases':120,'results':results,'note':'Uncertain/errors count as missed failures for conservative recall; shown separately. Shared 120 answers are Astra-generated from related reused synthetic histories. Models differ in protocol/effort; deterministic baseline has archived input rules. AI-assisted references user-reported human confirmed. No independent held-out generalisation.'}
(OUT/'analysis.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({'complete':complete,'results':{k:{x:v[x] for x in ('detected_failures','false_alarms','coverage','unresolved')} for k,v in results.items()}},ensure_ascii=False))
