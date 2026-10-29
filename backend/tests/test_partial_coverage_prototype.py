import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.services.generation_coverage import assert_generation_coverage, saved_suite_observation

POLICY = 'evidence_supported_only_v1'

def sample():
    plan = [{'dimension':'accuracy', 'test_type':'direct', 'supporting_memory_ids':['m1']}]
    frozen = {'coverage_policy':POLICY, 'requested_test_count':4, 'planned_test_count':1, 'coverage_plan':plan}
    digest = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    observation = {**frozen, 'coverage_plan_sha256':digest, 'saved_suite':True, 'agent_version':'agent-coverage-semantic-v22', 'count_target_met':False,
      'dimension_coverage':[{'dimension':d,'evidence_supported':True if d=='accuracy' else None,'required_question_count':1 if d=='accuracy' else 0} for d in ('accuracy','freshness','conflict_resolution','appropriate_use')]}
    test = SimpleNamespace(quality_status='accepted', dimension='accuracy', test_type='direct', supporting_memory_ids=['m1'])
    return observation, [test]

def test_partial_and_strict_never_silently_equate():
    obs, tests = sample()
    assert_generation_coverage(obs, tests, 4, coverage_policy=POLICY)
    with pytest.raises(HTTPException):
        assert_generation_coverage(obs, tests, 4)

def test_tamper_budget_policy_slot_or_missing_plan():
    obs, tests = sample()
    for mutate in (lambda o:o.update(planned_test_count=2), lambda o:o.update(coverage_plan=[]), lambda o:o['coverage_plan'][0].update(supporting_memory_ids=['other']), lambda o:o.update(coverage_policy='strict_full_v1')):
        bad=copy.deepcopy(obs); mutate(bad)
        with pytest.raises(HTTPException): assert_generation_coverage(bad, tests, 4, coverage_policy=POLICY)
    with pytest.raises(HTTPException): assert_generation_coverage(obs, tests, 5, coverage_policy=POLICY)

def test_missing_evidence_or_pending_fails():
    obs, tests=sample()
    for bad in ([], [SimpleNamespace(**{**vars(tests[0]), 'supporting_memory_ids':['other']})], [SimpleNamespace(**{**vars(tests[0]), 'quality_status':'pending'})]):
        with pytest.raises(HTTPException): assert_generation_coverage(obs, bad, 4, coverage_policy=POLICY)

def test_retry_failed_observation_never_replaces_saved_contract():
    obs, tests=sample()
    failed=copy.deepcopy(obs); failed['saved_suite']=False; failed['coverage_plan']=[]
    chosen=saved_suite_observation({'generation_observations':[obs,failed]})
    assert chosen == obs
    assert_generation_coverage(chosen, tests, 4, coverage_policy=POLICY)

from test_quality_workflows import client as client, run
from sqlalchemy import select
from app.models import AuditRunModel, TestCaseModel, ExperimentModel, MemoryModel
from app.api.quality_routes import fork_conditions
from app.schemas import TargetMemoryProfile

