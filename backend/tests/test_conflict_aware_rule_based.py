from datetime import datetime, timezone
from sqlalchemy import select
from test_execution_coverage_gate import saved_suite as saved_suite
from app.models import AuditRunModel, MemoryModel, MemoryRelationshipModel
from app.schemas import AuditRun, AuditStatus, Dimension, Memory, MemoryRelationship, MemoryStatus, RelationshipType, TargetConfiguration, TargetProvider
from app.test_generator.conflict_aware import ConflictAwareRuleBasedTestGenerator
from app.test_generator.location_scoped import LocationScopedRuleBasedTestGenerator


def test_frozen_v39_matches_development_study():
    import hashlib
    from pathlib import Path
    from app.test_generator import frozen_location_scoped_v39
    assert frozen_location_scoped_v39.LocationScopedRuleBasedTestGenerator.VERSION == 'rule-based-v39'
    assert hashlib.sha256(Path(frozen_location_scoped_v39.__file__).read_bytes()).hexdigest() == '86cfe7c159b6d240fe2cf2cf1eddd19cb370a19eab3f02017193e5321d6aa2af'


def m(key, value, rel=()):
    return Memory(memory_id=key, conversation_id='C', canonical_value=value,
                  status=MemoryStatus.CONFIRMED, source_message_ids=['S'+key], relationships=list(rel))

def audit(budget=8):
    return AuditRun(run_id='R', conversation_id='C', status=AuditStatus.CREATED,
                    target_configuration=TargetConfiguration.WEAK, provider=TargetProvider.RULE_BASED,
                    model='rules', temperature=0, random_seed=42, test_budget=budget,
                    prompt_template_version='v1', created_at=datetime.now(timezone.utc))

def test_existing_conflict_suppresses_both_resolved_update_probes():
    old=m('M001','My regular work location is the office.')
    current=m('M002','My regular work location is home instead of the office.', [MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id=old.memory_id)])
    conflict=m('M003','My regular work location is exclusively the office, not home.', [MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id=current.memory_id)])
    g=ConflictAwareRuleBasedTestGenerator(); tests=g.generate([old,current,conflict],audit())
    assert any(t.dimension==Dimension.CONFLICT_RESOLUTION and 'conflict' in t.prompt.lower() for t in tests)
    assert not any(t.dimension==Dimension.FRESHNESS for t in tests)
    assert not any('has an explicit update' in t.prompt for t in tests)
    assert g.last_observation['known_conflict_suppressed_count']==2
    assert {c['dimension'] for c in g.last_observation['known_conflict_suppressed_candidates']}=={'freshness','conflict_resolution'}
    assert all(c['supporting_memory_ids']==['M001','M002'] for c in g.last_observation['known_conflict_suppressed_candidates'])
    assert any(t.dimension==Dimension.FRESHNESS for t in LocationScopedRuleBasedTestGenerator().generate([old,current,conflict],audit()))

def test_unrelated_conflict_and_absent_conflict_preserve_update():
    old=m('M001','The backend used MySQL before.')
    current=m('M002','The backend now uses PostgreSQL.',[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id=old.memory_id)])
    first=m('M003','The project venue is the library.')
    second=m('M004','The project venue is the hall.',[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id=first.memory_id)])
    for memories in ([old,current],[old,current,first,second]):
        g=ConflictAwareRuleBasedTestGenerator();tests=g.generate(memories,audit())
        assert any(t.dimension==Dimension.FRESHNESS and set(t.supporting_memory_ids)=={'M001','M002'} for t in tests)
        assert g.last_observation['known_conflict_suppressed_count']==0

def test_api_persists_suppression_without_changing_old_audit(saved_suite):
    client,sessions,runs,_=saved_suite
    with sessions() as db:
        existing=db.get(AuditRunModel,runs[0]); cid=existing.conversation_id
        memories=db.scalars(select(MemoryModel).where(MemoryModel.conversation_id==cid)).all()
        old=next(x for x in memories if 'MySQL' in x.canonical_value)
        current=next(x for x in memories if 'PostgreSQL' in x.canonical_value)
        another=next(x for x in memories if x.id not in {old.id,current.id})
        db.add(MemoryRelationshipModel(id='REL-CONFLICT-TEST',memory_id=another.id,relationship_type='CONFLICT',target_memory_id=current.id,evidence_message_ids=[]));db.commit()
    before=client.get(f'/api/v1/audits/{runs[0]}/tests').json()
    created=client.post('/api/v1/audits',json={'conversation_id':cid,'provider':'rule_based','pipeline_provider':'rule_based','evaluator_provider':'rule_based','target_configuration':'weak','test_budget':4})
    assert created.status_code==201,created.text
    rid=created.json()['run_id']; result=client.post(f'/api/v1/audits/{rid}/generate-tests')
    assert result.status_code==200,result.text
    data=result.json(); assert not any(t['dimension']=='freshness' and set(t['supporting_memory_ids'])=={old.id,current.id} for t in data)
    with sessions() as db:
        run=db.get(AuditRunModel,rid);obs=run.reproducibility_metadata['generation_observations'][-1]
        assert obs['agent_version']=='rule-based-v40' and obs['known_conflict_suppressed_count']==2
    assert client.get(f'/api/v1/audits/{runs[0]}/tests').json()==before

def test_same_pair_has_conflict_and_update_conflict_probe_remains():
    old=m('M001','The backend used MySQL.')
    current=m('M002','The backend now uses PostgreSQL.',[
        MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id=old.memory_id),
        MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id=old.memory_id)])
    g=ConflictAwareRuleBasedTestGenerator();tests=g.generate([old,current],audit())
    assert any('conflict' in t.prompt.lower() and set(t.supporting_memory_ids)=={'M001','M002'} for t in tests)
    assert not any(t.dimension==Dimension.FRESHNESS for t in tests)
    assert g.last_observation['known_conflict_suppressed_count']==2

def test_unconfirmed_third_party_conflict_does_not_change_confirmed_graph():
    old=m('M001','The backend used MySQL.')
    current=m('M002','The backend now uses PostgreSQL.',[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id=old.memory_id)])
    candidate=m('M003','The backend requires SQLite.',[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id=current.memory_id)]).model_copy(update={'status':MemoryStatus.CANDIDATE})
    # Product only passes confirmed memories to the generator; this test exercises
    # the defensive status check directly, not an assertion about graph completeness.
    g=ConflictAwareRuleBasedTestGenerator();g.generate([old,current,candidate],audit())
    assert g.last_observation['known_conflict_suppressed_count']==0

def test_cross_conversation_and_missing_conflicts_do_not_count():
    old=m('M001','The backend used MySQL.')
    current=m('M002','The backend now uses PostgreSQL.',[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id=old.memory_id)])
    external=m('M003','The backend requires SQLite.',[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id=current.memory_id)]).model_copy(update={'conversation_id':'OTHER'})
    missing=m('M004','The frontend uses Angular.',[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id='MISSING')])
    g=ConflictAwareRuleBasedTestGenerator();g.generate([old,current,external,missing],audit())
    assert g.last_observation['known_conflict_suppressed_count']==0

def test_conflict_direction_and_old_endpoint_also_suppresses():
    old=m('M001','The backend used MySQL.')
    current=m('M002','The backend now uses PostgreSQL.',[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id=old.memory_id)])
    third=m('M003','The backend requires SQLite.')
    old.relationships=[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id=third.memory_id)]
    g=ConflictAwareRuleBasedTestGenerator();g.generate([old,current,third],audit())
    assert g.last_observation['known_conflict_suppressed_count']==2
