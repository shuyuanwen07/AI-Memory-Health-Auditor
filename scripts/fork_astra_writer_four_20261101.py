"""Register both frozen writer conditions for each of four reviewed sources."""
import json
from pathlib import Path
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models import AuditRunModel,ExperimentModel,TestCaseModel
from app.api.routes import audit_schema,audit_run_lock
from app.api.quality_routes import fork_conditions

ROOT=Path('/output/proposal-delivery/astra-writer-four-prospective-20261101-v1')
protocol=json.loads((ROOT/'protocol.json').read_text())
with SessionLocal() as db, audit_run_lock('astra-writer-four-prospective-20261101',db=db):
    result=[]
    for item in protocol['histories']:
        source=db.get(AuditRunModel,item['source_run_id'])
        if not source or source.status!='TESTS_GENERATED' or source.target_configuration!='weak' or source.pipeline_provider!='openai' or source.pipeline_model!='gpt-6-astra':
            raise SystemExit('Source configuration or status does not match protocol')
        tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==source.id)).all()
        if {x.id for x in tests}!=set(item['source_test_ids']):raise SystemExit('Source test identity mismatch')
        previous=[g for g in db.scalars(select(ExperimentModel)).all() if (g.test_suite_metadata or {}).get('study_role')=='astra_writer_four_prospective' and (g.test_suite_metadata or {}).get('diagnostic_source_run_id')==source.id]
        if previous:raise SystemExit(f'Prior fork exists for {source.id}; reconcile it first')
        base=audit_schema(source).target_memory_profile
        profiles=[base.model_copy(update={'label':'Rule writer'}),base.model_copy(update={'label':'Astra writer'})]
        package=fork_conditions(source,db,profiles,role='astra_writer_four_prospective',note='Predeclared paired writer comparison; source question human review confirmed; answer review pending.',
          same_suite=True,targeted_memory_writer='llm_structured',shared_memory_strategy='relationship_packet',
          target_provider='openai',target_model='gpt-6-astra',target_evaluator_provider='openai',target_evaluator_model='gpt-6-astra',preserve_target_configuration=True)
        result.append({'history_id':item['history_id'],'source_run_id':source.id,'experiment_id':package['experiment_id'],'baseline_run_id':package['runs'][0]['run_id'],'candidate_run_id':package['runs'][1]['run_id']})
        print(json.dumps(result[-1]),flush=True)