def test_repair_fork_inherits_policy_and_exact_saved_plan(client):
    audit,_=run(client)
    with client.sessions() as db:
        source=db.get(AuditRunModel,audit['run_id'])
        tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==source.id)).all()
        plan=[{'dimension':t.dimension, 'test_type':t.test_type, 'supporting_memory_ids':t.supporting_memory_ids} for t in tests]
        frozen={'coverage_policy':POLICY,'requested_test_count':source.test_budget,'planned_test_count':len(plan),'coverage_plan':plan}
        digest=hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',', ':'),ensure_ascii=False).encode()).hexdigest()
        observation={**frozen,'coverage_plan_sha256':digest,'saved_suite':True,'agent_version':'agent-coverage-semantic-v22','dimension_coverage':[{'dimension':d,'evidence_supported':True if any(p['dimension']==d for p in plan) else None,'required_question_count':sum(p['dimension']==d for p in plan)} for d in ('accuracy','freshness','conflict_resolution','appropriate_use')]}
        source.reproducibility_metadata={**source.reproducibility_metadata,'coverage_policy':POLICY,'generation_observations':[observation]}
        source.pipeline_provider='ollama'
        source.pipeline_model='fixture-model'
        source.semantic_review_provider='ollama'
        source.semantic_review_model='fixture-model'
        group=db.get(ExperimentModel,source.experiment_id)
        group.test_suite_configuration={**group.test_suite_configuration,'coverage_policy':POLICY,'pipeline_provider':'ollama','pipeline_model':'fixture-model','semantic_review_provider':'ollama','semantic_review_model':'fixture-model'}
        db.commit()
        package=fork_conditions(source,db,[TargetMemoryProfile()],role='repair_comparison',note='fixture')
        clone=db.get(AuditRunModel,package['runs'][0]['run_id'])
        clone_tests=db.scalars(select(TestCaseModel).where(TestCaseModel.run_id==clone.id)).all()
        assert clone.reproducibility_metadata['coverage_policy']==POLICY
        assert saved_suite_observation(clone.reproducibility_metadata)==observation
        assert_generation_coverage(observation,clone_tests,clone.test_budget,coverage_policy=POLICY)
        assert db.get(ExperimentModel,package['experiment_id']).test_suite_configuration['coverage_policy']==POLICY

def test_planner_contract_is_persisted_before_mock_dispatch_and_receipt_is_kept():
    from test_llm_pipeline import _audit, _coverage_memories
    from app.test_generator.agent import AgentTestGenerator
    snapshots=[]
    generator=None
    class Planner:
        provider='mock'; model='fixture'; last_execution=None
        def complete_json(self, **request):
            assert snapshots and snapshots[-1]['coverage_planner']['status']=='started'
            frozen=snapshots[-1]['planning_contract']
            assert frozen['max_planner_calls']==1
            assert frozen['schema']==request['schema']
            payload=json.loads(request['prompt'].split('\n\n',1)[1])
            assert frozen['input_payload']==payload
            selected={d:ids[:payload['required_available_quota_by_dimension'][d]] for d,ids in payload['candidate_ids_by_dimension'].items()}
            self.last_execution={'request_attempts':1,'usage':{'total_tokens':42},'cost':'fixture-only'}
            return {'selected_candidate_ids_by_dimension':selected,'coverage_notes':[]}
    planner=Planner()
    generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=planner)
    generator._agent_observation={'semantic_reviews':[]}
    generator.progress_observer=lambda: snapshots.append(copy.deepcopy(generator._agent_observation))
    audit=_audit();audit.reproducibility.coverage_policy=POLICY
    inventory=generator._coverage_seed_inventory(_coverage_memories(),4,coverage_policy=POLICY)
    plan=generator._build_coverage_plan(_coverage_memories(),audit,inventory=inventory)
    assert plan
    assert generator._agent_observation['coverage_planner']['execution']==planner.last_execution
    assert generator._agent_observation['coverage_planner']['status']=='completed'

def test_preview_partial_keeps_unmeasured_distinct_from_zero_score(client):
    from test_quality_workflows import history
    identity=history(client, '[User] I prefer Python.')
    partial=client.get(f'/api/v1/conversations/{identity}/test-coverage-preview?test_budget=4&coverage_policy={POLICY}')
    assert partial.status_code==200,partial.text
    body=partial.json()
    assert body['coverage_policy']==POLICY
    assert body['minimum_met'] is True
    assert 0<body['planned_test_count']<=4
    unplanned=[item for item in body['dimensions'] if item['required_question_count']==0]
    assert unplanned
    assert all(item['evidence_supported'] is None for item in unplanned)
    strict=client.get(f'/api/v1/conversations/{identity}/test-coverage-preview?test_budget=4')
    assert strict.status_code==200
    assert strict.json()['coverage_policy']=='strict_full_v1'
    assert strict.json()['minimum_met'] is False

