"""Recovery fork using the app's exact-suite service, preserving failed originals."""
import json,sys
sys.path.insert(0,'/app')
from app.database.session import SessionLocal
from app.models import AuditRunModel
from app.api.routes import audit_schema
from app.api.quality_routes import fork_conditions,completed
with SessionLocal() as db:
 source=completed(sys.argv[1],db)
 result=fork_conditions(source,db,[audit_schema(source).target_memory_profile],role='provider_interruption_recovery',note='503 interruption; identical canonical suite and target controls; original evidence retained',same_suite=True)
 print(json.dumps(result))
