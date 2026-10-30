from datetime import datetime, timezone

import pytest

from app.schemas import AuditRun, Dimension, Memory, MemoryStatus, RelationshipType, MemoryRelationship
from app.services.runtime_freeze import audit_runtime_signature
from app.test_generator.factory import get_test_generator
from app.test_generator.location_subject_guard_v1 import location_subject_advice
from app.test_generator.quality import RuleBasedTestQualityValidator
from app.test_generator.topic_scoped_v41 import TopicScopedRuleBasedTestGenerator


def memory(identifier, fact, relationships=None):
    return Memory(memory_id=identifier, conversation_id='C', canonical_value=fact,
                  status=MemoryStatus.CONFIRMED, relationships=relationships or [])


def audit(budget=4):
    return AuditRun(run_id='R', conversation_id='C', status='CREATED', target_configuration='weak',
                    provider='rule_based', model='local', temperature=0, random_seed=42,
                    test_budget=budget, prompt_template_version='test', created_at=datetime.now(timezone.utc))


@pytest.mark.parametrize('fact,subject,answer',[
    ('The research group is based in Canberra.', 'the research group', 'Canberra'),
    ('The museum staff is based in Melbourne.', 'the museum staff', 'Melbourne'),
    ('The theatre company is based in Hobart.', 'the theatre company', 'Hobart'),
])
def test_third_party_location_retains_subject_without_leaking_answer(fact,subject,answer):
    source=memory('M',fact)
    result=TopicScopedRuleBasedTestGenerator().generate([source],audit(1))
    assert len(result)==1
    test=result[0]
    assert subject in test.prompt
    assert answer not in test.prompt
    assert "user's recorded location" not in test.prompt
    assert test.supporting_memory_ids==['M']
    assert location_subject_advice(test,[source]) is None
    assert RuleBasedTestQualityValidator().validate(test,[source]).quality_status.value=='accepted'


@pytest.mark.parametrize('prior,current,topic,answer',[
    ('The study had 24 participants.', 'The study now has 23 participants.', 'participant count', '23'),
    ('The event was scheduled for Monday.', 'The event was rescheduled for Thursday.', 'schedule', 'Thursday'),
    ('The garden watering was on Monday.', 'The garden watering is now Wednesday.', 'watering schedule', 'Wednesday'),
    ('The shop used Courier A for delivery.', 'The shop now uses Courier B for delivery.', 'delivery arrangement', 'Courier B'),
])
def test_updates_ask_about_a_concrete_topic_without_answer_leakage(prior,current,topic,answer):
    old=memory('OLD',prior)
    new=memory('NEW',current,[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='OLD')])
    result=TopicScopedRuleBasedTestGenerator().generate([old,new],audit(4))
    question=next(t for t in result if t.dimension==Dimension.FRESHNESS)
    assert topic in question.prompt
    assert answer not in question.prompt
    assert set(question.supporting_memory_ids)=={'OLD','NEW'}
    assert RuleBasedTestQualityValidator().validate(question,[old,new]).quality_status.value=='accepted'


def test_v41_is_active_and_recorded_in_runtime_signature():
    assert get_test_generator('rule_based').VERSION=='rule-based-v41'
    assert audit_runtime_signature()['generator']=='rule-based-v41'


def test_previous_baseline_versions_remain_importable_for_replay():
    from app.test_generator.frozen_baselines_v10_v9_v8 import DirectGroundTruthTestGenerator, ContextualIndirectTestGenerator, FixedTemplateTestGenerator
    assert DirectGroundTruthTestGenerator.VERSION=='direct-ground-truth-v10'
    assert ContextualIndirectTestGenerator.VERSION=='contextual-indirect-auditor-v8'
    assert FixedTemplateTestGenerator.VERSION=='fixed-template-v9'


def test_user_location_is_not_reassigned_to_another_subject():
    source=memory('M','I live in Sydney.')
    test=TopicScopedRuleBasedTestGenerator().generate([source],audit(1))[0]
    assert "user's recorded location" in test.prompt
    assert location_subject_advice(test,[source]) is None


@pytest.mark.parametrize('first,second,topic',[
    ('The delivery window is 9–11 am.', 'The signed order says the delivery window is 1–3 pm.', 'delivery window'),
    ('The active plan assigns the shared bed to Group A.', 'A signed allocation assigns the same bed to Group B.', 'resource allocation'),
])
def test_conflict_prompt_names_the_actual_topic(first,second,topic):
    old=memory('OLD',first)
    new=memory('NEW',second,[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id='OLD')])
    result=TopicScopedRuleBasedTestGenerator().generate([old,new],audit(4))
    question=next(t for t in result if t.dimension==Dimension.CONFLICT_RESOLUTION)
    assert topic in question.prompt
    assert 'operating system' not in question.prompt
    assert 'stored information' not in question.prompt
    assert set(question.supporting_memory_ids)=={'OLD','NEW'}


