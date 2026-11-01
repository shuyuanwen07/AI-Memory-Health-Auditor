"""Evidence-only coverage commitments; these objects are never target tests."""
from dataclasses import dataclass, replace

from app.schemas import Dimension, MemoryStatus, RelationshipType, TestType


@dataclass(frozen=True)
class PlanningEvidenceSlot:
    dimension: Dimension
    test_type: TestType
    supporting_memory_ids: list[str]

    def model_copy(self, *, update):
        # Match the sole immutable update used by allowed-test-type planning.
        return replace(self, **update)


def planning_evidence_slots(memories):
    """Inventory confirmed cited evidence without pretending to write questions.

    Known relationship endpoints cannot be standalone Accuracy evidence. No
    missing relation is inferred from text, time or synthetic scenario IDs.
    A relation slot includes the full connected unresolved-conflict component.
    The generator must later write, validate and semantically review real tests.
    """
    if len({m.conversation_id for m in memories}) > 1:
        raise ValueError('Coverage planning cannot mix conversation sources.')
    if len({m.memory_id for m in memories}) != len(memories):
        raise ValueError('Coverage planning requires unique memory IDs.')
    by_id = {m.memory_id: m for m in memories
             if m.status in (MemoryStatus.CONFIRMED, MemoryStatus.EDITED)
             and m.canonical_value.strip() and m.source_message_ids
             and all(str(ref).strip() for ref in m.source_message_ids)}
    endpoints = {m.memory_id for m in memories if m.relationships}
    endpoints.update(r.target_memory_id for m in memories for r in m.relationships)
    conflicts = []
    for memory in by_id.values():
        for relation in memory.relationships:
            if relation.type == RelationshipType.CONFLICT and relation.target_memory_id != memory.memory_id:
                conflicts.append((memory.memory_id, relation.target_memory_id))

    def conflict_closure(ids):
        selected = set(ids)
        while True:
            extended = selected | {mid for pair in conflicts if selected.intersection(pair) for mid in pair}
            if not extended.issubset(by_id):
                return None
            if extended == selected:
                return sorted(selected)
            selected = extended

    result = []
    for memory in by_id.values():
        if memory.memory_id not in endpoints:
            result.append(PlanningEvidenceSlot(Dimension.ACCURACY, TestType.DIRECT, [memory.memory_id]))
    has_explicit_conflict = any(left in by_id and right in by_id for left, right in conflicts)
    for memory in by_id.values():
        for relation in memory.relationships:
            if relation.target_memory_id not in by_id or relation.target_memory_id == memory.memory_id:
                continue
            ids = conflict_closure([memory.memory_id, relation.target_memory_id])
            if ids is None:
                continue
            if relation.type == RelationshipType.UPDATE:
                result.append(PlanningEvidenceSlot(Dimension.FRESHNESS, TestType.CONTEXTUAL, ids))
                if not has_explicit_conflict:
                    result.append(PlanningEvidenceSlot(Dimension.CONFLICT_RESOLUTION, TestType.INDIRECT, ids))
            elif relation.type == RelationshipType.CONFLICT:
                result.append(PlanningEvidenceSlot(Dimension.CONFLICT_RESOLUTION, TestType.INDIRECT, ids))
            elif relation.type == RelationshipType.CONTEXTUAL_OVERRIDE:
                result.append(PlanningEvidenceSlot(Dimension.APPROPRIATE_USE, TestType.PARAPHRASED, ids))
    unique = {}
    for slot in result:
        key = (slot.dimension, slot.test_type, tuple(sorted(slot.supporting_memory_ids)))
        unique.setdefault(key, slot)
    return list(unique.values())
