"""Six ordinary development probes. Never claim formal A human approval."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/app')
from app.database.session import SessionLocal
from app.models import AuditRunModel,MemoryModel
from app.schemas import AuditCreate,TestCase
from app.api.routes import build_audit,audit_schema,memory_schema,persist_generated_tests,public_test_schema
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.quality import RuleBasedTestQualityValidator
source=Path('/app/.engineering-smoke/phase4/A-live.json');a=json.loads(source.read_text());D=Path('/app/.engineering-smoke/phase4-followup');D.mkdir(exist_ok=True);path=D/'clarification.json'
if path.exists():raise SystemExit('Development probes already prepared; preserve them and do not duplicate target calls.')
state={'scope':'Six new unambiguous development probes, not a replacement formal Experiment A','status':'preparing','original_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'planned_target_calls':6,'estimated_target_cost_usd':0.01,'budget':'Within existing authorised US$5; hard stop after six one-answer runs','human_approval':'No fabricated human validity record. AI-reviewed engineering probes only.','app_source_sha256':{str(p.relative_to('/app')):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app/app').rglob('*.py')},'runs':[]}
def save():path.write_text(json.dumps(state,indent=2))
with SessionLocal() as db:
 for h in a['scenarios']:
  if h['scenario_id']=='P4-H1':continue
  for original in h['runs']:
   old=next(t for t in original['tests'] if t['dimension']=='accuracy');cfg=original['configuration'];memories=[memory_schema(db,db.get(MemoryModel,mid)) for mid in old['supporting_memory_ids']];assert len(memories)==1
   current=memories[0];assert any(r.type.value=='UPDATE' for r in current.relationships)
   if original['label']=='Contextual/indirect Auditor tests':prompt='Prepare an up-to-date profile for the user. Include the current '+RuleBasedTestGenerator._scoped_topic(current)+' as a concrete fact.'
   else:prompt=RuleBasedTestGenerator._accuracy(current)[1]
   assert 'current' in prompt and 'MySQL' not in prompt and 'PostgreSQL' not in prompt
   fields=['conversation_id','target_configuration','provider','model','temperature','random_seed','memory_strategy','memory_maintenance_policy','target_memory_capacity','target_memory_writer','retrieval_mode','pipeline_provider','pipeline_model','semantic_review_provider','semantic_review_model','evaluator_provider','target_memory_profile']
   body={k:cfg[k] for k in fields};body['test_budget']=1;body['target_memory_profile']={**body['target_memory_profile'],'label':'AI-reviewed development clarification; not formal A'};body['pipeline_model']=RuleBasedTestGenerator.VERSION
   made=build_audit(AuditCreate.model_validate(body),db);row=db.get(AuditRunModel,made.run_id)
   case=TestCase.model_validate({**old,'run_id':made.run_id,'prompt':prompt,'generator_version':'phase4-current-state-development-v1','target_memory_context':[],'human_validity_status':'pending','human_validity_reviewer':None,'human_validity_note':None,'human_validity_reviewed_at':None})
   assessment=RuleBasedTestQualityValidator().validate(case,memories);assert assessment.quality_status.value=='accepted',assessment.reason
   case=case.model_copy(update={'quality_status':assessment.quality_status,'grounding_status':assessment.grounding_status,'validation_notes':'AI-reviewed new temporal-scope development probe; '+assessment.reason})
   saved=persist_generated_tests(db,row,[case]);row.status='TESTS_GENERATED';row.reproducibility_metadata={**row.reproducibility_metadata,'study_role':'development_temporal_scope_clarification','diagnostic_source_run_id':original['run_id'],'human_validation':'pending','generation_observations':[{'saved_suite':True,'requested_test_count':1,'count_target_met':True,'coverage_plan':[{'dimension':'accuracy','test_type':case.test_type.value,'supporting_memory_ids':case.supporting_memory_ids}]}]};db.commit()
   state['runs'].append({'history':h['scenario_id'],'method':original['label'],'source_run_id':original['run_id'],'source_test_id':old['test_id'],'original_prompt':old['prompt'],'run_id':made.run_id,'configuration':audit_schema(row).model_dump(mode='json'),'tests':[public_test_schema(t).model_dump(mode='json') for t in saved]});save()
assert len(state['runs'])==6
state['status']='prepared_AI_reviewed_development_only';save();print('Prepared six source-bound unambiguous probes; formal A unchanged; no target calls yet.')