def test_api_rejects_partial_rule_and_nonbehavioural_and_formal_research(client):
    from test_quality_workflows import history
    identity=history(client,'[User] I prefer Python.')
    base={'conversation_id':identity,'label':'Fixture','test_suite_configuration':{'coverage_policy':POLICY,'test_budget':4}}
    rejected=client.post('/api/v1/experiments',json=base)
    assert rejected.status_code==422,rejected.text
    nonbehavioural=copy.deepcopy(base)
    nonbehavioural['test_suite_configuration'].update(pipeline_provider='ollama',pipeline_model='fixture',suite_mode='paired_contextual')
    rejected=client.post('/api/v1/experiments',json=nonbehavioural)
    assert rejected.status_code==422,rejected.text
    formal=copy.deepcopy(base)
    formal['test_suite_configuration'].update(pipeline_provider='ollama',pipeline_model='fixture',compare_evaluators=True)
    rejected=client.post('/api/v1/experiments',json=formal)
    assert rejected.status_code==422,rejected.text
    rule_audit=client.post('/api/v1/audits',json={'conversation_id':identity,'target_configuration':'weak','provider':'rule_based','coverage_policy':POLICY,'pipeline_provider':'rule_based'})
    assert rule_audit.status_code==422,rule_audit.text

def test_research_promotion_rejects_partial_even_for_completed_source(client):
    audit,_=run(client)
    with client.sessions() as db:
        source=db.get(AuditRunModel,audit['run_id'])
        source.reproducibility_metadata={**source.reproducibility_metadata,'coverage_policy':POLICY}
        db.commit()
    response=client.post(f"/api/v1/audits/{audit['run_id']}/method-comparison")
    assert response.status_code==409,response.text

def test_partial_fork_unknown_research_roles_fail_closed(client):
    audit,_=run(client)
    with client.sessions() as db:
        source=db.get(AuditRunModel,audit['run_id'])
        source.reproducibility_metadata={**source.reproducibility_metadata,'coverage_policy':POLICY}
        for role in ['adaptive_follow_up','audit_method_comparison','new_unknown_research_role']:
            with pytest.raises(HTTPException) as exc:
                fork_conditions(source,db,[TargetMemoryProfile()],role=role,note='fixture')
            assert exc.value.status_code==409

