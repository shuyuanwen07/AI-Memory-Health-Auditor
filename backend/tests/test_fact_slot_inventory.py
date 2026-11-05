"""The inventory proposes slots only; it never certifies generated questions."""
import pytest
from types import SimpleNamespace
from app.schemas import Dimension, Memory, MemoryRelationship, MemoryStatus, RelationshipType
from app.test_generator.agent import AgentTestGenerator
from app.test_generator.fact_slot_inventory import fact_slots


def memory(identity='m1', **changes):
    values = dict(memory_id=identity, conversation_id='c1', canonical_value='A referenced fact',
                  status=MemoryStatus.CONFIRMED, source_message_ids=['s1'], relationships=[])
    return Memory(**(values | changes))


@pytest.mark.parametrize('changes', [dict(status=MemoryStatus.CANDIDATE), dict(status=MemoryStatus.REJECTED),
                                     dict(source_message_ids=[]), dict(source_message_ids=[' ']), dict(canonical_value='  ')])
def test_unconfirmed_or_uncited_facts_do_not_create_slots(changes):
    assert fact_slots([memory(**changes)]) == []


@pytest.mark.parametrize('relation', list(RelationshipType))
def test_known_relationship_endpoints_excluded(relation):
    left = memory('m1', relationships=[MemoryRelationship(type=relation, target_memory_id='m2')])
    assert [slot.supporting_memory_ids for slot in fact_slots([left, memory('m2'), memory('m3')])] == [['m3']]


def test_mixed_conversations_and_duplicate_ids_fail_closed():
    with pytest.raises(ValueError):
        fact_slots([memory(), memory()])
    with pytest.raises(ValueError):
        fact_slots([memory(), memory('m2', conversation_id='other')])


def test_partial_can_propose_a_slot_without_a_rule_template():
    sample = [memory(canonical_value='My apartment has a small north-facing balcony')]
    seeds, quotas, available = AgentTestGenerator._coverage_seed_inventory(sample, 4, coverage_policy='evidence_supported_only_v1')
    assert available[Dimension.ACCURACY] == quotas[Dimension.ACCURACY] == 1
    assert seeds[0].supporting_memory_ids == ['m1']
    assert 'no question' in seeds[0].prompt


def test_partial_plan_avoids_repeating_update_as_conflict_when_real_conflict_exists():
    update = [memory('old'), memory('new', relationships=[MemoryRelationship(type=RelationshipType.UPDATE, target_memory_id='old')])]
    conflict = [memory('venue1'), memory('venue2', relationships=[MemoryRelationship(type=RelationshipType.CONFLICT, target_memory_id='venue1')])]
    freshness = SimpleNamespace(dimension=Dimension.FRESHNESS, supporting_memory_ids=['old', 'new'])
    repeated = SimpleNamespace(dimension=Dimension.CONFLICT_RESOLUTION, supporting_memory_ids=['old', 'new'])
    unresolved = SimpleNamespace(dimension=Dimension.CONFLICT_RESOLUTION, supporting_memory_ids=['venue1', 'venue2'])
    select = AgentTestGenerator._remove_redundant_partial_update_slots
    assert select([freshness, repeated, unresolved], update + conflict) == [freshness, unresolved]
    assert select([freshness, repeated], update) == [freshness, repeated]
