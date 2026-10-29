"""New location questions must not silently attribute others' locations to a user."""
from datetime import datetime, timezone

import pytest

from app.schemas import AuditRun, Dimension, GroundingStatus, Memory, MemoryStatus, TestCase, TestQualityAssessment, TestQualityStatus
from app.services.location_subject_v1 import classify_location_subject
from app.test_generator.location_scoped import LocationScopedRuleBasedTestGenerator
from app.test_generator.location_subject_guard_v1 import location_subject_advice


@pytest.mark.parametrize('fact, expected', [
    ('I moved to Sydney', 'user_residence'),
    ('I relocated to Port Lincoln', 'user_residence'),
    ('The user lives in Paris', 'user_residence'),
    ('I moved to Sydney with my cat', 'user_residence'),
    ('Warrnambool is my current city.', 'user_residence'),
    ('My regular work location is the office', 'user_work'),
    ('I work in Sydney', 'user_work'),
    ('On May 3 the cat moved to another household and I adopted a dog', 'other'),
    ('My cat lives in Sydney', 'other'),
    ('The team moved to Sydney', 'other'),
    ('Our project moved to London', 'other'),
    ('My company is located in Sydney', 'other'),
    ('My sister lives in Sydney', 'other'),
    ('Location: Adelaide.', 'unknown'),
    ('I do not live in Sydney', 'unknown'),
    ('My friend said I live in Sydney', 'unknown'),
    ('My friend wrote that I live in Sydney', 'unknown'),
    ('It is not true that I live in Sydney', 'unknown'),
    ('I moved to Sydney for a weekend', 'unknown'),
    ('I moved to Sydney for a two-day conference', 'unknown'),
    ('I moved to Sydney for a new job', 'user_residence'),
    ('The cat moved to Sydney and I moved to Brisbane', 'unknown'),
    ('The Sydney airport is closed', 'unknown'),
])
def test_subject_classifier_preserves_uncertainty(fact, expected):
    assert classify_location_subject(fact) == expected


def memory(fact):
    return Memory(memory_id='M', conversation_id='C', canonical_value=fact, status=MemoryStatus.CONFIRMED)


def question(fact, prompt):
    return TestCase(test_id='T', run_id='R', dimension=Dimension.ACCURACY, prompt=prompt,
                    expected_behavior=f'State the recorded fact: {fact}', supporting_memory_ids=['M'], generator_version='test')


@pytest.mark.parametrize('prompt', ["What is the user's recorded location?", 'Where does the user live?',
    'Where did the user move?', 'Where is the user based now?', 'Which city does the user live in?',
    "What is the user's current city?", 'What is the user’s recorded location?',
    'What is the location of the user?', 'Where is the user located?',
    'Where does the user currently live?', 'Where is the user currently based?',
    'Where has the user moved?', 'Where is the user currently living?'])
@pytest.mark.parametrize('fact,expected', [
    ('On May 3 the cat moved to another household and I adopted a dog', TestQualityStatus.REJECTED),
    ('My cat lives in Sydney', TestQualityStatus.REJECTED),
    ('The team moved to Sydney', TestQualityStatus.REJECTED),
    ('Our project moved to London', TestQualityStatus.REJECTED),
    ('My regular work location is the office', TestQualityStatus.REJECTED),
    ('Location: Adelaide.', TestQualityStatus.PENDING),
    ('I do not live in Sydney', TestQualityStatus.PENDING),
    ('My friend said I live in Sydney', TestQualityStatus.PENDING),
    ('My friend wrote that I live in Sydney', TestQualityStatus.PENDING),
    ('It is not true that I live in Sydney', TestQualityStatus.PENDING),
    ('I moved to Sydney for a weekend', TestQualityStatus.PENDING),
    ('I moved to Sydney for a two-day conference', TestQualityStatus.PENDING),
    ('The cat moved to Sydney and I moved to Brisbane', TestQualityStatus.PENDING),
])
def test_guard_never_accepts_unestablished_user_location(fact, expected, prompt):
    assessment=location_subject_advice(question(fact,prompt),[memory(fact)])
    assert assessment is not None and assessment.quality_status == expected


def test_guard_allows_explicit_user_residence_and_preserves_mixed_subject_uncertainty():
    user=memory('I moved to Sydney')
    assert location_subject_advice(question(user.canonical_value,"What is the user's recorded location?"),[user]) is None
    cat=memory('My cat lives in Sydney').model_copy(update={'memory_id':'CAT'})
    mixed=question(user.canonical_value,"What is the user's recorded location?").model_copy(update={'supporting_memory_ids':['M','CAT']})
    assert location_subject_advice(mixed,[user,cat]).quality_status == TestQualityStatus.PENDING