def test_mock_model_partial_audit_generates_and_executes(client, monkeypatch):
    from test_quality_workflows import history
    from app.test_generator.agent import AgentTestGenerator
    import app.api.routes as routes
    class Planner:
        provider='ollama';model='fixture';last_execution=None
        def complete_json(self,**request):
            payload=json.loads(request['prompt'].split('\n\n',1)[1])
            self.last_execution={'status':'parsed','request_attempts':1,'reported_cost_credits':None,'scope':'fixture only'}
            return {'selected_candidate_ids_by_dimension':{d:ids[:payload['required_available_quota_by_dimension'][d]] for d,ids in payload['candidate_ids_by_dimension'].items()},'coverage_notes':[]}
    generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=Planner())
    def generate_slots(memories,audit):
        seeds,_,_=generator._coverage_seed_inventory(memories,audit.test_budget,coverage_policy=POLICY)
        output=[]
        for slot in generator._active_coverage_plan:
            seed=next(seed for seed in seeds if seed.dimension.value==slot['dimension'] and seed.test_type.value==slot['test_type'] and seed.supporting_memory_ids==slot['supporting_memory_ids'])
            output.append(seed.model_copy(update={'run_id':audit.run_id,'test_id':f'MOCK-{len(output)}'}))
        return output
    generator._generate_planned_slots=generate_slots
    monkeypatch.setattr(routes,'get_test_generator',lambda *args,**kwargs:generator)
    identity=history(client,'[User] I prefer Python.')
    group=client.post('/api/v1/experiments',json={'conversation_id':identity,'label':'mock fixture','test_suite_configuration':{'test_budget':1,'pipeline_provider':'ollama','pipeline_model':'fixture','coverage_policy':POLICY}})
    assert group.status_code==201,group.text
    audit=client.post('/api/v1/audits',json={'conversation_id':identity,'experiment_id':group.json()['experiment_id'],'target_configuration':'weak','provider':'rule_based'})
    assert audit.status_code==201,audit.text
    rid=audit.json()['run_id']
    peer=client.post('/api/v1/audits',json={'conversation_id':identity,'experiment_id':group.json()['experiment_id'],'target_configuration':'weak','provider':'rule_based'})
    assert peer.status_code==201,peer.text
    peer_id=peer.json()['run_id']
    generation=client.post(f'/api/v1/audits/{rid}/generate-tests')
    assert generation.status_code==200,generation.text
    assert all(t['quality_status']=='pending' and t['validation_notes'].startswith('partial-source-review-v1:') for t in generation.json())
    review=client.get(f'/api/v1/audits/{rid}/test-review')
    assert review.status_code==200,review.text
    assert review.json()['coverage_policy']==POLICY
    assert review.json()['planned_test_count']==1
    reviewed=review.json()['dimension_coverage']
    assert sum(item['evidence_supported'] is None for item in reviewed)==3
    assert all('unknown' in item['reason'] for item in reviewed if item['evidence_supported'] is None)
    shared=client.post(f'/api/v1/audits/{peer_id}/generate-tests')
    assert shared.status_code==200,shared.text
    peer_review=client.get(f'/api/v1/audits/{peer_id}/test-review')
    assert peer_review.status_code==200,peer_review.text
    assert peer_review.json()['coverage_policy']==POLICY
    assert peer_review.json()['planned_test_count']==1
    assert peer_review.json()['canonical_run_id']==rid
    assert [t['supporting_memory_ids'] for t in shared.json()]==[t['supporting_memory_ids'] for t in generation.json()]
    blocked=client.post(f'/api/v1/audits/{peer_id}/execute')
    assert blocked.status_code==409,blocked.text
    supporting_id=generation.json()[0]['supporting_memory_ids'][0]
    with client.sessions() as db:
        memory=db.get(MemoryModel,supporting_id)
        original_sources=list(memory.source_message_ids)
        memory.source_message_ids=['missing-source']
        db.commit()
    unavailable=client.patch(f"/api/v1/audits/{rid}/tests/{generation.json()[0]['test_id']}/review",json={'quality_status':'accepted'})
    assert unavailable.status_code==422,unavailable.text
    with client.sessions() as db:
        db.get(MemoryModel,supporting_id).source_message_ids=original_sources
        db.commit()
    accepted=client.patch(f"/api/v1/audits/{rid}/tests/{generation.json()[0]['test_id']}/review",json={'quality_status':'accepted','note':'Checked complete source'})
    assert accepted.status_code==200,accepted.text
    peer_execute=client.post(f'/api/v1/audits/{peer_id}/execute')
    assert peer_execute.status_code==200,peer_execute.text
    execution=client.post(f'/api/v1/audits/{rid}/execute')
    assert execution.status_code==200,execution.text
    evaluation=client.post(f'/api/v1/audits/{rid}/evaluate')
    assert evaluation.status_code==200,evaluation.text
    result=client.get(f'/api/v1/audits/{rid}/results')
    assert result.status_code==200,result.text
    assert result.json()['formal_overall_score'] is None
    assert sum(item['percentage'] is None for item in result.json()['dimensions']) >= 3
    with client.sessions() as db:
        row=db.get(AuditRunModel,rid)
        obs=saved_suite_observation(row.reproducibility_metadata)
        assert obs['planned_test_count']==1
        assert obs['planning_contract']['model']=='fixture'
        assert obs['coverage_planner']['execution']['request_attempts']==1
        original_metadata=copy.deepcopy(row.reproducibility_metadata)
        peer_row=db.get(AuditRunModel,peer_id)
        peer_metadata=copy.deepcopy(peer_row.reproducibility_metadata)
        assert not saved_suite_observation(peer_metadata)
        fork=fork_conditions(peer_row,db,[TargetMemoryProfile()],role='repair_comparison',note='peer source')
        forked=db.get(AuditRunModel,fork['runs'][0]['run_id'])
        assert saved_suite_observation(forked.reproducibility_metadata)==obs
        db.refresh(row);db.refresh(peer_row)
        assert row.reproducibility_metadata==original_metadata
        assert peer_row.reproducibility_metadata==peer_metadata

