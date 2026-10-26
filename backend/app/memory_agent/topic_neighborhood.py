"""Bounded topic-recall proposals from retained records, never factual links.

The caller owns strategy/profile eligibility and the existing final record and
character budgets. This helper cannot fetch history, revive records, write a
relationship, or assert that two passages describe the same person or event.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any

from app.memory_agent.retrieval_text import expand_pronoun_contractions


VERSION = "retained-content-topic-neighborhood-v1"
_WORDS = re.compile(r"[a-zA-Z]+(?:[-'][a-zA-Z]+)*")
# Discourse, request and provenance scaffolding must not create topic bridges.
# These are domain-independent words, not an ingredient/entity/answer lexicon.
_GENERIC = frozenset("""
a an the and or but if so as at by for from in into of on out to up with
i me my mine we us our ours you your yours he him his she her hers it its
they them their theirs this that these those there here who what where when
why how which any some all each other another both either neither
is am are was were be been being do does did have has had having
can could will would shall should may might must not no yes
im ive id ill youre youve dont doesnt didnt cant couldnt wont wouldnt
s t ve d ll m re
about also actually already always just only really very quite still even
more most much many few less little now then recently currently previously
first last next same different new old good great better best extra
like likes liked liking love loves loved enjoy enjoys enjoyed
try tries tried trying want wants wanted need needs needed
think thinks thought thinking feel feels felt feeling
say says said tell told ask asked know knows knew
found find finds get gets got getting make makes made making
use uses used using add adds added adding something anything everything
thing things type types way ways advice tip tips suggest suggests suggestion
suggestions recommend recommends recommendation recommendations help helpful
please thanks thank hello sure okay well let lets looking look looks
prior assistant conversation history untrusted verified standalone user fact
role content source message record context
over under above below before after during between across around near away
back down off through until within without onto upon beside beyond against
toward towards throughout small smaller smallest large larger largest big
bigger biggest short shorter shortest long longer longest high higher low
lower early earlier late later soon today yesterday tomorrow morning afternoon
evening night daily weekly monthly yearly day days week weeks month months
year years sound sounds interesting interested kind kinds sort sorts
particular particularly
""".split())


@dataclass(frozen=True)
class TopicNeighborhoodProposal:
    memory_id: str
    anchor_memory_id: str
    shared_terms: tuple[str, ...]
    shared_weight: float
    neighbor_content_coverage: float
    relevance: float
    context_score: float
    anchor_source_roles: tuple[str, ...]
    reason: str = "bounded_retained_content_topic_one_hop"
    validation_scope: str = "retrieval_hint_only_not_fact_or_identity"


def meaningful_topic_terms(text: str) -> frozenset[str]:
    """Retrieval-only surface terms; original content is never rewritten."""
    terms = set()
    for raw in _WORDS.findall(expand_pronoun_contractions(text).lower()):
        for word in (raw, *re.split(r"[-']", raw)):
            if len(word) < 3 or word in _GENERIC:
                continue
            normalized = (word[:-3] + "y" if len(word) > 4 and word.endswith("ies")
                          else word[:-1] if len(word) > 4 and word.endswith("s")
                          and not word.endswith(("ss", "us", "is")) else word)
            if normalized not in _GENERIC:
                terms.add(normalized)
    return frozenset(terms)


def _finite_positive(value: Any) -> float:
    return float(value) if (type(value) in (int, float)
                            and math.isfinite(value) and value > 0) else 0.0


def _active(item: dict) -> bool:
    record = item.get("record")
    state = getattr(record, "lifecycle_state", None)
    state = getattr(state, "value", state)
    return (item.get("eligible") is True and state == "ACTIVE"
            and isinstance(getattr(record, "id", None), str)
            and bool(record.id) and isinstance(getattr(record, "canonical_value", None), str))


def _stable_record_key(item: dict) -> tuple:
    """Stable provenance/content order; private generated IDs never break ties."""
    record = item["record"]
    order = getattr(record, "write_order", None)
    order = order if type(order) is int else 0
    observed = getattr(record, "observed_at", None)
    observed = observed.isoformat() if hasattr(observed, "isoformat") else (
        observed if isinstance(observed, str) else "")
    sources = getattr(record, "source_message_ids", ())
    sources = tuple(sorted(x for x in sources if isinstance(x, str))) if isinstance(
        sources, (list, tuple, set, frozenset)) else ()
    return (order, observed, sources,
            hashlib.sha256(record.canonical_value.encode("utf-8")).hexdigest())


def topic_neighborhood_proposals(
    candidates: list[dict], *, max_anchors: int = 8, max_neighbors: int = 8,
    min_shared_terms: int = 2, min_neighbor_coverage: float = 0.25,
    attenuation: float = 0.5,
) -> list[TopicNeighborhoodProposal]:
    """Return bounded proposals without mutating candidates or selecting context.

    Anchors must have original direct relevance AND meaningful query overlap.
    Same-message expansions are never new anchors. Links use only two or more
    shared content terms, weighted by retained-record document frequency; no
    source-session adjacency, dates, IDs or query-to-answer exceptions are used.
    Assistant records may locate user records, but remain untrusted topic hints.
    """
    if (type(max_anchors) is not int or type(max_neighbors) is not int
            or max_anchors < 0 or max_neighbors < 0
            or type(min_shared_terms) is not int or min_shared_terms < 2
            or type(min_neighbor_coverage) not in (int, float)
            or not math.isfinite(min_neighbor_coverage)
            or not 0 < min_neighbor_coverage <= 1
            or type(attenuation) not in (int, float) or not math.isfinite(attenuation)
            or not 0 < attenuation < 1):
        raise ValueError("Topic neighborhood limits must be finite, bounded and attenuated.")
    if not max_anchors or not max_neighbors:
        return []
    available = [item for item in candidates if _active(item)]
    ids = [item["record"].id for item in available]
    if len(set(ids)) != len(ids):
        raise ValueError("Topic neighborhood requires unique retained memory IDs.")
    stable_keys = {item["record"].id: _stable_record_key(item) for item in available}
    terms = {item["record"].id: meaningful_topic_terms(item["record"].canonical_value)
             for item in available}
    frequencies = Counter(term for values in terms.values() for term in values)
    weights = {term: 1 + math.log((len(available) + 1) / (count + 1))
               for term, count in frequencies.items()}
    anchors = []
    for item in available:
        direct = _finite_positive(item.get("direct_relevance"))
        query = item.get("_query_terms", ())
        if not isinstance(query, (set, frozenset, list, tuple)):
            continue
        query_terms = meaningful_topic_terms(" ".join(x for x in query if isinstance(x, str)))
        overlap = query_terms & terms[item["record"].id]
        if direct and overlap:
            score = sum(weights[x] for x in sorted(overlap))
            anchors.append((score, stable_keys[item["record"].id], item, direct))
    anchors.sort(key=lambda value: (-value[0], value[1]))
    # Freeze the original anchors before considering any proposed neighbor.
    anchors = anchors[:max_anchors]
    proposals = []
    for item in available:
        mid = item["record"].id
        if _finite_positive(item.get("direct_relevance")):
            continue  # This helper expands recall, not existing direct ranks.
        total = sum(weights[x] for x in sorted(terms[mid]))
        if not total:
            continue
        best = None
        for query_score, _, anchor, direct in anchors:
            anchor_id = anchor["record"].id
            shared = terms[mid] & terms[anchor_id]
            if len(shared) < min_shared_terms:
                continue
            shared_weight = sum(weights[x] for x in sorted(shared))
            coverage = shared_weight / total
            if coverage < min_neighbor_coverage:
                continue
            direct_score = _finite_positive(anchor.get("direct_context_score")) or query_score
            proposal = TopicNeighborhoodProposal(
                memory_id=mid, anchor_memory_id=anchor_id,
                shared_terms=tuple(sorted(shared)), shared_weight=shared_weight,
                neighbor_content_coverage=coverage, relevance=attenuation * direct,
                context_score=attenuation * direct_score * coverage,
                anchor_source_roles=tuple(sorted(anchor.get("source_roles", set()))),
            )
            if best is None or (-proposal.context_score, -proposal.shared_weight,
                                stable_keys[proposal.anchor_memory_id]) < (-best.context_score,
                                -best.shared_weight, stable_keys[best.anchor_memory_id]):
                best = proposal
        if best is not None:
            proposals.append(best)
    proposals.sort(key=lambda p: (-p.context_score, -p.shared_weight, stable_keys[p.memory_id]))
    return proposals[:max_neighbors]
