"""Read-only aggregate of primary/repeat ledger status; never select responses.

The helper runs in the existing backend container and emits only grouped counts
and frozen fingerprints. A dispatched or unknown receipt is not evidence that
its process remains live. These counts do not measure correctness or acceptance.
"""
import argparse,json,sys
from datetime import datetime,timezone

FORMATS={'primary':'ec20077e07ead83925fa38bb67936d81773098e0762c1e4627ae3b94d8ff0f58',
         'repeat':'d5f88c4d118ffd0ffb941d564cf1c33cce82dd10ee78f8aaa33f91e508df2246'}

def summarize(expected,scopes,receipts):
 by_sha={v:k for k,v in FORMATS.items()}; mappings={}; outputs={}
 for s in scopes:
  if s['frozen_sha256'] not in by_sha or s['status'] not in ('active','unknown') or s['scope_id'] in mappings: raise ValueError('Unexpected scope')
  role=by_sha[s['frozen_sha256']]
  if role in mappings.values():raise ValueError('Duplicate study scope')
  mappings[s['scope_id']]=role
 for role in FORMATS:
  ids=expected.get(role)
  if not isinstance(ids,list) or len(ids)!=(120 if role=='primary' else 40) or len(set(ids))!=len(ids):raise ValueError('Bad expected test IDs')
  outputs[role]={'expected':len(ids),'settled':0,'dispatched':0,'unknown':0,'not_dispatched':len(ids),'scope_observed':role in mappings.values()}
 seen=set()
 for r in receipts:
  role=mappings.get(r['scope_id']); key=(r['scope_id'],r['test_id']);status=r['status']
  if role is None or key in seen or r['test_id'] not in expected[role] or status not in ('settled','dispatched','unknown'):raise ValueError('Unexpected ledger receipt')
  seen.add(key);outputs[role][status]+=1;outputs[role]['not_dispatched']-=1
 return {'format':'ac3-ledger-progress-v1','observed_at_utc':datetime.now(timezone.utc).isoformat(),
  'primary':outputs['primary'],'repeat':outputs['repeat'],'frozen_sha256':FORMATS,
  'interpretation':'Read-only count snapshot, not correctness, grading, or AC3 acceptance. An outstanding receipt does not establish a live process.'}


def database_helper():
 from sqlalchemy import text
 from app.database.session import engine
 expected=json.load(sys.stdin)
 with engine.connect() as conn:
  trans=conn.begin()
  try:
   conn.execute(text('SET TRANSACTION READ ONLY'))
   scopes=[dict(r) for r in conn.execute(text('SELECT scope_id, frozen_sha256, status FROM ac3_attempt_scopes WHERE frozen_sha256 IN (:a,:b)'),{'a':FORMATS['primary'],'b':FORMATS['repeat']}).mappings()]
   rows=[]
   for scope in scopes:
    rows.extend(dict(r) for r in conn.execute(text('SELECT scope_id, test_id, status FROM ac3_attempt_receipts WHERE scope_id=:scope'),{'scope':scope['scope_id']}).mappings())
   result=summarize(expected,scopes,rows)
   print(json.dumps(result))
  finally:trans.rollback()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database-helper',action='store_true');a=p.parse_args()
 if not a.database_helper:raise SystemExit('Use the read-only database helper through the host snapshot publisher')
 database_helper()