def test_failed_planner_saves_failure_receipt_without_partial_suite():
    from test_llm_pipeline import _audit, _coverage_memories
    from app.test_generator.agent import AgentTestGenerator
    snapshots=[]
    class FailedPlanner:
        provider='mock';model='fixture';last_execution=None
        def complete_json(self,**request):
            self.last_execution={'status':'failed','request_attempts':1,'reported_cost_credits':None,'scope':'failed request usage unknown'}
            raise RuntimeError('simulated transport failure')
    generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=FailedPlanner())
    generator.progress_observer=lambda:snapshots.append(copy.deepcopy(generator.last_observation))
    audit=_audit();audit.reproducibility.coverage_policy=POLICY
    with pytest.raises(RuntimeError): generator.generate(_coverage_memories(),audit)
    assert snapshots[-1]['status']=='failed'
    assert snapshots[-1]['coverage_planner']['execution']['request_attempts']==1
    assert snapshots[-1]['coverage_planner']['execution']['reported_cost_credits'] is None
    assert snapshots[-1].get('coverage_plan') in (None,[])
    assert snapshots[-1]['planning_contract_sha256']

def test_legacy_strict_read_and_fork_do_not_rewrite_original_metadata(client,monkeypatch):
    import app.api.routes as routes
    inputs=[]
    original=routes.fingerprint
    def capture(value):
        inputs.append(copy.deepcopy(value));return original(value)
    monkeypatch.setattr(routes,'fingerprint',capture)
    audit,_=run(client)
    assert any('test_budget' in value and 'pipeline_provider' in value and 'coverage_policy' not in value for value in inputs if isinstance(value,dict))
    with client.sessions() as db:
        source=db.get(AuditRunModel,audit['run_id'])
        metadata=copy.deepcopy(source.reproducibility_metadata)
        metadata.pop('coverage_policy',None)
        source.reproducibility_metadata=metadata
        group=db.get(ExperimentModel,source.experiment_id)
        legacy_config=copy.deepcopy(group.test_suite_configuration)
        legacy_config.pop('coverage_policy',None)
        group.test_suite_configuration=legacy_config
        db.commit()
        before=copy.deepcopy(metadata);config_before=copy.deepcopy(legacy_config)
    result=client.get(f"/api/v1/audits/{audit['run_id']}/results")
    assert result.status_code==200,result.text
    assert result.json()['reproducibility']['coverage_policy']=='strict_full_v1'
    with client.sessions() as db:
        source=db.get(AuditRunModel,audit['run_id'])
        fork_conditions(source,db,[TargetMemoryProfile()],role='repair_comparison',note='legacy')
        db.refresh(source);group=db.get(ExperimentModel,source.experiment_id);db.refresh(group)
        assert source.reproducibility_metadata==before
        assert group.test_suite_configuration==config_before

def test_partial_plan_rejects_quota_mismatch_and_duplicate_even_with_recomputed_digest():
    obs,tests=sample()
    quota=copy.deepcopy(obs)
    quota['dimension_coverage'][0]['required_question_count']=0
    with pytest.raises(HTTPException): assert_generation_coverage(quota,tests,4,coverage_policy=POLICY)
    duplicate=copy.deepcopy(obs)
    duplicate['coverage_plan'].append(copy.deepcopy(duplicate['coverage_plan'][0]))
    duplicate['planned_test_count']=2
    duplicate['dimension_coverage'][0]['required_question_count']=2
    frozen={k:duplicate[k] for k in ['coverage_policy','requested_test_count','planned_test_count','coverage_plan']}
    duplicate['coverage_plan_sha256']=hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',', ':'),ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(HTTPException): assert_generation_coverage(duplicate,tests*2,4,coverage_policy=POLICY)

