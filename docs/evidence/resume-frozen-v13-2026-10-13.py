"""Bounded recovery of approved synthetic v13; immutable original failure."""
import hashlib,json,os,shutil,sqlite3,tempfile,zipfile,sys
from pathlib import Path
from datetime import datetime,timezone
origin=Path('/tmp/luna-current-isolated-api-v13-2026-10-13.json')
original=json.loads(origin.read_text());snapshot=Path('/tmp/luna-current-isolated-api-v13-synthetic-only.db')
assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==original['snapshot_sha256']
source=Path('/datasets/smoke/qwen-four-dimension-source-v1.json');approval=Path('/datasets/smoke/qwen-four-dimension-approval-v1.json')
assert hashlib.sha256(source.read_bytes()).hexdigest()==original['source_sha256']
assert hashlib.sha256(approval.read_bytes()).hexdigest()==original['approval_sha256']
assert original['research_evidence'] is False
readonly=sqlite3.connect(f'file:{snapshot}?mode=ro',uri=True);readonly.row_factory=sqlite3.Row
retained={r['id']:dict(r) for r in readonly.execute('select * from target_responses')};readonly.close()
output=Path('/tmp/luna-v13-frozen-runtime-recovery-2026-10-13.json')
report={'scope':'synthetic_saved_audit_recovery_engineering_only','research_evidence':False,'production_database_writes':0,'origin_report_sha256':hashlib.sha256(origin.read_bytes()).hexdigest(),'origin_snapshot_sha256':original['snapshot_sha256'],'source_sha256':original['source_sha256'],'approval_sha256':original['approval_sha256'],'planned_repetitions_per_strategy':2,'original_saved_response_ids':sorted(retained),'started_at':datetime.now(timezone.utc).isoformat(),'status':'running','requests':[],'runs':[]}
def save():output.write_text(json.dumps(report,indent=2)+'\n')
with tempfile.TemporaryDirectory(prefix='mha-v13-recovery-') as directory:
 working=Path(directory)/'recovery.db';shutil.copyfile(snapshot,working)
 os.environ.update(DATABASE_URL=f'sqlite:///{working}',AUTO_CREATE_SCHEMA='true',AUDITOR_ACCESS_MODE='local',PIPELINE_MAX_OUTPUT_TOKENS='1200',OPENROUTER_PROVIDER='')
 archive=Path('/tmp/luna-v13-frozen-source.zip')
 assert hashlib.sha256(archive.read_bytes()).hexdigest()=='6696e4bf8e187b55bece9fbf39878e8813c5a9006586551af69b9326ab8c038e'
 restored=Path(directory)/'original-source'
 with zipfile.ZipFile(archive) as z:
  for name in z.namelist():
   if name.startswith('backend/app/') and name.endswith('.py'):
    assert '..' not in Path(name).parts
    destination=restored/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(z.read(name))
 sys.path.insert(0,str(restored/'backend'))
 report['recovery_runtime']='original v13 frozen source restored in disposable process only'
 from fastapi.testclient import TestClient
 from app.main import app
 from app.database.session import engine
 from app.services.runtime_freeze import audit_runtime_signature
 report['runtime_signature']=audit_runtime_signature();assert report['runtime_signature']==original['runtime_signature'];save()
 try:
  with TestClient(app) as client:
   def request(method,path):
    print(json.dumps({'event':'dispatch','method':method,'path':path}),flush=True)
    response=client.request(method,'/api/v1'+path)
    body=response.json() if response.content and 'json' in response.headers.get('content-type','') else response.text
    report['requests'].append({'method':method,'path':path,'status_code':response.status_code,'body':body});save()
    print(json.dumps({'event':'response','path':path,'status_code':response.status_code}),flush=True)
    if response.status_code!=200:raise RuntimeError(f'{method} {path}: HTTP{response.status_code}')
    return body
   for old_run in original['runs']:
    run={'run_id':old_run['run_id'],'strategy':old_run['strategy'],'repetition':old_run['repetition']};report['runs'].append(run)
    for _ in range(3):
     plan=request('GET',f"/audits/{run['run_id']}/retry-plan")
     if plan['next_stage'] is None:break
     if not plan['retryable']:raise RuntimeError(f'Existing runtime/input freeze blocks recovery: {plan.get("resume_blocked_reason")}')
     request('POST',f"/audits/{run['run_id']}/retry")
    run['result']=request('GET',f"/audits/{run['run_id']}/results")
    run['agents']=request('GET',f"/audits/{run['run_id']}/agent-executions");save()
   report['bundle']=request('GET',f"/experiments/{original['experiment_id']}/reproducibility-bundle.json")
   report['csv']=request('GET',f"/experiments/{original['experiment_id']}/export.csv")
   report['status']='completed'
 except Exception as exc:
  report.update(status='failed',error_code=type(exc).__name__,error=str(exc))
 finally:
  engine.dispose()
  c=sqlite3.connect(f'file:{working}?mode=ro',uri=True);c.row_factory=sqlite3.Row
  for response_id,old in retained.items():
   row=c.execute('select * from target_responses where id=?',(response_id,)).fetchone();assert row is not None and dict(row)==old
  report['original_saved_responses_unchanged']=True
  report['saved_response_count']=c.execute('select count(*) from target_responses').fetchone()[0]
  report['failed_target_receipts']=[dict(r) for r in c.execute("select role,status,error_summary,error_diagnostics from agent_executions where role='target_answer'")]
  c.close();backup=Path('/tmp/luna-v13-frozen-runtime-recovery-synthetic-only.db');shutil.copyfile(working,backup)
  report.update(snapshot_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),finished_at=datetime.now(timezone.utc).isoformat());save()
report['disposable_database_removed']=not working.exists()
assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==original['snapshot_sha256']
report['original_snapshot_unchanged']=True;save()
print(json.dumps({k:report.get(k) for k in ('status','error','saved_response_count','original_saved_responses_unchanged','disposable_database_removed')}),flush=True)