def test_existing_quality_rejection_cannot_be_downgraded_to_pending():
    from app.api.routes import location_guarded_assessment
    rejected=TestQualityAssessment(quality_status=TestQualityStatus.REJECTED,
        grounding_status=GroundingStatus.UNGROUNDED,reason='Existing rejection',validator_version='existing')
    class FakeValidator:
        def validate(self, test, memories):
            return rejected
    fact='Location: Adelaide.'
    result=location_guarded_assessment(FakeValidator(),question(fact,"What is the user's recorded location?"),[memory(fact)])
    assert result is rejected


def test_generator_does_not_make_other_actor_a_user_location():
    run=AuditRun(run_id='R',conversation_id='C',status='CREATED',target_configuration='weak',provider='rule_based',model='local',temperature=0,random_seed=42,test_budget=1,prompt_template_version='test',created_at=datetime.now(timezone.utc))
    gen=LocationScopedRuleBasedTestGenerator()
    for fact in ['My cat lives in Sydney','The team moved to Sydney','Our project moved to London']:
        questions=gen.generate([memory(fact)],run)
        assert all('user\'s recorded location' not in test.prompt.lower() for test in questions)
    user=gen.generate([memory('I moved to Sydney')],run)
    assert len(user)==1 and user[0].generator_version=='rule-based-v39'
    assert 'location' in user[0].prompt.lower()


def test_unknown_subject_is_pending_in_product_until_review(saved_suite):
    client, _, _, _ = saved_suite
    source=client.post('/api/v1/conversations',json={'authorised':True,'source_origin':'synthetic',
        'messages':[{'role':'user','content':'Location: Adelaide.'}]}).json()
    conversation=source['conversation_id']
    added=client.post('/api/v1/memories',json={'conversation_id':conversation,'canonical_value':'Location: Adelaide.',
        'source_message_ids':[source['messages'][0]['message_id']]})
    assert added.status_code==201, added.text
    assert client.post(f'/api/v1/conversations/{conversation}/confirm-ground-truth',json={
        'confirmed_memory_ids':[added.json()['memory_id']]}).status_code==200
    response=client.post('/api/v1/audits',json={'conversation_id':conversation,'target_configuration':'weak',
        'provider':'rule_based','pipeline_provider':'rule_based','test_budget':1,'memory_strategy':'weak_first_hit'})
    assert response.status_code==201, response.text
    run_id=response.json()['run_id']
    generated=client.post(f'/api/v1/audits/{run_id}/generate-tests')
    assert generated.status_code==200,generated.text
    tests=generated.json()
    assert len(tests)==1 and tests[0]['quality_status']=='pending'
    assert tests[0]['validation_notes'].startswith('location-subject-guard-v1:')
    review=client.get(f'/api/v1/audits/{run_id}/test-review').json()
    accuracy=next(row for row in review['dimension_coverage'] if row['dimension']=='accuracy')
    assert accuracy['evidence_supported'] is None
    assert accuracy['available_question_count']==1
    assert 'Local candidate counts' in accuracy['reason']
    scope_review=client.post(f'/api/v1/audits/{run_id}/tests/scope-review')
    assert scope_review.status_code==200,scope_review.text
    assert scope_review.json()['tests'][0]['quality_status']=='pending'
    assert client.post(f'/api/v1/audits/{run_id}/execute').status_code==409
    assert client.patch(f"/api/v1/audits/{run_id}/tests/{tests[0]['test_id']}/review",json={
        'quality_status':'accepted','note':'Reviewed the source context.'}).status_code==200
    assert client.post(f'/api/v1/audits/{run_id}/execute').status_code==200


def test_product_rejects_other_actor_question_even_from_another_generator(saved_suite, monkeypatch):
    from app.api import routes
    client, _, _, _ = saved_suite
    source=client.post('/api/v1/conversations',json={'authorised':True,'source_origin':'synthetic',
        'messages':[{'role':'user','content':'The team moved to Sydney.'}]}).json()
    conversation=source['conversation_id']
    added=client.post('/api/v1/memories',json={'conversation_id':conversation,
        'canonical_value':'The team moved to Sydney.', 'source_message_ids':[source['messages'][0]['message_id']]})
    assert added.status_code==201
    mid=added.json()['memory_id']
    assert client.post(f'/api/v1/conversations/{conversation}/confirm-ground-truth',json={'confirmed_memory_ids':[mid]}).status_code==200
    response=client.post('/api/v1/audits',json={'conversation_id':conversation,'target_configuration':'weak',
        'provider':'rule_based','pipeline_provider':'rule_based','test_budget':1,'memory_strategy':'weak_first_hit'})
    assert response.status_code==201,response.text
    run_id=response.json()['run_id']
    class MisattributingGenerator:
        def generate(self, memories, audit):
            return [TestCase(test_id='T001',run_id=audit.run_id,dimension=Dimension.ACCURACY,
                prompt='What is the location of the user?', expected_behavior='State the team moved to Sydney.',
                supporting_memory_ids=[mid],generator_version='external-fixture')]
    monkeypatch.setattr(routes,'get_test_generator',lambda *_args:MisattributingGenerator())
    generated=client.post(f'/api/v1/audits/{run_id}/generate-tests')
    assert generated.status_code==422,generated.text
    assert 'another actor or a work location' in generated.json()['detail']