def test_strict_creation_idempotency_matches_legacy_fingerprint_without_rewriting(client):
    from test_quality_workflows import history
    identity=history(client,'[User] I prefer Python.')
    body={'creation_request_key':'legacy-experiment-key-001','conversation_id':identity,'label':'Legacy request','test_suite_configuration':{'test_budget':4}}
    created=client.post('/api/v1/experiments',json=body)
    assert created.status_code==201,created.text
    experiment_id=created.json()['experiment_id']
    with client.sessions() as db:
        row=db.get(ExperimentModel,experiment_id)
        legacy=copy.deepcopy(row.test_suite_configuration)
        legacy.pop('coverage_policy',None)
        row.test_suite_configuration=legacy
        db.commit();stored=copy.deepcopy(row.creation_request_fingerprint)
    resumed=client.post('/api/v1/experiments',json=body)
    assert resumed.status_code==201 and resumed.json()['experiment_id']==experiment_id,resumed.text
    with client.sessions() as db:
        row=db.get(ExperimentModel,experiment_id)
        assert row.creation_request_fingerprint==stored
        assert row.test_suite_configuration==legacy
    changed=copy.deepcopy(body);changed['test_suite_configuration']['coverage_policy']=POLICY
    assert client.post('/api/v1/experiments',json=changed).status_code==409

def test_partial_rejected_at_formal_release_inventory_mapping_and_restore_without_mutation(client):
    from app.api.quality_routes import freeze_method_comparison_inventory, freeze_method_comparison_discovery_mapping
    from app.services.formal_matrix import FormalSyntheticMatrixService
    audit,_=run(client)
    with client.sessions() as db:
        source=db.get(AuditRunModel,audit['run_id'])
        source.reproducibility_metadata={**source.reproducibility_metadata,'coverage_policy':POLICY}
        db.commit()
        before=copy.deepcopy(source.reproducibility_metadata)
        for call in (lambda:freeze_method_comparison_inventory(source.id,None,db),
                     lambda:freeze_method_comparison_discovery_mapping(source.id,None,db),
                     lambda:FormalSyntheticMatrixService().restore(db,source.id)):
            with pytest.raises(HTTPException) as exc: call()
            assert exc.value.status_code==409
        db.refresh(source)
        assert source.reproducibility_metadata==before

def test_partial_inflight_cancel_cannot_save_plan_or_revive_condition(client,monkeypatch):
    from test_quality_workflows import history
    from app.test_generator.agent import AgentTestGenerator
    import app.api.routes as routes
    identity=history(client,'[User] I prefer Python.')
    group=client.post('/api/v1/experiments',json={'conversation_id':identity,'label':'cancel fixture','test_suite_configuration':{'test_budget':1,'pipeline_provider':'ollama','pipeline_model':'fixture','coverage_policy':POLICY}}).json()['experiment_id']
    audit=client.post('/api/v1/audits',json={'conversation_id':identity,'experiment_id':group,'target_configuration':'weak','provider':'rule_based'}).json()['run_id']
    class CancelPlanner:
        provider='ollama';model='fixture';last_execution={'status':'parsed','request_attempts':1,'reported_cost_credits':None}
        def complete_json(self,**request):
            assert client.post(f'/api/v1/experiments/{group}/cancel').status_code==200
            data=json.loads(request['prompt'].split('\n\n',1)[1])
            return {'selected_candidate_ids_by_dimension':{d:ids[:data['required_available_quota_by_dimension'][d]] for d,ids in data['candidate_ids_by_dimension'].items()},'coverage_notes':[]}
    generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=CancelPlanner())
    generator._generate_planned_slots=lambda *_:pytest.fail('a cancelled audit must not reach question writing')
    monkeypatch.setattr(routes,'get_test_generator',lambda *args,**kwargs:generator)
    result=client.post(f'/api/v1/audits/{audit}/generate-tests')
    assert result.status_code==409,result.text
    assert client.get(f'/api/v1/audits/{audit}').json()['status']=='CANCELLED'
    assert client.get(f'/api/v1/audits/{audit}/tests').json()==[]

