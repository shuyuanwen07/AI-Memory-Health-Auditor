"""Register one source-frozen audit per strategy using the application helper."""
import json
from pathlib import Path
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models import AuditRunModel, ExperimentModel, TestCaseModel
from app.api.routes import audit_schema, audit_run_lock
from app.api.quality_routes import fork_conditions

OUT=Path('/output/proposal-delivery/b-astra-four-strategy-20261101-v1')
p=json.loads((OUT/'protocol.json').read_text())
with SessionLocal() as db, audit_run_lock('b-astra-four-strategy-20261101-v1',db=db):
    registrations=[]
    for h in p['histories']:
        source=db.get(AuditRunModel,h['source_run_id'])
        if not source or source.status!='TESTS_GENERATED':raise SystemExit('Source audit not ready')
        tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==source.id)).all()
        if {t.id for t in tests}!=set(h['source_test_ids']):raise SystemExit('Frozen test identities differ')
        exists=[g for g in db.scalars(select(ExperimentModel)).all() if (g.test_suite_metadata or {}).get('study_role')=='b_astra_four_strategy_v1' and (g.test_suite_metadata or {}).get('diagnostic_source_run_id')==source.id]
        if exists:raise SystemExit('Prior group exists; reconcile before any retry')
        base=audit_schema(source).target_memory_profile
        for strategy in p['strategies']:
            group=fork_conditions(source,db,[base.model_copy(update={'label':strategy})],role='b_astra_four_strategy_v1',note='Same human-checked questions; one Astra target run per strategy; answer review pending.',same_suite=True,
                shared_memory_strategy=strategy,target_provider='openai',target_model='gpt-6-astra',preserve_target_configuration=True)
            registrations.append({'history_id':h['history_id'],'source_run_id':source.id,'strategy':strategy,
                                  'experiment_id':group['experiment_id'],'run_id':group['runs'][0]['run_id']})
            print(json.dumps(registrations[-1]),flush=True)
