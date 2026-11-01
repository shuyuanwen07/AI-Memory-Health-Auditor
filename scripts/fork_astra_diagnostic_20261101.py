"""One exploratory source-bound retrieval fork, invoked inside the backend.

Uses the application's existing comparison service. No provider is called here.
"""
import json
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models import AuditRunModel, ExperimentModel, TestCaseModel, TargetResponseModel
from app.api.routes import audit_schema, audit_run_lock
from app.api.quality_routes import fork_conditions

SOURCE='RUN49C874718ED54D76AFFAC79518A43B9E'
ROLE='astra_retrieval_followup'
with SessionLocal() as db, audit_run_lock('astra-retrieval-followup-20261101',db=db):
    source=db.get(AuditRunModel,SOURCE)
    if not source or source.status!='COMPLETED' or source.provider!='openai' or source.model!='gpt-6-astra' or source.target_configuration!='weak' or source.memory_strategy!='weak_first_hit':
        raise SystemExit('Source settings or completion do not match the frozen protocol.')
    tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==SOURCE)).all()
    answers=db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id==SOURCE)).all()
    if len(tests)!=4 or len(answers)!=4 or {t.id for t in tests}!={r.test_id for r in answers}:
        raise SystemExit('Source does not have four matched questions and answers.')
    previous=[g for g in db.scalars(select(ExperimentModel)).all() if (g.test_suite_metadata or {}).get('study_role')==ROLE and (g.test_suite_metadata or {}).get('diagnostic_source_run_id')==SOURCE]
    if previous: raise SystemExit('A prior fork exists; inspect it rather than creating a duplicate.')
    profile=audit_schema(source).target_memory_profile
    package=fork_conditions(source,db,[profile],role=ROLE,note='Exploratory single-history same-question retrieval follow-up; human review pending.',
                            same_suite=True,targeted_memory_strategy='relationship_packet',preserve_target_configuration=True)
    print(json.dumps(package))