def test_retry_after_frozen_unsaved_plan_fails_closed_without_replanning(client,monkeypatch):
    from test_quality_workflows import history
    from app.test_generator.agent import AgentTestGenerator
    import app.api.routes as routes
    identity=history(client,'[User] I prefer Python.')
    group=client.post('/api/v1/experiments',json={'conversation_id':identity,'label':'failure fixture','test_suite_configuration':{'test_budget':1,'pipeline_provider':'ollama','pipeline_model':'fixture','coverage_policy':POLICY}}).json()['experiment_id']
    audit=client.post('/api/v1/audits',json={'conversation_id':identity,'experiment_id':group,'target_configuration':'weak','provider':'rule_based'}).json()['run_id']
    class Planner:
        provider='ollama';model='fixture';last_execution={'status':'parsed','request_attempts':1,'reported_cost_credits':None}
        calls=0
        def complete_json(self,**request):
            self.calls+=1
            data=json.loads(request['prompt'].split('\n\n',1)[1])
            return {'selected_candidate_ids_by_dimension':{d:ids[:data['required_available_quota_by_dimension'][d]] for d,ids in data['candidate_ids_by_dimension'].items()},'coverage_notes':[]}
    planner=Planner();generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=planner)
    from app.extraction.llm import PipelineRequestError
    def fail_after_plan(*_): raise PipelineRequestError('simulated writer failure')
    generator._generate_planned_slots=fail_after_plan
    monkeypatch.setattr(routes,'get_test_generator',lambda *args,**kwargs:generator)
    first=client.post(f'/api/v1/audits/{audit}/generate-tests')
    assert first.status_code==502,first.text
    with client.sessions() as db:
        row=db.get(AuditRunModel,audit);before=copy.deepcopy(row.reproducibility_metadata)
        assert before['generation_observations'][-1]['coverage_plan']
    retry=client.post(f'/api/v1/audits/{audit}/generate-tests')
    assert retry.status_code==409,retry.text
    assert planner.calls==1
    with client.sessions() as db: assert db.get(AuditRunModel,audit).reproducibility_metadata==before
    assert client.get(f'/api/v1/audits/{audit}/tests').json()==[]

def test_partial_cannot_masquerade_as_frozen_formal_runtime():
    from app.services.formal_freeze import assert_formal_runtime_frozen
    audit=SimpleNamespace(reproducibility_metadata={'formal_matrix_version':'fixture','coverage_policy':POLICY})
    with pytest.raises(HTTPException) as exc: assert_formal_runtime_frozen(audit)
    assert exc.value.status_code==409

def test_uncertain_planner_dispatch_is_not_repeated_and_original_receipt_is_preserved(client,monkeypatch):
    from test_quality_workflows import history
    from app.test_generator.agent import AgentTestGenerator
    from app.extraction.llm import PipelineRequestError
    import app.api.routes as routes
    identity=history(client,'[User] I prefer Python.')
    group=client.post('/api/v1/experiments',json={'conversation_id':identity,'label':'uncertain dispatch fixture','test_suite_configuration':{'test_budget':1,'pipeline_provider':'ollama','pipeline_model':'fixture','coverage_policy':POLICY}}).json()['experiment_id']
    audit=client.post('/api/v1/audits',json={'conversation_id':identity,'experiment_id':group,'target_configuration':'weak','provider':'rule_based'}).json()['run_id']
    class LostPlanner:
        provider='ollama';model='fixture';last_execution=None;calls=0
        def complete_json(self,**request):
            self.calls+=1
            self.last_execution={'status':'failed','request_attempts':1,'reported_cost_credits':None,'scope':'failed request cost unknown'}
            raise PipelineRequestError('simulated timeout')
    planner=LostPlanner();generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=planner)
    monkeypatch.setattr(routes,'get_test_generator',lambda *args,**kwargs:generator)
    first=client.post(f'/api/v1/audits/{audit}/generate-tests')
    assert first.status_code==502,first.text
    with client.sessions() as db:
        row=db.get(AuditRunModel,audit);before=copy.deepcopy(row.reproducibility_metadata)
        observation=before['generation_observations'][-1]
        assert observation['planning_contract'] and not observation.get('coverage_plan')
        assert observation['coverage_planner']['execution']['reported_cost_credits'] is None
    second=client.post(f'/api/v1/audits/{audit}/generate-tests')
    assert second.status_code==409,second.text
    assert planner.calls==1
    with client.sessions() as db:
        row=db.get(AuditRunModel,audit)
        assert row.reproducibility_metadata==before
        row.status='FAILED';db.commit()
    retry_plan=client.get(f'/api/v1/audits/{audit}/retry-plan')
    assert retry_plan.status_code==200,retry_plan.text
    assert retry_plan.json()['retryable'] is False
    assert 'redispatch is blocked' in retry_plan.json()['resume_blocked_reason']
    retried=client.post(f'/api/v1/audits/{audit}/retry')
    assert retried.status_code==409,retried.text
    with client.sessions() as db:
        row=db.get(AuditRunModel,audit)
        assert row.status=='FAILED'
        assert row.reproducibility_metadata==before
    assert planner.calls==1
    assert client.get(f'/api/v1/audits/{audit}/tests').json()==[]

