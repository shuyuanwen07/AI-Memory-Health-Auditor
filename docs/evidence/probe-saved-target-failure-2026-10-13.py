"""One read-only replay of v13's unfinished target input, no new retrieval/gold."""
import hashlib,json,sqlite3
from pathlib import Path
from fastapi import HTTPException
from app.schemas import AuditRun,TestCase
from app.target_ai.providers import HttpTargetAIConnector
report_path=Path('/tmp/luna-current-isolated-api-v13-2026-10-13.json')
report=json.loads(report_path.read_text())
source=Path('/datasets/smoke/qwen-four-dimension-source-v1.json')
assert hashlib.sha256(source.read_bytes()).hexdigest()==report['source_sha256']
assert json.loads(source.read_text())['authorised'] is True
assert json.loads(source.read_text())['source_origin']=='synthetic'
snapshot=Path('/tmp/luna-current-isolated-api-v13-synthetic-only.db')
assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==report['snapshot_sha256']
db=sqlite3.connect(f'file:{snapshot}?mode=ro',uri=True);db.row_factory=sqlite3.Row
pending=db.execute('select * from target_agent_retrievals where final_response_id is null').fetchall()
assert len(pending)==1
retrieval=pending[0]
run=next(r for r in report['runs'] if r['run_id']==retrieval['run_id'])
audit=AuditRun.model_validate(run['configuration'])
test=TestCase.model_validate(next(t for t in run['tests'] if t['test_id']==retrieval['test_id']))
ids=json.loads(retrieval['selected_memory_ids'])
context=[]
for memory_id in ids:
 row=db.execute('select canonical_value from target_agent_memories where id=? and run_id=?',(memory_id,audit.run_id)).fetchone()
 assert row is not None
 context.append(row[0])
assert db.execute('select count(*) from target_responses where test_id=?',(test.test_id,)).fetchone()[0]==0
target_test=test.model_copy(update={'expected_behavior':'','supporting_memory_ids':[],'target_memory_context':context})
out={'scope':'one_saved_unfinished_target_input_probe','research_evidence':False,'source_report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),'source_sha256':report['source_sha256'],'snapshot_sha256':report['snapshot_sha256'],'test_id':test.test_id,'run_id':audit.run_id,'selected_target_owned_memory_ids':ids,'production_database_writes':0,'snapshot_database_writes':0,'new_retrievals':0,'model':audit.model,'requested_output_token_limit':audit.target_memory_profile.output_token_limit}
try:
 response=HttpTargetAIConnector().execute(target_test,audit)
 out.update(status='completed',response=response.model_dump(mode='json'))
except HTTPException as exc:
 out.update(status='failed',http_status=exc.status_code,error=exc.detail,execution=getattr(exc,'target_execution',None))
assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==report['snapshot_sha256']
Path('/tmp/luna-saved-target-error-probe-2026-10-13.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k in ('status','http_status','error','execution','requested_output_token_limit')}))
