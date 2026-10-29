"""Publish count-only snapshots from frozen experiment evidence; no model calls.

Snapshots contain neither candidate text, reference text, answers nor reviewer
identities. A marker without a result is only an unresolved observed attempt;
it is not proof that a process is currently running.
"""
import argparse, hashlib, json, os, subprocess, tempfile, time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AC1_FROZEN=ROOT/'output/proposal-delivery/ac1-extraction-frozen-2026-10-28-v1.json'
AC1_JOURNAL=ROOT/'output/ac3-generated/AC1-1a74cc906df755f6fc2a4855'
PRIMARY=ROOT/'output/proposal-delivery/ac3-expanded-primary-frozen-2026-10-28.json'
REPEAT=ROOT/'output/proposal-delivery/ac3-expanded-repeat-frozen-2026-10-28.json'
PRIMARY_SHA='ec20077e07ead83925fa38bb67936d81773098e0762c1e4627ae3b94d8ff0f58'
REPEAT_SHA='d5f88c4d118ffd0ffb941d564cf1c33cce82dd10ee78f8aaa33f91e508df2246'
AC1_OUTPUT=ROOT/'frontend/public/reports/ac1-extraction-progress-v1.json'
AC3_OUTPUT=ROOT/'frontend/public/reports/ac3-frozen-protocol-status-v1.json'
AC3_LEDGER_OUTPUT=ROOT/'frontend/public/reports/ac3-ledger-progress-v1.json'
ROLES=('memory_extraction','relationship_analysis','independent_memory_review')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):
 if path.is_symlink() or not path.is_file():raise ValueError('Evidence must be a regular file')
 return path.read_bytes()
def ac1_snapshot(frozen,journal):
 raw=read(frozen); protocol=json.loads(raw); frozen_sha=sha(raw)
 if protocol.get('format')!='ac1-extraction-prospective-frozen-v1':raise ValueError('Unexpected AC1 protocol')
 ids=protocol.get('history_ids');
 if not isinstance(ids,list) or len(ids)!=30 or len(set(ids))!=30 or any(not isinstance(i,str) or not i or not all(c.isalnum() or c in '-_' for c in i) for i in ids):raise ValueError('Invalid AC1 history list')
 ledger=json.loads(read(journal/'protocol.json'))
 if ledger.get('format')!='ac1-extraction-ledger-v1' or ledger.get('frozen_sha256')!=frozen_sha:raise ValueError('AC1 journal does not bind frozen protocol')
 outcomes={'completed':0,'partial':0,'failed':0,'runtime_changed':0}; stages={role:{'completed':0,'failed':0,'other':0} for role in ROLES}; started_only=0; receipts=[]
 for hid in ids:
  start=journal/f'{hid}.started.json';result=journal/f'{hid}.result.json'
  if start.exists():
   s=json.loads(read(start))
   if s.get('format')!='ac1-extraction-start-v1' or s.get('history_id')!=hid or s.get('frozen_sha256')!=frozen_sha:raise ValueError('Invalid start marker')
  if result.exists():
   if not start.exists():raise ValueError('Result has no start marker')
   body=read(result); r=json.loads(body)
   if r.get('format')!='ac1-extraction-result-v1' or r.get('history_id')!=hid or r.get('frozen_sha256')!=frozen_sha or r.get('status') not in outcomes:raise ValueError('Invalid result evidence')
   outcomes[r['status']]+=1;receipts.append([hid,sha(body)])
   seen=set()
   for s in r.get('agent_stages',[]):
    role=s.get('role')
    if role not in ROLES:continue
    if role in seen:raise ValueError('Duplicate extraction-stage role')
    seen.add(role);status=s.get('status');stages[role][status if status in ('completed','failed') else 'other']+=1
  elif start.exists():started_only+=1
 observed=sum(outcomes.values())
 return {'format':'ac1-extraction-progress-v1','observed_at_utc':datetime.now(timezone.utc).isoformat(),
  'expected_histories':len(ids),'result_histories':observed,'outcomes':outcomes,'started_without_result':started_only,
  'not_yet_observed':len(ids)-observed-started_only,'stage_outcomes':stages,
  'protocol_sha256':frozen_sha,'runtime_source_sha256':protocol['runtime_source_sha256'],
  'result_receipts_sha256':sha(json.dumps(receipts,separators=(',',':')).encode()),
  'interpretation':'Count-only source snapshot; an observed attempt may not be currently running. Results are not human validation or AC1 acceptance.'}