def test_formal_topic_scope_distinguishes_analysis_deadlines_and_delivery_providers():
    from app.test_generator.topic_scoped_v42 import TopicScopedV42
    first=memory('A','The active protocol sets the analysis deadline as 5 June.')
    second=memory('B','The active instruction sets the analysis deadline as 8 June.')
    assert TopicScopedV42._scoped_topic(first,second)=='analysis deadline'
    old=memory('OLD','The shop initially used Courier North for local deliveries.')
    new=memory('NEW','The shop switched its local delivery provider to Courier South.')
    assert TopicScopedV42._scoped_topic(old,new)=='delivery provider for the shop'


def test_previous_v11_baselines_remain_importable_for_replay():
    from app.test_generator.frozen_baselines_v11_v9_v9 import DirectGroundTruthTestGenerator, ContextualIndirectTestGenerator
    assert DirectGroundTruthTestGenerator.VERSION=='direct-ground-truth-v11'
    assert ContextualIndirectTestGenerator.VERSION=='contextual-indirect-auditor-v9'
    from app.test_generator.frozen_baselines_v12_v9_v10 import ContextualIndirectTestGenerator as V10
    assert V10.VERSION=='contextual-indirect-auditor-v10'
    from app.test_generator.frozen_baselines_v12_v9_v11 import ContextualIndirectTestGenerator as V11
    assert V11.VERSION=='contextual-indirect-auditor-v11'
    from app.test_generator.frozen_baselines_v12_v9_v12 import ContextualIndirectTestGenerator as V12
    assert V12.VERSION=='contextual-indirect-auditor-v12'


def test_contextual_retains_both_dimensions_when_they_share_a_topic():
    from app.test_generator.baselines import ContextualIndirectTestGenerator
    general=memory('M6','The organiser generally prefers printed handouts.')
    scoped=memory('M7','For the workshop the organiser requires accessible digital handouts; the general preference remains for other events.',[MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE,target_memory_id='M6')])
    old=memory('M2','The workshop was originally scheduled for 12 April.')
    current=memory('M3','The organiser moved the workshop to 19 April, replacing 12 April.',[MemoryRelationship(type=RelationshipType.UPDATE,target_memory_id='M2')])
    hall_a=memory('M4','The active booking says the only final workshop venue is Hall A.')
    hall_b=memory('M5','The active signed notice says the only final workshop venue is Hall B; neither record has priority.',[MemoryRelationship(type=RelationshipType.CONFLICT,target_memory_id='M4')])
    # Scoped memory first reproduces DB ordering where accuracy and appropriate
    # use draw the same topic but are distinct dimensions and evidence families.
    items=[scoped,old,current,hall_a,hall_b,general]
    tests=ContextualIndirectTestGenerator().generate(items,audit(4))
    assert len(tests)==4
    assert {t.dimension for t in tests}==set(Dimension)
    assert len({RuleBasedTestQualityValidator.normalize_prompt(t.prompt) for t in tests})==4
    assert all(RuleBasedTestQualityValidator().validate(t,items).quality_status.value=='accepted' for t in tests)


def test_unknown_scope_does_not_create_a_fabricated_contextual_question():
    from app.test_generator.baselines import DirectGroundTruthTestGenerator, ContextualIndirectTestGenerator
    general=memory('M1','The organiser generally prefers printed handouts.')
    scoped=memory('M2','A special exception requires digital handouts.',[MemoryRelationship(type=RelationshipType.CONTEXTUAL_OVERRIDE,target_memory_id='M1')])
    for generator in (DirectGroundTruthTestGenerator(),ContextualIndirectTestGenerator()):
        assert all(t.dimension!=Dimension.APPROPRIATE_USE for t in generator.generate([general,scoped],audit(4)))