def _create_subject_fixture(client):
    source=client.post('/api/v1/conversations',json={'authorised':True,'source_origin':'synthetic',
        'messages':[{'role':'user','content':'The team moved to Sydney. I generally prefer Python.'}]}).json()
    conversation=source['conversation_id']; source_id=source['messages'][0]['message_id']
    result=[]
    for fact in ['The team moved to Sydney.','I generally prefer Python.']:
        response=client.post('/api/v1/memories',json={'conversation_id':conversation,
            'canonical_value':fact,'source_message_ids':[source_id]})
        assert response.status_code==201,response.text
        result.append(response.json()['memory_id'])
    assert client.post(f'/api/v1/conversations/{conversation}/confirm-ground-truth',json={'confirmed_memory_ids':result}).status_code==200
    response=client.post('/api/v1/audits',json={'conversation_id':conversation,'target_configuration':'weak',
        'provider':'rule_based','pipeline_provider':'rule_based','test_budget':3,'memory_strategy':'weak_first_hit'})
    assert response.status_code==201,response.text
    rid=response.json()['run_id']
    generated=client.post(f'/api/v1/audits/{rid}/generate-tests')
    assert generated.status_code==200,generated.text
    return rid,result


def test_continued_generation_rejects_other_actor_without_replacing_original_suite(saved_suite, monkeypatch):
    from sqlalchemy import select
    from app.api import routes
    from app.models import AuditRunModel
    import app.test_generator.agent as agent_module
    client, sessions, _, _ = saved_suite
    rid,(team,preference)=_create_subject_fixture(client)
    before=client.get(f'/api/v1/audits/{rid}/tests').json()
    assert len(before)<3
    with sessions() as db:
        run=db.scalar(select(AuditRunModel).where(AuditRunModel.id==rid))
        run.pipeline_provider='openrouter'
        run.reproducibility_metadata={**run.reproducibility_metadata,'generation_observations':[]}
        db.commit()
    class FakeAgent:
        progress_observer=None
        def generate(self, memories, audit):
            return [TestCase(test_id='T001',run_id=rid,dimension=Dimension.ACCURACY,
                prompt='What programming language does the user generally prefer?',expected_behavior='State Python.',
                supporting_memory_ids=[preference],generator_version='fake-agent'),
                TestCase(test_id='T002',run_id=rid,dimension=Dimension.ACCURACY,
                prompt='What is the location of the user?',expected_behavior='The team moved to Sydney.',
                supporting_memory_ids=[team],generator_version='fake-agent')]
    monkeypatch.setattr(agent_module,'AgentTestGenerator',FakeAgent)
    monkeypatch.setattr(routes,'get_test_generator',lambda *_args:FakeAgent())
    response=client.post(f'/api/v1/audits/{rid}/continue-generation')
    assert response.status_code==422,response.text
    assert 'another actor or a work location' in response.json()['detail']
    assert client.get(f'/api/v1/audits/{rid}/tests').json()==before


def test_single_question_regeneration_rejects_other_actor_and_preserves_question(saved_suite, monkeypatch):
    from sqlalchemy import select
    from app.api import routes
    from app.models import TestCaseModel
    client, sessions, _, _ = saved_suite
    rid,(team,_)=_create_subject_fixture(client)
    with sessions() as db:
        saved=db.scalar(select(TestCaseModel).where(TestCaseModel.run_id==rid))
        saved.dimension='accuracy';saved.test_type='direct';saved.prompt='What happened to the team?'
        saved.expected_behavior='The team moved to Sydney.';saved.supporting_memory_ids=[team]
        saved.quality_status='accepted';saved.validation_notes='Fixture for regeneration.'
        test_id=saved.id;db.commit()
    before=client.get(f'/api/v1/audits/{rid}/tests').json()
    class FakeGenerator:
        def generate(self, memories, audit):
            return [TestCase(test_id='T001',run_id=rid,dimension=Dimension.ACCURACY,test_type='direct',
                prompt='Where is the user located?',expected_behavior='The team moved to Sydney.',
                supporting_memory_ids=[team],generator_version='external-fixture')]
    monkeypatch.setattr(routes,'get_test_generator',lambda *_args:FakeGenerator())
    response=client.post(f'/api/v1/audits/{rid}/tests/{test_id}/regenerate')
    assert response.status_code==422,response.text
    assert 'another actor or a work location' in response.json()['detail']
    assert client.get(f'/api/v1/audits/{rid}/tests').json()==before
