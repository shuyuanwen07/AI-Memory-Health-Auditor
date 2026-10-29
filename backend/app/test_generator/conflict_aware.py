"""Keep known unresolved conflicts from being described as settled updates."""
from app.schemas import Dimension, MemoryStatus, RelationshipType
from app.test_generator.location_scoped import LocationScopedRuleBasedTestGenerator


class ConflictAwareRuleBasedTestGenerator(LocationScopedRuleBasedTestGenerator):
    VERSION = 'rule-based-v40'

    def generate(self, memories, audit):
        by_id = {m.memory_id: m for m in memories
                 if m.conversation_id == audit.conversation_id
                 and m.status in {MemoryStatus.CONFIRMED, MemoryStatus.EDITED}}
        conflicted = set()
        for memory in by_id.values():
            for relation in memory.relationships:
                if relation.type == RelationshipType.CONFLICT and relation.target_memory_id in by_id:
                    conflicted.update((memory.memory_id, relation.target_memory_id))
        self._unsafe_update_pairs = {
            frozenset((memory.memory_id, relation.target_memory_id))
            for memory in by_id.values() for relation in memory.relationships
            if relation.type == RelationshipType.UPDATE and relation.target_memory_id in by_id
            and (memory.memory_id in conflicted or relation.target_memory_id in conflicted)
        }
        self._suppressed_known_conflict = []
        result = super().generate(memories, audit)
        self.last_observation['known_conflict_suppressed_count'] = len(self._suppressed_known_conflict)
        self.last_observation['known_conflict_suppressed_candidates'] = self._suppressed_known_conflict
        return result

    def _balanced_order(self, candidates):
        kept = []
        for candidate in candidates:
            dimension, prompt, expected, ids, kind = candidate
            update_question = (dimension == Dimension.FRESHNESS or
                               (dimension == Dimension.CONFLICT_RESOLUTION and
                                'has an explicit update.' in prompt))
            if update_question and frozenset(ids) in self._unsafe_update_pairs:
                self._suppressed_known_conflict.append({
                    'dimension': dimension.value, 'prompt': prompt,
                    'expected_behavior': expected, 'supporting_memory_ids': list(ids),
                    'reason': 'An UPDATE endpoint is part of a confirmed CONFLICT; a unique current value is not established.',
                })
            else:
                kept.append(candidate)
        return super()._balanced_order(kept)