def test_partial_real_api_plan_suppresses_conflicted_update_and_keeps_clarification(client,monkeypatch):
    from app.test_generator.agent import AgentTestGenerator
    from app.extraction.llm import PipelineRequestError
    import app.api.routes as routes
    texts=['My regular work location is the office.','My regular work location is home instead of the office.','My regular work location is exclusively the office, not home.']
    messages=[{'message_id':f'S{i+1}','role':'user','content':text} for i,text in enumerate(texts)]
    cid=client.post('/api/v1/conversations',json={'authorised':True,'messages':messages}).json()['conversation_id']
    ids=[]
    for i,text in enumerate(texts):
        relationships=[] if i==0 else [{'type':'UPDATE' if i==1 else 'CONFLICT','target_memory_id':ids[0 if i==1 else 1]}]
        response=client.post('/api/v1/memories',json={'conversation_id':cid,'canonical_value':text,'source_message_ids':[f'S{i+1}'],'relationships':relationships})
        assert response.status_code==201,response.text
        ids.append(response.json()['memory_id'])
    confirmed=client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':ids})
    assert confirmed.status_code==200,confirmed.text
    preview=client.get(f'/api/v1/conversations/{cid}/test-coverage-preview?test_budget=8&coverage_policy={POLICY}')
    assert preview.status_code==200,preview.text
    dimensions={x['dimension']:x for x in preview.json()['dimensions']}
    assert dimensions['freshness']['required_question_count']==0
    assert dimensions['conflict_resolution']['required_question_count']>0
    group=client.post('/api/v1/experiments',json={'conversation_id':cid,'label':'conflict fixture','test_suite_configuration':{'test_budget':8,'pipeline_provider':'ollama','pipeline_model':'fixture','coverage_policy':POLICY}}).json()['experiment_id']
    audit=client.post('/api/v1/audits',json={'conversation_id':cid,'experiment_id':group,'target_configuration':'weak','provider':'rule_based'}).json()['run_id']
    class Planner:
        provider='ollama';model='fixture';last_execution={'status':'parsed','request_attempts':1,'reported_cost_credits':None}
        def complete_json(self,**request):
            data=json.loads(request['prompt'].split('\n\n',1)[1])
            assert not any(s['dimension']=='freshness' for s in data['candidate_slots'])
            assert any(s['dimension']=='conflict_resolution' and set(s['supporting_memory_ids'])==set(ids[1:]) for s in data['candidate_slots'])
            return {'selected_candidate_ids_by_dimension':{d:v[:data['required_available_quota_by_dimension'][d]] for d,v in data['candidate_ids_by_dimension'].items()},'coverage_notes':[]}
    generator=AgentTestGenerator(client=object(),reviewer_client=object(),planner_client=Planner())
    def stop_after_plan(*_): raise PipelineRequestError('fixture stops before writing')
    generator._generate_planned_slots=stop_after_plan
    monkeypatch.setattr(routes,'get_test_generator',lambda *a,**k:generator)
    response=client.post(f'/api/v1/audits/{audit}/generate-tests')
    assert response.status_code==502,response.text
    with client.sessions() as db:
        plan=db.get(AuditRunModel,audit).reproducibility_metadata['generation_observations'][-1]['coverage_plan']
        assert not any(slot['dimension']=='freshness' and set(slot['supporting_memory_ids'])==set(ids[:2]) for slot in plan)
        assert any(slot['dimension']=='conflict_resolution' and set(slot['supporting_memory_ids'])==set(ids[1:]) for slot in plan)
