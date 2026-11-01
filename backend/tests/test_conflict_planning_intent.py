"""Mixed relationship slots retain both their dimension and unresolved conflict."""
import json
from types import SimpleNamespace

import pytest

from app.schemas import Dimension, Memory, MemoryRelationship, TestCase
from app.test_generator.agent import AgentTestGenerator


@pytest.mark.parametrize(('dimension','relations','expected'), [
    (Dimension.FRESHNESS, ['UPDATE'], 'Apply the current record over its explicitly replaced historical record.'),
    (Dimension.APPROPRIATE_USE, ['CONTEXTUAL_OVERRIDE'], 'Apply a contextual requirement only in its scope while retaining the general preference elsewhere.'),
])
def test_uncontested_intents_keep_their_existing_contract(dimension,relations,expected):
    assert AgentTestGenerator._intent(dimension,relations) == expected


@pytest.mark.parametrize('dimension', [Dimension.FRESHNESS,Dimension.APPROPRIATE_USE])
def test_conflict_does_not_erase_the_dimension_or_become_a_unique_current_value(dimension):
    kind = 'UPDATE' if dimension == Dimension.FRESHNESS else 'CONTEXTUAL_OVERRIDE'
    intent = AgentTestGenerator._intent(dimension,[kind,'CONFLICT'])
    summary = AgentTestGenerator._coverage_slot_review_summary({
        'dimension':dimension.value, 'relationship_signatures':[
            {'source_memory_id':'current','type':kind,'target_memory_id':'prior'},
            {'source_memory_id':'other','type':'CONFLICT','target_memory_id':'current'},
        ],
    })
    assert 'clarif' in intent and 'conflict' in intent
    assert 'current --'+kind+'--> prior' in summary
    assert 'other --CONFLICT--> current' in summary
    assert 'Test that the current record replaces the historical record.' not in summary
    if dimension == Dimension.FRESHNESS:
        assert 'historical update' in intent and 'earlier value' in intent
        assert 'earlier-to-replacement historical change' in summary
        assert 'update alone does not resolve' in summary
    else:
        assert 'scoped instruction' in intent and 'only within its context' in intent
        assert 'unambiguous instruction only in its stated scope' in summary
        assert 'disputed scoped or general value' in summary


def test_uncontested_freshness_review_summary_is_unchanged():
    assert AgentTestGenerator._coverage_slot_review_summary({
        'dimension':'freshness','relationship_signatures':[
            {'source_memory_id':'M2','type':'UPDATE','target_memory_id':'M1'}],
    }) == 'Validated Freshness relation: M2 --UPDATE--> M1. Test that the current record replaces the historical record.'


def test_planner_and_reviewer_receive_the_same_conflict_preserving_slot_intent():
    def memory(mid,text,relations=()):
        return Memory(memory_id=mid,conversation_id='C',canonical_value=text,status='confirmed',
                      source_message_ids=['S'+mid],relationships=list(relations))
    memories = [
        memory('old',"The user's regular workout is swimming."),
        memory('current',"As of May 3, the user's regular workout is running instead of swimming.",
               [MemoryRelationship(type='UPDATE',target_memory_id='old')]),
        memory('other',"For the same period the user's regular workout is exclusively swimming, not running.",
               [MemoryRelationship(type='CONFLICT',target_memory_id='current')]),
        memory('scoped','During pool rehabilitation sessions the user swims; this does not settle the regular workout elsewhere.',
               [MemoryRelationship(type='CONTEXTUAL_OVERRIDE',target_memory_id='current')]),
        memory('time','The user prefers morning sessions.'),
    ]
    captured = {}
    class Planner:
        def complete_json(self,**request):
            payload=json.loads(request['prompt'].split('\n\n',1)[1]);captured['planner']=payload
            return {'selected_candidate_ids_by_dimension':{
                dim:ids[:payload['required_available_quota_by_dimension'][dim]]
                for dim,ids in payload['candidate_ids_by_dimension'].items()},'coverage_notes':[]}
    class Reviewer:
        def complete_json(self,**request):
            captured['reviewer']=json.loads(request['prompt'].split('\n\n',1)[1])
            captured['reviewer_version']=request['prompt_template_version']
            return {'duplicate_pairs':[],'quality_findings':[],'slot_alignment_findings':[]}
    generator=AgentTestGenerator(client=object(),planner_client=Planner(),reviewer_client=Reviewer())
    generator._agent_observation={'semantic_reviews':[]}
    audit=SimpleNamespace(test_budget=4,reproducibility=SimpleNamespace(coverage_policy='strict_full_v1'))
    plan=generator._build_coverage_plan(memories,audit)
    assert len(plan)==4
    for dim in ('freshness','appropriate_use'):
        slot=next(x for x in plan if x['dimension']==dim)
        inventory=next(x for x in captured['planner']['candidate_slots'] if x['candidate_id']==slot['planner_candidate_id'])
        assert slot['intent']==inventory['intent']
        assert 'CONFLICT' in slot['relationship_types']
        assert 'clarif' in slot['intent'] and 'conflict' in slot['intent']
    tests=[TestCase(test_id=f'T{i}',run_id='R',dimension=slot['dimension'],test_type=slot['test_type'],
                    prompt='Describe the relevant recorded information.',expected_behavior='Keep source distinctions and ask for clarification.',
                    supporting_memory_ids=slot['supporting_memory_ids'],generator_version='fixture')
           for i,slot in enumerate(plan,1)]
    generator._review_semantic_intent(tests,memories,plan)
    for dim in ('freshness','appropriate_use'):
        reviewed=next(x for x in captured['reviewer']['tests'] if x['dimension']==dim)
        assert reviewed['coverage_slot']['intent']==next(x['intent'] for x in plan if x['dimension']==dim)
        assert 'unresolved' in reviewed['coverage_slot_summary']
    assert captured['reviewer_version']==AgentTestGenerator.REVIEWER_VERSION
