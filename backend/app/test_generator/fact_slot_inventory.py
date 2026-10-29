"""Provisional cited-fact inventory; candidate slots are not valid questions."""
from app.schemas import Dimension, MemoryStatus, TestCase, TestType


def fact_slots(memories):
    """Inventory cited confirmed facts, excluding all known relation endpoints.

    Extracted relationships can be incomplete, so exclusion of known endpoints
    does not certify that a fact has no conflicts. Source and semantic review of
    any subsequently generated question remains mandatory.
    """
    conversations = {m.conversation_id for m in memories}
    if len(conversations) > 1:
        raise ValueError('Candidate memories must share a conversation')
    ids = [m.memory_id for m in memories]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate memory IDs')
    endpoints = {m.memory_id for m in memories if m.relationships}
    endpoints.update(r.target_memory_id for m in memories for r in m.relationships)
    result = []
    for memory in memories:
        if (memory.status not in (MemoryStatus.CONFIRMED, MemoryStatus.EDITED)
                or not memory.canonical_value.strip() or not memory.source_message_ids
                or any(not str(source).strip() for source in memory.source_message_ids)
                or memory.memory_id in endpoints):
            continue
        result.append(TestCase(test_id=f'S{len(result)+1:03}', run_id='COVERAGE_PREVIEW',
                               dimension=Dimension.ACCURACY, test_type=TestType.DIRECT,
                               prompt='Candidate slot only; no question has been generated.',
                               expected_behavior='Candidate slot only; no answer has been generated.',
                               supporting_memory_ids=[memory.memory_id], generator_version='fact-slot-inventory-v1'))
    return result
