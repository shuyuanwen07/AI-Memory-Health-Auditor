"""Defects observed during real Phase 2 synthetic workflow verification."""
from datetime import datetime, timezone
NOW=datetime(2026,10,27,tzinfo=timezone.utc)
import json
from pathlib import Path
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Conversation, Memory, MemoryStatus, MemoryRelationship, RelationshipType, AuditRun, Dimension, TestCase, TargetResponse


def test_signed_region_brief_survives_extraction_and_forms_unresolved_conflict():
    conversation=Conversation.model_validate({'conversation_id':'C','authorised':True,'created_at':NOW,'messages':[
        {'message_id':'one','timestamp':NOW,'role':'user','content':'The current deployment plan for the Maple capstone says the production region is North.'},
        {'message_id':'two','timestamp':NOW,'role':'user','content':'The signed client brief for the same Maple capstone deployment says the production region is South.'}]})
    memories=RuleBasedMemoryExtractor().extract(conversation)
    assert len(memories)==2
    assert any(r.type==RelationshipType.CONFLICT and r.target_memory_id==memories[0].memory_id for r in memories[1].relationships)


def test_database_migration_value_is_not_the_deictic_sentence_tail():
    evaluator=RuleBasedBehaviourEvaluator()
    test=TestCase(test_id='T',run_id='R',dimension=Dimension.FRESHNESS,
        prompt='Which database should the user use now? Explain how it replaces the historical value.',
        expected_behavior='Use the recorded current value: We migrated the Maple capstone backend to PostgreSQL; MySQL is no longer used there.',
        supporting_memory_ids=['new'],generator_version='fixture')
    memory=Memory(memory_id='new',conversation_id='C',canonical_value='We migrated the Maple capstone backend to PostgreSQL; MySQL is no longer used there.',status=MemoryStatus.CONFIRMED)
    answer=TargetResponse(response_id='R1',run_id='R',test_id='T',model='saved-real-response',temperature=0,created_at=NOW,response_text='PostgreSQL — the records say the Maple backend was migrated from MySQL to PostgreSQL.')
    assert evaluator.evaluate(test,answer,[memory]).passed is True
    assert evaluator.evaluate(test,answer.model_copy(update={'response_text':'MySQL'}),[memory]).passed is False


def test_missing_conflict_region_cannot_pass_on_clarification_words_alone():
    evaluator=RuleBasedBehaviourEvaluator()
    support=['The deployment plan says the production region is North.', 'The signed brief says the production region is South.']
    assert evaluator._unresolved_deployment_conflict_issues('North is listed, but another conflicting requirement is missing. Please clarify which region controls.',support)
    assert evaluator._unresolved_deployment_conflict_issues('North and South conflict. Please clarify which requirement controls.',support)==[]


def test_unresolved_reference_status_is_not_used_as_a_scalar_accuracy_question():
    from app.schemas import TargetConfiguration
    fact=Memory(memory_id='M1',conversation_id='C',canonical_value='Both deployment documents are still active; I have not established which instruction controls.',status=MemoryStatus.CONFIRMED)
    location=Memory(memory_id='M2',conversation_id='C',canonical_value='I live in Adelaide.',status=MemoryStatus.CONFIRMED)
    audit=AuditRun(run_id='R',conversation_id='C',target_configuration=TargetConfiguration.WEAK,test_budget=4,status='CREATED',provider='rule_based',model='fixture',temperature=0,random_seed=42,prompt_template_version='fixture',created_at=NOW)
    suite=RuleBasedTestGenerator().generate([fact,location],audit)
    assert len(suite)==1 and suite[0].supporting_memory_ids==['M2']
