"""Development regressions for temporal scope and bounded omission classification."""
from datetime import datetime,timezone
import pytest
from app.schemas import Memory,MemoryRelationship,TestCase,TargetResponse,AuditRun
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.evaluator.source_abstention import classify_source_abstention
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.test_generator.baselines import DirectGroundTruthTestGenerator,FixedTemplateTestGenerator,ContextualIndirectTestGenerator

def pair(kind='UPDATE'):
 values={'UPDATE':('The Talus project previously used SQLite.','The Talus project now uses MariaDB.'),'CONTEXTUAL_OVERRIDE':('I generally prefer Rust.','The Talus project requires Java.'),'CONFLICT':('The Talus production region is East.','The Talus production region is West.')}
 old,new=values[kind]
 return [Memory(memory_id='old',conversation_id='C',canonical_value=old,status='confirmed'),Memory(memory_id='new',conversation_id='C',canonical_value=new,status='confirmed',relationships=[MemoryRelationship(type=kind,target_memory_id='old')])]

@pytest.mark.parametrize('dimension',['accuracy','freshness','conflict_resolution','appropriate_use'])
@pytest.mark.parametrize('kind,prompt,answer,expected',[
 ('UPDATE','What database does the Talus project use now?',"I don't have enough remembered information to identify the current database.",'freshness'),
 ('CONTEXTUAL_OVERRIDE','What is the language requirement for the Talus project?',"I cannot identify the language requirement from the supplied record.",'appropriate_use'),
 ('CONFLICT','What deployment region for the Talus project should be used?',"I don't have remembered information about deployment-region constraints.",'conflict_resolution'),
])
def test_observed_explicit_omission_uses_source_and_question_not_test_dimension(dimension,kind,prompt,answer,expected):
 memories=pair(kind)
 reference={'UPDATE':'Use the current value: MariaDB.','CONTEXTUAL_OVERRIDE':'Java is required.','CONFLICT':'Identify both conflicting constraints and request clarification.'}[kind]
 test=TestCase(test_id='T',run_id='R',dimension=dimension,prompt=prompt,expected_behavior=reference,supporting_memory_ids=['old','new'],generator_version='fixture')
 response=TargetResponse(response_id='A',test_id='T',run_id='R',response_text=answer,model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
 verdict=RuleBasedBehaviourEvaluator().evaluate(test,response,memories)
 assert verdict.passed is False
 assert verdict.failure_classification.method=='source-abstention-v1'
 assert verdict.failure_type.value==expected
 assert 'not its internal cause' in verdict.failure_classification.reason

@pytest.mark.parametrize('answer',[
 'The project previously used SQLite.',
 'I cannot identify the current database, but the current database is MariaDB.',
 'If I cannot identify the current database, I should ask for help.',
 'The example says I cannot identify the current database.',
 'Irrelevant prose with none of the expected keywords.',
])
def test_missing_terms_or_history_alone_does_not_create_typed_omission(answer):
 assert classify_source_abstention('What database does the Talus project use now?',answer,pair()) is None

def test_without_source_edge_or_with_other_project_classification_abstains():
 memories=pair();memories[1].relationships=[]
 answer="I cannot identify the current database."
 assert classify_source_abstention('What database does the Talus project use now?',answer,memories) is None
 assert classify_source_abstention('What database does the Nacre project use now?',answer,pair()) is None
 assert classify_source_abstention('What database did the Talus project use previously?',answer,pair()) is None

def test_ambiguous_multi_topic_query_keeps_classification_unknown():
 memories=pair()+[m.model_copy(update={'memory_id':'c'+m.memory_id,'relationships':[MemoryRelationship(type='CONFLICT',target_memory_id='cold')] if m.memory_id=='new' else []}) for m in pair('CONFLICT')]
 assert classify_source_abstention('What is the current database and deployment region for the Talus project?',"I cannot identify this information.",memories) is None

@pytest.mark.parametrize('generator',[RuleBasedTestGenerator,DirectGroundTruthTestGenerator,FixedTemplateTestGenerator,ContextualIndirectTestGenerator])
def test_updated_database_accuracy_question_explicitly_requests_current_state(generator):
 audit=AuditRun(run_id='R',conversation_id='C',status='CREATED',target_configuration='strong',provider='rule_based',model='fixture',test_budget=4,temperature=0,random_seed=42,prompt_template_version='fixture',created_at=datetime.now(timezone.utc))
 questions=generator().generate(pair(),audit)
 accuracy=[t for t in questions if t.dimension.value=='accuracy' and 'new' in t.supporting_memory_ids]
 assert accuracy
 for q in accuracy:
  assert 'current' in q.prompt.lower()
  assert 'MariaDB' not in q.prompt and 'SQLite' not in q.prompt