@pytest.mark.parametrize('messages',[
    ['The workshop organiser is based in Perth.','The workshop was originally scheduled for 12 April.','The organiser moved the workshop to 19 April, replacing 12 April.','The active workshop booking says the only final venue is Hall A.','The active signed notice says the only final venue is Hall B; neither document has priority.','The organiser generally prefers printed handouts.','For this workshop the organiser requires accessible digital handouts; the general preference remains elsewhere.'],
    ['The research group is based in Canberra.','The study originally had 24 participants.','After withdrawal the study has 23 participants; the previous count is superseded.','The active protocol sets the analysis deadline as 5 June.','The active supervisor instruction sets the same deadline as 8 June; neither has priority.','The researcher generally prefers in-person meetings.','For this study the supervisor requires online meetings; the general preference remains elsewhere.'],
    ['The garden coordinator is based in Hobart.','The watering rota initially named Monday.','The coordinator changed the watering day to Wednesday, replacing Monday.','The active plan assigns the entire shared bed exclusively to Group Red.','The active allocation assigns the same entire shared bed exclusively to Group Blue; neither has priority.','The coordinator usually prefers morning volunteer sessions.','For compost collection volunteers must attend in the afternoon; the general preference remains elsewhere.'],
    ['The shop owner is based in Darwin.','The shop initially used Parcel North for local deliveries.','The shop switched its local delivery provider to Parcel South; Parcel North is no longer used.','The active supplier schedule sets a delivery window of 9–11 am.','The active signed order specifies 1–3 pm for the same delivery window; neither document has priority.','The owner usually prefers email notifications.','For this delivery the recipient requires a phone notification; the general preference remains elsewhere.'],
])
def test_four_domain_three_method_api_quality_and_gates(saved_suite,messages):
    """Synthetic API fixture only; no target-model calls or human research claims."""
    client,_,_,_=saved_suite
    data=[{'message_id':f'S{i+1}','role':'user','content':text} for i,text in enumerate(messages)]
    res=client.post('/api/v1/conversations',json={'authorised':True,'source_origin':'synthetic','messages':data})
    assert res.status_code==201,res.text
    cid=res.json()['conversation_id'];mids=[]
    for i,message in enumerate(data):
        relationships=[]
        if i in {2,4,6}:
            target,kind={2:(1,'UPDATE'),4:(3,'CONFLICT'),6:(5,'CONTEXTUAL_OVERRIDE')}[i]
            relationships=[{'type':kind,'target_memory_id':mids[target],'evidence_message_ids':[data[target]['message_id'],message['message_id']]}]
        res=client.post('/api/v1/memories',json={'conversation_id':cid,'canonical_value':message['content'],'source_message_ids':[message['message_id']],'relationships':relationships})
        assert res.status_code==201,res.text
        mids.append(res.json()['memory_id'])
    assert client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth',json={'confirmed_memory_ids':mids}).status_code==200
    res=client.post('/api/v1/audits',json={'conversation_id':cid,'target_configuration':'weak','provider':'rule_based','pipeline_provider':'rule_based','test_budget':4,'memory_strategy':'weak_first_hit'})
    assert res.status_code==201,res.text
    rid=res.json()['run_id']
    res=client.post(f'/api/v1/audits/{rid}/generate-tests'); assert res.status_code==200,res.text
    source_tests=res.json(); assert len(source_tests)==4 and all(t['quality_status']=='accepted' for t in source_tests)
    assert client.post(f'/api/v1/audits/{rid}/execute').status_code==200
    assert client.post(f'/api/v1/audits/{rid}/evaluate').status_code==200
    res=client.post(f'/api/v1/audits/{rid}/method-comparison'); assert res.status_code==201,res.text
    plan=res.json(); inventory=plan['inventory_template']
    source_by_memory=dict(zip(mids,(m['message_id'] for m in data)))
    inventory.update({'release_id':'synthetic-test','reviewers':['Fixture one','Fixture two'],'defects':[],
        'fixed_template_release_id':'synthetic-fixed','fixed_template_reviewers':['Fixture one'],
        'fixed_template_review_confirmed':True,'fixed_template_questions':[
            {'template_id':f'FIX-{i}', 'dimension':t['dimension'],'prompt':t['prompt'],'expected_behavior':t['expected_behavior'],
             'supporting_memory_ids':t['supporting_memory_ids'],
             'source_message_ids':[source_by_memory[mid] for mid in t['supporting_memory_ids']],
             'test_type':t['test_type']} for i,t in enumerate(source_tests)]})
    res=client.post(f'/api/v1/audits/{rid}/method-comparison-inventory',json=inventory); assert res.status_code==201,res.text
    for run in plan['runs']:
        run_id=run['run_id']
        res=client.post(f'/api/v1/audits/{run_id}/generate-tests');assert res.status_code==200,res.text
        tests=res.json();assert len(tests)==4 and {t['dimension'] for t in tests}=={d.value for d in Dimension}
        saved=client.get(f'/api/v1/audits/{run_id}/tests');assert saved.status_code==200,saved.text
        assert len(saved.json())==4 and {t['dimension'] for t in saved.json()}=={d.value for d in Dimension}
        assert all(t['quality_status']=='accepted' for t in tests),tests
        if run['label']!='Fixed templates':
            for test in tests:
                prompt=test['prompt'].lower()
                assert "user's" not in prompt and 'the user' not in prompt and 'project task' not in prompt
                assert 'conflict' not in prompt and 'clarification' not in prompt and 'replaced' not in prompt
            conflict=next(t for t in tests if t['dimension']=='conflict_resolution')
            assert 'clarif' in conflict['expected_behavior'].lower()
        if run['label']=='Contextual/indirect Auditor tests':
            assert all(t['prompt'].startswith('Draft ') for t in tests)
            assert all('for a briefing, what' not in t['prompt'].lower() for t in tests)
        assert client.post(f'/api/v1/audits/{run_id}/execute').status_code==409
        for test in tests:
            res=client.patch(f"/api/v1/audits/{run_id}/tests/{test['test_id']}/human-validity-review",json={'decision':'accepted','reviewer_pseudonym':'Synthetic test fixture','note':'Fixture only; not human research review.'})
            assert res.status_code==200,res.text
        res=client.post(f'/api/v1/audits/{run_id}/execute');assert res.status_code==200,res.text
        res=client.post(f'/api/v1/audits/{run_id}/evaluate');assert res.status_code==200,res.text
