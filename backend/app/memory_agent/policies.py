"""Explainable memory retrieval policies for controlled target agents.

The underlying language model does not decide which memories are available.
This module does.  Each policy returns an ordered private context from lowest
to highest priority, so the existing controlled target's strong profile can
use the final record while the weak profile sees only the first record.
"""
from __future__ import annotations

import re

from app.schemas import Memory, MemoryStrategy, RelationshipType, TestCase

_TERMS = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]*")
_STOP = frozenset({"the", "and", "for", "with", "from", "that", "this", "what", "which", "should", "would", "about", "user", "memory", "remembered"})


def build_target_memory_context(test: TestCase, memories: list[Memory], strategy: MemoryStrategy) -> list[str]:
    """Select the controlled agent's private context for one test.

    Only memories explicitly supporting the generated test are eligible. This
    keeps retrieval traceable and avoids exposing unrelated user information.
    """
    by_id = {memory.memory_id: memory for memory in memories}
    candidates = [by_id[memory_id] for memory_id in test.supporting_memory_ids if memory_id in by_id]
    if not candidates:
        return []
    if strategy == MemoryStrategy.WEAK_FIRST_HIT:
        return [candidates[0].canonical_value]

    targets_of_update = {
        relation.target_memory_id
        for memory in candidates for relation in memory.relationships
        if relation.type == RelationshipType.UPDATE
    }
    if strategy == MemoryStrategy.STRONG_RULE_BASED:
        ordered = sorted(candidates, key=lambda memory: _rule_rank(memory, targets_of_update))
    else:
        ordered = sorted(candidates, key=lambda memory: _score_rank(memory, test, targets_of_update))
    return [memory.canonical_value for memory in ordered]


def _rule_rank(memory: Memory, targets_of_update: set[str]) -> tuple[int, float, str]:
    """Explicit policy: contextual override > update > stable > superseded."""
    priority = 20
    if memory.memory_id in targets_of_update:
        priority = 0
    if any(relation.type == RelationshipType.UPDATE for relation in memory.relationships):
        priority = 40
    if any(relation.type == RelationshipType.CONTEXTUAL_OVERRIDE for relation in memory.relationships):
        priority = 60
    return priority, _time_value(memory), memory.memory_id


def _score_rank(memory: Memory, test: TestCase, targets_of_update: set[str]) -> tuple[float, float, str]:
    """A transparent weighted alternative suitable for later ablation studies."""
    prompt_terms = _tokens(test.prompt)
    memory_terms = _tokens(memory.canonical_value)
    score = len(prompt_terms & memory_terms) * 10.0
    if memory.memory_id in targets_of_update:
        score -= 30.0
    if any(relation.type == RelationshipType.UPDATE for relation in memory.relationships):
        score += 20.0
    if any(relation.type == RelationshipType.CONTEXTUAL_OVERRIDE for relation in memory.relationships):
        score += 30.0
    if any(relation.type == RelationshipType.CONFLICT for relation in memory.relationships):
        score += 5.0
    return score, _time_value(memory), memory.memory_id


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TERMS.findall(text) if token.lower() not in _STOP}


def _time_value(memory: Memory) -> float:
    return memory.timestamp.timestamp() if memory.timestamp else 0.0
