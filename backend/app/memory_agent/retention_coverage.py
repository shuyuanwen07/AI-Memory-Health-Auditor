"""Pure retention selectors; the store explicitly opts into source coverage.

Only existing written-record metadata enters this selector. Provenance coverage
is not event/person identity, and observation chronology is not an event date.
The caller supplies the existing scope/relationship priority; diversification
never promotes a lower tier over a higher one. No role/query/history input exists.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Iterable


VERSION = "retention-observation-coverage-prototype-v1"
INFORMATION_VERSION = "retention-observation-coverage-prototype-v2-content-information"
_EXCLUDED = frozenset({"EVICTED", "SUPERSEDED", "DIAGNOSTIC_ONLY"})
_STATES = _EXCLUDED | {"ACTIVE", "CONFLICTED"}
# A fixed grammatical/request/discourse filter, not a domain or entity list.
# Negation, temporal words, numbers and arbitrary names deliberately remain.
_DISCOURSE = frozenset("""
i me my mine myself we us our ours ourselves you your yours yourself yourselves
he him his himself she her hers herself they them their theirs themselves it its itself
a an the and or but as at by for from in into of on onto to with through
is am are was were be been being have has had having do does did doing
can could may might must shall should will would ve ll re m s d t
this that these those which who whom whose what where how why
some any such much many more most very really quite so also too just
please thanks thank okay ok well yeah yes hey hello anyway
thing things something anything everything
want wants wanted wanting need needs needed needing
like likes liked liking love loves loved loving
hope hopes hoped hoping wish wishes wished wishing
think thinks thought thinking wonder wonders wondered wondering
curious interested interest interesting excited exciting
look looks looked looking seem seems seemed seeming
know knows knew knowing learn learns learned learning
hear hears heard hearing say says said saying tell tells told telling
ask asks asked asking help helps helped helping advice tips suggestions suggestion
recommend recommendations recommendation recommenders recommended recommending
great good nice amazing wonderful awesome helpful useful
""".split())


def _content_tokens(text: str) -> set[str]:
    # Codepoint words include digits and all scripts; no entity recognition.
    # Interior title-case/all-capital tokens are kept even if their spelling
    # overlaps a grammatical word. This preserves potential dates/names without
    # a list of particular people, places or benchmark entities.
    result = set()
    for index, word in enumerate(re.findall(r"[^\W_]+", text)):
        token = word.casefold()
        potential_identifier = (index > 0 and len(word) > 1
                                and (word.isupper() or word.istitle()))
        if token not in _DISCOURSE or potential_identifier:
            result.add(token)
    return result


@dataclass(frozen=True)
class RetentionCoverageCandidate:
    memory_id: str
    lifecycle_state: str
    retention_priority: int
    observed_at: str | None
    observed_order: float
    write_order: int
    source_message_ids: tuple[str, ...]
    canonical_value: str


@dataclass(frozen=True)
class RetentionCoverageDecision:
    version: str
    capacity: int
    retained_memory_ids: tuple[str, ...]
    evicted_memory_ids: tuple[str, ...]
    excluded_memory_ids: tuple[str, ...]
    protected_overflow: bool
    priority_counts: tuple[dict, ...]
    decisions: tuple[dict, ...]


def _group(item: RetentionCoverageCandidate) -> tuple:
    # Unknown provenance cannot make unrelated records one observation.
    sources = tuple(sorted(set(item.source_message_ids)))
    return (sources, item.observed_at, None if sources else item.memory_id)


def _group_id(item: RetentionCoverageCandidate) -> str:
    return hashlib.sha256(json.dumps(_group(item), ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _covers(container: RetentionCoverageCandidate, other: RetentionCoverageCandidate) -> bool:
    if _group(container) != _group(other):
        return False
    a, b = container.canonical_value, other.canonical_value
    return a == b or (len(b) >= 12 and b in a)


def _chronology(item: RetentionCoverageCandidate) -> tuple:
    return item.observed_order, item.write_order, item.memory_id


def _spread(groups: list[tuple], count: int) -> list[tuple]:
    """Deterministic quantiles of observation order, never inferred event time."""
    if count >= len(groups):
        return groups
    if count == 1:
        return [groups[(len(groups) - 1) // 2]]
    return [groups[i * (len(groups) - 1) // (count - 1)] for i in range(count)]


def select_retention_coverage(
    candidates: Iterable[RetentionCoverageCandidate], *, capacity: int,
    representative_policy: str = "recency",
) -> RetentionCoverageDecision:
    """Select within a fixed record cap, preserving priority and conflicts.

    This is a batch decision over *currently available* records. It never reads
    old evicted content back into the store. For counterfactual ingestion, invoke
    it before the original eviction on a newly written batch, not on a diagnostic
    union of historical evictions. A conflict overflow preserves the existing
    store's soft-limit behavior (all available records remain, with an explicit
    overflow flag); it does not silently raise the configured capacity.
    """
    if type(capacity) is not int or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    if representative_policy not in {"recency", "content_information"}:
        raise ValueError("unknown representative policy")
    items = list(candidates)
    seen: set[str] = set()
    for item in items:
        if (not isinstance(item, RetentionCoverageCandidate)
                or not isinstance(item.memory_id, str) or not item.memory_id
                or item.memory_id in seen or item.lifecycle_state not in _STATES
                or type(item.retention_priority) is not int or item.retention_priority < 0
                or not (item.observed_at is None or isinstance(item.observed_at, str))
                or type(item.observed_order) not in {int, float}
                or not math.isfinite(item.observed_order)
                or type(item.write_order) is not int or item.write_order < 0
                or not isinstance(item.source_message_ids, tuple)
                or any(not isinstance(s, str) or not s for s in item.source_message_ids)
                or not isinstance(item.canonical_value, str) or not item.canonical_value.strip()):
            raise ValueError("invalid or duplicate retention candidate")
        seen.add(item.memory_id)
    items.sort(key=_chronology)
    available = [item for item in items if item.lifecycle_state not in _EXCLUDED]
    information: dict[str, float] = {}
    if representative_policy == "content_information":
        documents = {item.memory_id: _content_tokens(item.canonical_value) for item in available}
        frequency = Counter(token for tokens in documents.values() for token in tokens)
        for memory_id, tokens in documents.items():
            information[memory_id] = sum(
                1 + math.log((len(documents) + 1) / (frequency[token] + 1))
                for token in sorted(tokens)
            )
    protected = [item for item in available if item.lifecycle_state == "CONFLICTED"]
    chosen = {item.memory_id for item in protected}
    reason = {item.memory_id: ("protected_conflict", 0) for item in protected}
    overflow = len(protected) > capacity
    if overflow or len(available) <= capacity:
        for item in available:
            chosen.add(item.memory_id)
            reason.setdefault(item.memory_id, ("conflict_soft_limit_preserved_all" if overflow else "room_available", 0))
    else:
        by_priority: dict[int, list[RetentionCoverageCandidate]] = defaultdict(list)
        for item in available:
            if item.memory_id not in chosen:
                by_priority[item.retention_priority].append(item)
        for priority in sorted(by_priority, reverse=True):
            tier = by_priority[priority]
            room = capacity - len(chosen)
            if room <= 0:
                break
            if len(tier) <= room:
                for item in tier:
                    chosen.add(item.memory_id)
                    reason[item.memory_id] = ("higher_priority_tier_fits", 0)
                continue
            groups: dict[tuple, list[RetentionCoverageCandidate]] = defaultdict(list)
            for item in tier:
                groups[_group(item)].append(item)
            all_selected = [item for item in available if item.memory_id in chosen]
            allocations = Counter(_group(item) for item in all_selected)
            round_number = 0
            while room > 0 and groups:
                round_number += 1
                lowest = min(allocations[group] for group in groups)
                eligible_groups = [group for group in groups if allocations[group] == lowest]
                eligible_groups.sort(key=lambda group: min(_chronology(item) for item in groups[group]))
                for group in _spread(eligible_groups, min(room, len(eligible_groups))):
                    options = groups[group]
                    def representativeness(item: RetentionCoverageCandidate) -> tuple:
                        novel = not any(_covers(old, item) for old in all_selected)
                        covered = sum(_covers(item, other) for other in options)
                        if representative_policy == "content_information":
                            return novel, covered, information[item.memory_id], -item.write_order, item.memory_id
                        return novel, covered, item.observed_order, item.write_order, item.memory_id
                    item = max(options, key=representativeness)
                    chosen.add(item.memory_id)
                    all_selected.append(item)
                    allocations[group] += 1
                    reason[item.memory_id] = ("observation_coverage_and_exact_text_nonredundancy", round_number)
                    options.remove(item)
                    if not options:
                        del groups[group]
                    room -= 1
            break  # A cut tier consumes all remaining room; lower tiers cannot override it.
    retained = [item for item in available if item.memory_id in chosen]
    decisions = []
    for item in items:
        excluded = item.lifecycle_state in _EXCLUDED
        covered_by = next((other.memory_id for other in retained
                           if other.memory_id != item.memory_id and _covers(other, item)), None)
        action = "already_unavailable" if excluded else "retain" if item.memory_id in chosen else "evict"
        why, selection_round = reason.get(item.memory_id, (
            "unavailable_state_not_revived" if excluded else "capacity_priority_or_coverage_cutoff", None))
        decisions.append({"memory_id": item.memory_id, "action": action, "reason": why,
                          "retention_priority": item.retention_priority, "observation_group_sha256": _group_id(item),
                          "source_message_ids": list(item.source_message_ids), "observed_at": item.observed_at,
                          "observation_chronology": item.observed_order, "write_order": item.write_order,
                          "selection_round": selection_round, "exact_text_covered_by_memory_id": covered_by,
                          "canonical_sha256": hashlib.sha256(item.canonical_value.encode()).hexdigest()})
        if representative_policy == "content_information":
            decisions[-1].update(representative_policy=representative_policy,
                                 content_information_score=information.get(item.memory_id),
                                 content_information_scope="available_written_batch_document_frequency")
    priorities = sorted({item.retention_priority for item in available}, reverse=True)
    return RetentionCoverageDecision(
        version=INFORMATION_VERSION if representative_policy == "content_information" else VERSION, capacity=capacity,
        retained_memory_ids=tuple(item.memory_id for item in retained),
        evicted_memory_ids=tuple(item.memory_id for item in available if item.memory_id not in chosen),
        excluded_memory_ids=tuple(item.memory_id for item in items if item.lifecycle_state in _EXCLUDED),
        protected_overflow=overflow,
        priority_counts=tuple({"retention_priority": priority,
                               "available": sum(item.retention_priority == priority for item in available),
                               "retained": sum(item.retention_priority == priority for item in retained)}
                              for priority in priorities),
        decisions=tuple(decisions),
    )