def ac3_snapshot(primary_path,repeat_path):
 pb,rb=read(primary_path),read(repeat_path);p,r=json.loads(pb),json.loads(rb);ph=sha(pb)
 if (ph!=PRIMARY_SHA or sha(rb)!=REPEAT_SHA or p.get('format')!='ac3-prospective-frozen-suite-v1' or p.get('study_role')!='primary_validation'
     or r.get('format')!='ac3-stability-derived-suite-v1' or r.get('study_role')!='stability_repeat'
     or r.get('parent_frozen_sha256')!=ph or r.get('stability_plan_sha256')!=p.get('stability_plan_sha256')):raise ValueError('Frozen study linkage failed')
 a=p.get('suite',{}).get('cases',[]);b=r.get('suite',{}).get('cases',[])
 if len(a)!=30 or len(b)!=10 or sum(len(x.get('tests',[])) for x in a)!=120 or sum(len(x.get('tests',[])) for x in b)!=40:raise ValueError('Frozen study counts differ')
 aid={c['history_id']:c for c in a};bid={c['history_id']:c for c in b}
 if len(aid)!=30 or len(bid)!=10 or any(aid.get(k)!=v for k,v in bid.items()):raise ValueError('Repeat is not the exact primary subset')
 thresholds=p.get('protocol',{}).get('thresholds'); expected={'failure_detection_recall_min':.8,'failure_classification_accuracy_min':.8,'test_validity_min':.9,'false_positive_rate_max':.1}
 if thresholds!=expected or r.get('protocol',{}).get('thresholds')!=thresholds:raise ValueError('Frozen thresholds differ')
 return {'format':'ac3-frozen-protocol-status-v1','primary_histories':30,'primary_questions':120,
   'repeat_histories':10,'repeat_questions':40,'thresholds':thresholds,'primary_sha256':ph,'repeat_sha256':sha(rb),
   'primary_frozen_at_utc':p['frozen_at_utc'],'repeat_frozen_at_utc':r['frozen_at_utc'],
   'interpretation':'Both protocol snapshots are frozen; this is not a claim that any experiment has finished or met acceptance.'}

def publish(path,document):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.progress-',suffix='.json',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(document,f,ensure_ascii=False,indent=2);f.write('\n')
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def ac3_ledger_snapshot(primary_path, repeat_path):
    """Ask the backend container for only ledger counts in a read-only transaction."""
    ac3_snapshot(primary_path, repeat_path)
    payload={}
    for role,path in (('primary',primary_path),('repeat',repeat_path)):
        doc=json.loads(read(path))
        payload[role]=[test['test_id'] for case in doc['suite']['cases'] for test in case['tests']]
    proc=subprocess.run(['docker','compose','exec','-T','backend','python','/scripts/observe_ac3_public_progress.py','--database-helper'],
        cwd=ROOT,input=json.dumps(payload),text=True,capture_output=True,timeout=30)
    if proc.returncode:raise ValueError('Read-only ledger observation failed')
    result=json.loads(proc.stdout)
    if result.get('format')!='ac3-ledger-progress-v1' or result.get('frozen_sha256')!={'primary':PRIMARY_SHA,'repeat':REPEAT_SHA}:
        raise ValueError('Unbound ledger snapshot')
    for role,total in (('primary',120),('repeat',40)):
        x=result.get(role,{})
        if (x.get('expected')!=total or type(x.get('scope_observed')) is not bool or
            any(type(x.get(k)) is not int or x[k]<0 for k in ('settled','dispatched','unknown','not_dispatched')) or
            sum(x[k] for k in ('settled','dispatched','unknown','not_dispatched'))!=total):
            raise ValueError('Malformed ledger snapshot')
    return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--watch-seconds',type=int,default=0);p.add_argument('--interval',type=float,default=5);p.add_argument('--ledger',action='store_true');a=p.parse_args()
 if a.watch_seconds<0 or not 1<=a.interval<=60:raise ValueError('Invalid polling interval')
 deadline=time.monotonic()+a.watch_seconds
 while True:
  try:
   a1=ac1_snapshot(AC1_FROZEN,AC1_JOURNAL);a3=ac3_snapshot(PRIMARY,REPEAT)
   publish(AC1_OUTPUT,a1);publish(AC3_OUTPUT,a3)
  except (ValueError, OSError, json.JSONDecodeError) as exc:
   # A source can be mid-write; retain the prior valid snapshot and retry.
   print('Progress snapshot not updated:',type(exc).__name__,flush=True)
  if a.ledger:
   try:publish(AC3_LEDGER_OUTPUT,ac3_ledger_snapshot(PRIMARY,REPEAT))
   except (ValueError,OSError,json.JSONDecodeError,subprocess.TimeoutExpired) as exc:print('Ledger snapshot not updated:',type(exc).__name__,flush=True)
  if not a.watch_seconds or time.monotonic()>=deadline:break
  time.sleep(a.interval)
if __name__=='__main__':main()
