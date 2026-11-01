"""Planning capacity must not certify actual question quality."""
from dataclasses import fields

import pytest

from app.schemas import Dimension, Memory, MemoryRelationship, TestCase, TestType
from app.test_generator.evidence_slot_inventory import PlanningEvidenceSlot, planning_evidence_slots
from app.test_generator.quality import RuleBasedTestQualityValidator


def memory(mid, text, relationships=(), **extra):
    return Memory(memory_id=mid, conversation_id='C', canonical_value=text,
                  status=extra.pop('status', 'confirmed'),
                  source_message_ids=extra.pop('source_message_ids', ['source-'+mid]),
                  relationships=list(relationships), **extra)


def edge(kind, target):
    return MemoryRelationship(type=kind, target_memory_id=target)


def test_unknown_topics_yield_only_evidence_objects_not_questions():
    slots=planning_evidence_slots([memory('a', 'The visitor enjoys peculiar mineral collections.'),
                                  memory('b', 'The visitor serves refreshments.')])
    assert len(slots)==2
    assert all(slot.dimension==Dimension.ACCURACY for slot in slots)
    assert {field.name for field in fields(PlanningEvidenceSlot)}=={'dimension','test_type','supporting_memory_ids'}
    assert all(not hasattr(slot,'prompt') and not hasattr(slot,'expected_behavior') for slot in slots)
    assert all(not isinstance(slot,TestCase) for slot in slots)
    assert slots[0].model_copy(update={'test_type':TestType.CONTEXTUAL}).test_type==TestType.CONTEXTUAL


def test_relation_slots_preserve_conflict_closure_without_counting_endpoints_as_accuracy():
    memories=[memory('old','The earlier value was amber.'),
              memory('new','The updated value is violet.',[edge('UPDATE','old')]),
              memory('other','For the same period the value is amber.',[edge('CONFLICT','new')]),
              memory('third','Another incompatible value is ivory.',[edge('CONFLICT','other')]),
              memory('scope','For the display only the value is amber.',[edge('CONTEXTUAL_OVERRIDE','new')]),
              memory('fact','The visitor collects stamps.')]
    slots=planning_evidence_slots(memories)
    assert {slot.dimension for slot in slots}==set(Dimension)
    assert [slot.supporting_memory_ids for slot in slots if slot.dimension==Dimension.ACCURACY]==[['fact']]
    fresh=next(slot for slot in slots if slot.dimension==Dimension.FRESHNESS)
    scoped=next(slot for slot in slots if slot.dimension==Dimension.APPROPRIATE_USE)
    assert set(fresh.supporting_memory_ids)=={'old','new','other','third'}
    assert set(scoped.supporting_memory_ids)=={'scope','new','other','third'}
    assert all(set(slot.supporting_memory_ids)>={'new','other','third'} for slot in slots if slot.dimension==Dimension.CONFLICT_RESOLUTION)


def test_facts_and_different_observation_times_do_not_invent_relationships():
    memories=[memory('a','The old preference is amber.'),memory('b','The new preference is violet.'),
              memory('c','For an exhibition only the preference is amber.')]
    slots=planning_evidence_slots(memories)
    assert all(slot.dimension==Dimension.ACCURACY for slot in slots)


def test_unavailable_citations_and_unconfirmed_facts_cannot_add_capacity():
    assert planning_evidence_slots([memory('a','A fact.',status='candidate'),
                                   memory('b','A second fact.',source_message_ids=[]),
                                   memory('c','',source_message_ids=['s'])])==[]


def test_missing_conflict_partner_blocks_affected_relation_slots():
    memories=[memory('old','The earlier value was amber.'),
              memory('new','The updated value is violet.',[edge('UPDATE','old'),edge('CONFLICT','missing')])]
    assert planning_evidence_slots(memories)==[]


def test_duplicate_relationships_do_not_multiply_capacity():
    memories=[memory('old','Earlier value.'),memory('new','New value.',[edge('UPDATE','old'),edge('UPDATE','old')])]
    slots=planning_evidence_slots(memories)
    assert len([slot for slot in slots if slot.dimension==Dimension.FRESHNESS])==1


def test_mixed_conversations_and_duplicate_memory_ids_are_rejected():
    with pytest.raises(ValueError,match='conversation'):
        planning_evidence_slots([memory('a','One fact.'),memory('b','Two facts.').model_copy(update={'conversation_id':'D'})])
    with pytest.raises(ValueError,match='unique'):
        planning_evidence_slots([memory('a','One fact.'),memory('a','Two facts.')])


def test_actual_questions_still_face_unchanged_wording_and_relationship_gates():
    ms=[memory('fact','The visitor collects stamps.')]
    test=TestCase(test_id='T',run_id='R',dimension=Dimension.ACCURACY,
                  prompt="What is the user's recorded stored information?",expected_behavior='Stamps.',
                  supporting_memory_ids=['fact'],generator_version='fixture')
    assert RuleBasedTestQualityValidator().validate(test,ms).quality_status.value=='rejected'
    freshness=test.model_copy(update={'dimension':Dimension.FRESHNESS,'prompt':'What changed?'})
    assert RuleBasedTestQualityValidator().validate(freshness,ms).quality_status.value=='rejected'
