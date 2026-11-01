"""Fork the saved retrieval result, changing only the target memory writer."""
import json
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models import AuditRunModel,ExperimentModel,TestCaseModel,TargetResponseModel
from app.api.routes import audit_schema,audit_run_lock
from app.api.quality_routes import fork_conditions

SOURCE='RUNBF02BDD704734F88B762577C86FDA87F';ROLE='astra_writer_followup'
with SessionLocal() as db, audit_run_lock('astra-writer-followup-20261101',db=db):
    source=db.get(AuditRunModel,SOURCE)
    if not source or source.status!='COMPLETED' or source.provider!='openai' or source.model!='gpt-6-astra' or source.target_configuration!='weak' or source.memory_strategy!='relationship_packet' or source.target_memory_writer!='rule_based':
        raise SystemExit('Source settings do not match protocol')
    tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==SOURCE)).all();responses=db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==SOURCE)).all()
    if len(tests)!=4 or len(responses)!=4 or {x.id for x in tests}!={x.test_id for x in responses}:raise SystemExit('Source questions or responses missing')
    previous=[g for g in db.scalars(select(ExperimentModel)).all() if (g.test_suite_metadata or {}).get('study_role')==ROLE and (g.test_suite_metadata or {}).get('diagnostic_source_run_id')==SOURCE]
    if previous:raise SystemExit('Prior fork exists; inspect rather than duplicate')
    profile=audit_schema(source).target_memory_profile
    package=fork_conditions(source,db,[profile],role=ROLE,note='Exploratory same-question writer follow-up; human review pending.',same_suite=True,
                            targeted_memory_writer='llm_structured',preserve_target_configuration=True)
    print(json.dumps(package))
