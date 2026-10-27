"""Private persistent memory lifecycle for a controlled target agent.

The auditor's ``memories`` table remains human-confirmed ground truth.  This
module instead models what a target agent would remember after seeing the
authorised conversation, so the target never receives reviewer-approved facts
as its memory store.  It provides a small deterministic baseline now and a
stable replacement seam for a future agent memory backend.
"""
from __future__ import annotations

import json
import math
from collections import Counter
import re
from app.services.location_facts import location_value
from app.services.memory_entities import named_projects
from app.services.memory_topics import is_language_topic
from app.services.meeting_facts import is_meeting_platform_topic
from app.services.fact_identity import FACT_TOKENS, fact_fingerprint
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.models import (
    TargetAgentMemoryEventModel,
    TargetAgentMemoryModel,
    TargetAgentMemoryRelationshipModel,
    TargetAgentRetrievalModel,
)
from app.schemas import (
    Conversation,
    MemoryRelationship,
    MemoryStrategy,
    RelationshipType,
    TargetAgentMemoryRecord,
    TargetMemoryEventType,
    TargetMemoryIngestionResult,
    TargetMemoryLifecycleState,
    TargetMemoryMaintenancePolicy,
    TargetMemoryRetrievalEvidence,
    TargetMemoryRetrievalResult,
    TargetMemoryScope,
    TargetMemoryWriteEvidence,
    TestCase,
)
from app.services.interfaces import MemoryExtractor, TargetMemoryStore
from app.schemas.target_profile import TargetMemoryProfile
from app.memory_agent.retrieval_agent import AgentMemoryRetriever
from app.memory_agent.temporal_context import temporal_question, query_window, temporal_references
from app.memory_agent.retrieval_text import retrieval_tokens, assistant_history_intent
from app.memory_agent.topic_neighborhood import topic_neighborhood_proposals
from app.memory_agent.retention_coverage import RetentionCoverageCandidate, select_retention_coverage


_WORDS = FACT_TOKENS
_STOP = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "what", "which",
    "should", "would", "about", "user", "memory", "remembered", "does", "use",
    "used", "using", "now", "current", "currently", "please", "tell", "me",
})
# Retrieval relevance must not arise merely from pronouns or question grammar.
# Keep these separate from the content signature used for conservative dedup.
_RETRIEVAL_STOP = frozenset({
    "i", "my", "we", "our", "you", "your", "it", "its", "s", "they", "their",
    "them", "he", "his", "she", "her", "a", "an", "of", "to", "in", "on",
    "at", "as", "by", "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "did", "how", "many", "much", "when", "where",
    "can", "could", "will", "would", "shall", "not", "just", "also", "so",
    "some", "any", "there", "then", "than", "since", "again", "new", "more",
})
_NEGATION_OR_CHANGE_CUES = frozenset({
    "not", "never", "without", "instead", "except", "former", "previous",
    "formerly", "before", "after", "until", "no", "different",
})
_UPDATE_HISTORY_QUESTION_CUES = re.compile(
    r"\b(?:before|previously|earlier|formerly|prior|original(?:ly)?|initial(?:ly)?|"
    r"histor(?:y|ical)|older|oldest|newer|final(?:\s+value)?|"
    r"conflict\w*|contradict\w*|differ\w*|compar(?:e|ed|ing|ison)|time[- ]ordered|"
    r"what\s+changed|change(?:d)?\s+from|how\s+(?:has|did)\b[^?!.]{0,80}\bchange(?:d)?)\b",
    re.IGNORECASE,
)


def _question_requests_update_history(question: str) -> bool:
    """Recognise explicit target-visible requests for earlier/update history."""
    return bool(_UPDATE_HISTORY_QUESTION_CUES.search(question))


def _ident(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:10].upper()}"


def infer_target_memory_scope(canonical_value: str) -> TargetMemoryScope:
    """Classify a private target-memory record without consulting ground truth.

    Scope is deliberately a small, deterministic label rather than an extra
    retrieval framework.  It lets experiments compare later scope-aware
    policies while preserving the same authorised source and stored values.
    A future target writer may replace this inference at this store boundary.
    """
    value = canonical_value.lower()
    if re.search(r"\b(?:assignment|project|task|requirement|requires|required|must|mandatory|for\s+this)\b", value):
        return TargetMemoryScope.PROJECT_REQUIREMENT
    if re.search(r"\b(?:prefer(?:s|red|ence)?|favour(?:s|ed|ite)?|favorite|favourite|(?:would|\'d)\s+rather)\b", value):
        return TargetMemoryScope.PREFERENCE
    if re.search(r"\bi\s+(?:(?:also|usually|generally|really|particularly)\s+)?(?:like|enjoy|love)\b", value):
        return TargetMemoryScope.PREFERENCE
    # Scope governs retention/retrieval priority, not truth or current-state certainty.
    # Keep ongoing background and explicit personal relationships from being
    # treated like disposable one-off conversation fragments. Preserve the
    # full source wording, including plans, dates and uncertainty.
    if re.search(r"\b(?:i|we)(?:['’](?:ve|m|re)|\s+(?:have|am|are))\s+(?:been\s+)?"
                 r"(?:work(?:ing|ed)?|liv(?:e|ing|ed)|stud(?:y|ying|ied))\b", value):
        return TargetMemoryScope.PROFILE
    if re.search(r"\bmy\s+(?:sister|brother|mother|father|daughter|son|partner|spouse|wife|husband)\b", value):
        return TargetMemoryScope.PROFILE
    if location_value(value) or re.search(r"\b(?:i\s+am|my\s+name|based\s+in|live\s+in|located\s+in|(?:moved|relocated)\s+to|work\s+as|(?:my|the)\s+backend|i\s+(?:now\s+)?use)\b", value):
        return TargetMemoryScope.PROFILE
    return TargetMemoryScope.EPISODIC


def _reference_ranges(reference: dict) -> list[tuple[str, str]]:
    """Keep disjoint calendar candidates disjoint during retrieval scoring."""
    candidates = reference.get("candidate_ranges")
    if reference.get("range_kind") == "candidate_envelope" and isinstance(candidates, list):
        return [(item["resolved_start"], item["resolved_end"]) for item in candidates
                if isinstance(item, dict) and isinstance(item.get("resolved_start"), str)
                and isinstance(item.get("resolved_end"), str)]
    return [(reference["resolved_start"], reference["resolved_end"])]


class SqlTargetMemoryStore(TargetMemoryStore):
    """SQLAlchemy implementation of one target memory store per audit run.

    ``ingest`` is idempotent: retries use the previously written state rather
    than changing the target's observed history.  ``retrieve`` is intentionally
    append-only, keeping every retrieval decision available for review while
    keeping it off public test endpoints.
    """

    def __init__(
        self,
        db: Session,
        extractor: MemoryExtractor | None = None,
        maintenance_policy: TargetMemoryMaintenancePolicy | str = TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION,
        capacity: int | None = 50,
        *,
        max_active_records: int | None = None,
        profile: TargetMemoryProfile | None = None,
        retrieval_agent: AgentMemoryRetriever | None = None,
    ):
        """Create a deterministic private memory store.

        ``capacity`` is the frozen, persisted audit setting. ``None`` remains
        available to direct callers that need an unlimited baseline. The
        keyword-only ``max_active_records`` is a backwards-compatible alias
        for older experimental callers. A positive limit is soft when
        unresolved conflicts alone exceed it, because silently dropping one
        side of a conflict would invalidate the condition being measured.
        """
        if max_active_records is not None and capacity != 50 and capacity != max_active_records:
            raise ValueError("Specify either capacity or max_active_records, not conflicting values.")
        resolved_capacity = max_active_records if max_active_records is not None else capacity
        if resolved_capacity is not None and resolved_capacity < 1:
            raise ValueError("capacity must be a positive integer or None.")
        self.profile = profile or TargetMemoryProfile()
        self.db = db
        self.extractor = extractor or RuleBasedMemoryExtractor()
        self.writer_version = getattr(self.extractor, "VERSION", self.extractor.__class__.__name__)
        self.maintenance_policy = TargetMemoryMaintenancePolicy(maintenance_policy)
        self.max_active_records = resolved_capacity
        self.retrieval_agent = retrieval_agent
        self._last_retrieval_agent_execution_id: str | None = None
        self._last_agent_execution_id: str | None = None

    def ingest(self, run_id: str, conversation: Conversation) -> TargetMemoryIngestionResult:
        if not conversation.authorised:
            raise ValueError("The target agent may only ingest an authorised conversation.")

        existing = self._records(run_id)
        if existing:
            return TargetMemoryIngestionResult(
                run_id=run_id,
                records=[self._record_schema(item) for item in existing],
                write_evidence=[self._event_schema(item) for item in self._write_events(run_id)],
            )

        try:
            extracted = self.extractor.extract(conversation)
        except Exception:
            self._record_target_memory_writer_stage(run_id, conversation.conversation_id)
            raise
        self._record_target_memory_writer_stage(run_id, conversation.conversation_id)
        extracted_ids: dict[str, TargetAgentMemoryModel] = {}
        # Update-aware consolidation removes exact duplicate writes and a
        # deliberately narrow class of near duplicates.  It does not use a
        # semantic model: a merge requires the same content-token signature,
        # no change/negation cue, and no lifecycle relationship on either
        # candidate.  That makes every merge reproducible and inspectable.
        deduplicated: dict[str, TargetAgentMemoryModel] = {}
        deduplicated_signatures: dict[frozenset[str], TargetAgentMemoryModel] = {}
        now = datetime.now(timezone.utc)
        self._event(
            run_id, None, TargetMemoryEventType.INGESTED,
            details={
                "conversation_id": conversation.conversation_id,
                "message_count": len(conversation.messages),
                "writer_version": self.writer_version,
                "maintenance_policy": self.maintenance_policy.value,
                "target_memory_capacity": self.max_active_records,
            },
            created_at=now,
        )
        for position, candidate in enumerate(extracted, start=1):
            fingerprint = _canonical_fingerprint(candidate.canonical_value)
            retained = deduplicated.get(fingerprint)
            signature = _near_duplicate_signature(candidate.canonical_value)
            merge_action = "merged_exact_duplicate"
            if (
                retained is None
                and signature
                and not candidate.relationships
                and _is_conservative_near_duplicate(candidate.canonical_value)
            ):
                possible = deduplicated_signatures.get(signature)
                if possible is not None and not self._has_relationship(possible.id):
                    retained = possible
                    merge_action = "merged_conservative_near_duplicate"
            if (
                retained is not None
                and self.maintenance_policy == TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION
            ):
                retained.source_message_ids = list(dict.fromkeys(
                    [*retained.source_message_ids, *candidate.source_message_ids]
                ))
                extracted_ids[candidate.memory_id] = retained
                self._event(
                    run_id, retained.id, TargetMemoryEventType.MAINTENANCE_APPLIED,
                    source_message_ids=list(candidate.source_message_ids),
                    details={
                        "duplicate_of_memory_id": retained.id,
                        "maintenance_policy": self.maintenance_policy.value,
                        "maintenance_action": merge_action,
                        "canonical_fingerprint": fingerprint,
                        "content_signature": sorted(signature),
                    },
                )
                continue
            source_roles = {message.role.strip().lower() for message in conversation.messages
                            if message.message_id in candidate.source_message_ids}
            scope = (TargetMemoryScope.EPISODIC if source_roles == {"assistant"}
                     else infer_target_memory_scope(candidate.canonical_value))
            record = TargetAgentMemoryModel(
                id=_ident("TM"), run_id=run_id,
                source_conversation_id=conversation.conversation_id,
                canonical_value=candidate.canonical_value,
                scope=scope.value,
                lifecycle_state=TargetMemoryLifecycleState.ACTIVE.value,
                source_message_ids=list(candidate.source_message_ids),
                observed_at=candidate.timestamp, write_order=position,
            )
            self.db.add(record)
            # Event rows carry a database foreign key to the private memory
            # row. SQLite test defaults do not enforce it, whereas PostgreSQL
            # does; flush the record before recording its evidence event.
            self.db.flush()
            extracted_ids[candidate.memory_id] = record
            deduplicated[fingerprint] = record
            if signature and not candidate.relationships:
                deduplicated_signatures.setdefault(signature, record)
            self._event(
                run_id, record.id, TargetMemoryEventType.WRITTEN,
                source_message_ids=list(candidate.source_message_ids),
                details={"write_order": position, "canonical_value": candidate.canonical_value, "scope": scope.value},
            )

        # IDs are generated client-side, so references can be written before a
        # flush.  The relationship direction is the same as ground truth:
        # current/new record -> related earlier record.
        for candidate in extracted:
            record = extracted_ids[candidate.memory_id]
            for relation in candidate.relationships:
                target = extracted_ids.get(relation.target_memory_id)
                # A duplicate can inherit a source ID, but must never create a
                # meaningless self-relationship in the retained private store.
                if not target or target.id == record.id:
                    continue
                self.db.add(TargetAgentMemoryRelationshipModel(
                    id=_ident("TMR"), run_id=run_id, memory_id=record.id,
                    relationship_type=relation.type.value, target_memory_id=target.id,
                ))
                if relation.type == RelationshipType.UPDATE:
                    if self.maintenance_policy == TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION:
                        target.lifecycle_state = TargetMemoryLifecycleState.SUPERSEDED.value
                        self._event(
                            run_id, record.id, TargetMemoryEventType.UPDATED,
                            source_message_ids=list(record.source_message_ids),
                            details={
                                "supersedes_memory_id": target.id,
                                "maintenance_policy": self.maintenance_policy.value,
                                "maintenance_action": "supersede_prior_record",
                            },
                        )
                    else:
                        # The append-only baseline retains old and new records
                        # as active observations.  It records the link but does
                        # not reconcile lifecycle state during ingestion.
                        self._event(
                            run_id, record.id, TargetMemoryEventType.MAINTENANCE_APPLIED,
                            source_message_ids=list(record.source_message_ids),
                            details={
                                "supersedes_memory_id": target.id,
                                "maintenance_policy": self.maintenance_policy.value,
                                "maintenance_action": "retained_prior_record",
                            },
                        )
                elif relation.type == RelationshipType.CONTEXTUAL_OVERRIDE:
                    self._event(
                        run_id, record.id, TargetMemoryEventType.CONTEXTUAL_OVERRIDE_RECORDED,
                        source_message_ids=list(record.source_message_ids),
                        details={"overrides_memory_id": target.id},
                    )
                elif relation.type == RelationshipType.CONFLICT:
                    # Preserve both facts.  A strong target is expected to
                    # identify unresolved conflict rather than discard either.
                    record.lifecycle_state = TargetMemoryLifecycleState.CONFLICTED.value
                    target.lifecycle_state = TargetMemoryLifecycleState.CONFLICTED.value
                    self._event(
                        run_id, record.id, TargetMemoryEventType.CONFLICT_RECORDED,
                        source_message_ids=list(record.source_message_ids),
                        details={"conflicts_with_memory_id": target.id},
                    )

        self.db.flush()
        self._apply_capacity_limit(run_id)
        self.db.flush()
        return TargetMemoryIngestionResult(
            run_id=run_id,
            records=[self._record_schema(item) for item in self._records(run_id)],
            write_evidence=[self._event_schema(item) for item in self._write_events(run_id)],
        )

    def retrieve(
        self, run_id: str, conversation: Conversation, test: TestCase,
        strategy: MemoryStrategy, *, retrieval_mode: str = "fixed",
    ) -> TargetMemoryRetrievalResult:
        self.ingest(run_id, conversation)
        records = self._records(run_id)
        relations = self._relationships(run_id)
        relation_by_memory: dict[str, list[TargetAgentMemoryRelationshipModel]] = {}
        for relation in relations:
            relation_by_memory.setdefault(relation.memory_id, []).append(relation)

        evicted_ids = self._evicted_memory_ids(run_id)
        candidates = [
            self._candidate(record, test, relation_by_memory.get(record.id, []))
            for record in records
        ]
        self._annotate_relative_chronology(candidates, conversation)
        if retrieval_mode == "agent":
            return self._retrieve_with_agent(
                run_id, test, strategy, candidates, relations, evicted_ids,
            )
        self._mark_retrieval_eligibility(candidates, strategy, evicted_ids)
        self._include_update_history_for_question_context(candidates, relations, test.prompt, strategy)
        if self.profile.retrieve_message_context and strategy not in {
            MemoryStrategy.NO_MEMORY, MemoryStrategy.WEAK_FIRST_HIT, MemoryStrategy.FULL_CONTEXT,
        }:
            self._annotate_lexical_strength(candidates)
            self._include_message_context(candidates)
            if temporal_question(test.prompt):
                self._include_temporal_neighborhood(candidates, test.prompt)
            else:
                self._include_topic_neighborhood(candidates)
        preferred_scope, _ = _preferred_scope(test.prompt)
        eligible: list[dict] = []
        for item in candidates:
            if strategy == MemoryStrategy.NO_MEMORY:
                # Keep the candidate evidence for diagnostics, but expose no
                # private memory to the target model.
                continue
            if strategy == MemoryStrategy.FULL_CONTEXT:
                if item["eligible"]:
                    eligible.append(item)
                continue
            scope_intent_fallback = (
                strategy == MemoryStrategy.SCOPE_AWARE
                and preferred_scope is not None
                and TargetMemoryScope(item["record"].scope) == preferred_scope
            )
            if item["eligible"] and (item["relevance"] > 0 or scope_intent_fallback):
                if scope_intent_fallback and item["relevance"] == 0:
                    item["reason"] = f"{item['reason']}, scope_intent_fallback"
                eligible.append(item)
        eligible = self._filter_profile_candidates(eligible, test)
        selected = self._apply_profile(self._select(eligible, strategy), test, strategy)
        selected_ids = {choice["record"].id for choice in selected}
        evidence_rows = [
            {
                "memory_id": item["record"].id,
                "relevance": item["relevance"],
                "temporal_window_match": item.get("temporal_window_match", False),
                "context_score": item.get("context_score"),
                "topic_neighborhood": item.get("topic_neighborhood"),
                "policy_score": item["policy_score"],
                "lifecycle_state": item["record"].lifecycle_state,
                "scope": item["record"].scope,
                "relationship_types": item["relationship_types"],
                # These are populated for every policy to make an experiment
                # able to compare the same source chronology.  The temporal
                # condition alone uses them to rank candidates.
                "relative_chronology": item["relative_chronology"],
                "chronology_basis": item["chronology_basis"],
                "recency_factor": item["recency_factor"],
                "importance_factor": item.get("importance_factor"),
                "importance_components": item.get("importance_components", []),
                "temporal_importance_score": item.get("temporal_importance_score"),
                "selected": item["record"].id in selected_ids,
                "eligible": item["eligible"],
                "reason": item["reason"],
            }
            for item in candidates
        ]
        retrieval = TargetAgentRetrievalModel(
            id=_ident("TR"), run_id=run_id, test_id=test.test_id,
            strategy=strategy.value,
            selected_memory_ids=[item["record"].id for item in selected],
            ranking_evidence=evidence_rows,
        )
        self.db.add(retrieval)
        self._event(
            run_id, None, TargetMemoryEventType.RETRIEVED,
            details={"test_id": test.test_id, "strategy": strategy.value,
                     "selected_memory_ids": retrieval.selected_memory_ids,
                     "maintenance_policy": self.maintenance_policy.value,
                     "max_active_records": self.max_active_records},
        )
        self.db.flush()
        return TargetMemoryRetrievalResult(
            context=[self._render_context(item) for item in selected],
            evidence=TargetMemoryRetrievalEvidence(
                retrieval_id=retrieval.id, run_id=run_id, test_id=test.test_id,
                strategy=strategy, selected_memory_ids=list(retrieval.selected_memory_ids),
                ranking_evidence=evidence_rows, final_response_id=None, created_at=retrieval.created_at,
            ),
        )

    def _retrieve_with_agent(
        self, run_id: str, test: TestCase, strategy: MemoryStrategy,
        candidates: list[dict], relations: list[TargetAgentMemoryRelationshipModel],
        evicted_ids: set[str],
    ) -> TargetMemoryRetrievalResult:
        """Ask the configured selector; retain all selection evidence privately."""
        if self.retrieval_agent is None:
            from app.extraction.llm import PipelineRequestError
            raise PipelineRequestError("The memory retrieval Agent is not configured for this audit.", 500)

        relation_context: dict[str, list[str]] = {}
        for relation in relations:
            relation_context.setdefault(relation.memory_id, []).append(
                f"{relation.relationship_type}:supersedes_or_links_to:{relation.target_memory_id}"
            )
            relation_context.setdefault(relation.target_memory_id, []).append(
                f"{relation.relationship_type}:linked_from:{relation.memory_id}"
            )

        requested_projects = named_projects(test.prompt)
        available: list[dict] = []
        for item in candidates:
            record = item["record"]
            if (record.id in evicted_ids or record.lifecycle_state in {
                TargetMemoryLifecycleState.EVICTED.value,
                TargetMemoryLifecycleState.DIAGNOSTIC_ONLY.value,
            }):
                item["agent_exclusion"] = "not_available_in_target_memory_store"
                continue
            projects = named_projects(record.canonical_value)
            if (self.profile.isolate_project_scope and requested_projects and projects
                    and not requested_projects.intersection(projects)):
                item["agent_exclusion"] = "excluded_by_project_isolation"
                continue
            item["agent_exclusion"] = None
            item["agent_included"] = False
            item["agent_reason"] = "Not selected by the retrieval Agent."
            available.append(item)

        # Every available target record must reach an Agent decision. If the
        # store is too large for one request (especially with a local model's
        # context window), ask the Agent to narrow chronological batches, then
        # ask it to compare the retained candidates. No lexical prefilter can
        # silently exclude a paraphrase before the Agent sees it.
        max_batch_records = 40
        max_batch_characters = 10_000
        encoded_by_id: dict[str, dict[str, str | list[str]]] = {}
        for item in available:
            record = item["record"]
            encoded_by_id[record.id] = {
                "id": record.id,
                "memory": record.canonical_value,
                "scope": record.scope,
                "state": record.lifecycle_state,
                # A large relationship fan-in should not crowd out memory text.
                "relationships": relation_context.get(record.id, [])[:12],
            }
            item["agent_included"] = False
            item["agent_selected_intermediate"] = False
            item["agent_final_input"] = False
            item["agent_reason"] = "Not selected by the retrieval Agent."
        available.sort(key=lambda item: item["record"].write_order)

        def make_batches(items: list[dict]) -> list[list[dict]]:
            batches: list[list[dict]] = []
            batch: list[dict] = []
            batch_size = 2  # JSON array brackets plus a small separator margin.
            for candidate in items:
                encoded = encoded_by_id[candidate["record"].id]
                size = len(json.dumps(encoded, ensure_ascii=False, separators=(",", ":"))) + 1
                if batch and (len(batch) >= max_batch_records or batch_size + size > max_batch_characters):
                    batches.append(batch)
                    batch = []
                    batch_size = 2
                batch.append(candidate)
                batch_size += size
            if batch:
                batches.append(batch)
            return batches or [[]]

        receipts: list[dict] = []
        sent_ids: set[str] = set()
        hierarchy_rounds = 0
        current = available
        while True:
            batches = make_batches(current)
            if len(batches) == 1:
                final_items = batches[0]
                for item in final_items:
                    item["agent_included"] = True
                    item["agent_final_input"] = True
                    sent_ids.add(item["record"].id)
                if final_items:
                    try:
                        choices = self.retrieval_agent.select(
                            question=test.prompt,
                            candidates=[encoded_by_id[item["record"].id] for item in final_items],
                            max_records=self.profile.max_retrieved_records,
                            context_character_budget=self.profile.context_character_budget,
                            isolate_project_scope=self.profile.isolate_project_scope,
                            prefer_current_state=self.profile.prefer_current_state,
                        )
                    except Exception:
                        self._record_retrieval_agent_stage(run_id, test.test_id)
                        raise
                    self._record_retrieval_agent_stage(run_id, test.test_id)
                    if self.retrieval_agent.last_execution:
                        receipts.append(self.retrieval_agent.last_execution)
                else:
                    choices = {"selected": [], "selection_summary": "No eligible target memories were available."}
                break

            hierarchy_rounds += 1
            next_items: list[dict] = []
            for batch in batches:
                for item in batch:
                    item["agent_included"] = True
                    sent_ids.add(item["record"].id)
                # A pass keeps up to half of each group, so every round makes
                # progress even when memory text alone exceeds the input cap.
                intermediate_limit = max(1, (len(batch) + 1) // 2)
                try:
                    result = self.retrieval_agent.select(
                        question=test.prompt,
                        candidates=[encoded_by_id[item["record"].id] for item in batch],
                        max_records=intermediate_limit,
                        context_character_budget=max_batch_characters,
                        isolate_project_scope=self.profile.isolate_project_scope,
                        prefer_current_state=self.profile.prefer_current_state,
                    )
                except Exception:
                    self._record_retrieval_agent_stage(run_id, test.test_id)
                    raise
                self._record_retrieval_agent_stage(run_id, test.test_id)
                if self.retrieval_agent.last_execution:
                    receipts.append(self.retrieval_agent.last_execution)
                group_by_id = {item["record"].id: item for item in batch}
                chosen_ids = {choice["memory_id"] for choice in result["selected"]}
                reasons = {choice["memory_id"]: choice["reason"] for choice in result["selected"]}
                for item in batch:
                    memory_id = item["record"].id
                    if memory_id in chosen_ids:
                        item["agent_selected_intermediate"] = True
                        item["agent_reason"] = reasons[memory_id]
                        next_items.append(group_by_id[memory_id])
                    else:
                        item["agent_reason"] = "Not selected by the retrieval Agent during an intermediate candidate review."
            if len(next_items) >= len(current):
                from app.extraction.llm import PipelineRequestError
                raise PipelineRequestError(
                    "The memory retrieval Agent could not reduce this store to a request-sized candidate set. "
                    "Try a model with a larger context window or a smaller target memory store."
                )
            current = next_items

        by_id = {item["record"].id: item for item in candidates}
        selected: list[dict] = []
        selected_reasons: dict[str, str] = {}
        characters = 0
        for choice in choices["selected"]:
            item = by_id[choice["memory_id"]]
            cost = len(self._render_context(item)) + 3
            if len(selected) >= self.profile.max_retrieved_records:
                item["agent_reason"] = "Selected by the Agent but excluded by the record-count limit."
                continue
            if characters + cost > self.profile.context_character_budget:
                item["agent_reason"] = "Selected by the Agent but excluded by the context-size limit."
                continue
            selected.append(item)
            selected_reasons[item["record"].id] = choice["reason"]
            item["agent_reason"] = choice["reason"]
            characters += cost

        selected_ids = {item["record"].id for item in selected}
        evidence_rows = []
        for item in candidates:
            record = item["record"]
            excluded = item.get("agent_exclusion")
            if excluded:
                reason = excluded
            elif record.id in selected_ids:
                reason = selected_reasons[record.id]
            elif item.get("agent_final_input"):
                reason = "Not selected in the final retrieval Agent comparison."
            elif item.get("agent_selected_intermediate"):
                reason = "Selected in an earlier Agent review, then omitted in a later comparison."
            elif item.get("agent_included"):
                reason = item.get("agent_reason") or "Not selected by the retrieval Agent during candidate review."
            else:
                reason = "Candidate was not available to the retrieval Agent."
            evidence_rows.append({
                "memory_id": record.id,
                "scope": record.scope,
                "lifecycle_state": record.lifecycle_state,
                "relationship_types": item["relationship_types"],
                "candidate_sent_to_agent": bool(item.get("agent_included")),
                "selected": record.id in selected_ids,
                "eligible": not bool(excluded),
                "reason": reason,
            })

        retrieval = TargetAgentRetrievalModel(
            id=_ident("TR"), run_id=run_id, test_id=test.test_id,
            strategy=strategy.value,
            selected_memory_ids=[item["record"].id for item in selected],
            ranking_evidence=evidence_rows,
        )
        self.db.add(retrieval)
        def total_receipt_value(key: str) -> int | float | None:
            values = [row.get(key) for row in receipts]
            numeric = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            return sum(numeric) if numeric else None

        self._event(
            run_id, None, TargetMemoryEventType.RETRIEVED,
            details={
                "test_id": test.test_id,
                "retrieval_mode": "agent",
                "retrieval_agent_version": AgentMemoryRetriever.VERSION,
                "retrieval_provider": self.retrieval_agent.provider,
                "retrieval_model": self.retrieval_agent.model,
                "selected_memory_ids": retrieval.selected_memory_ids,
                "candidate_count": len(candidates),
                "candidate_count_sent": len(sent_ids),
                "candidate_input_limit": max_batch_characters,
                "hierarchy_rounds": hierarchy_rounds,
                "model_calls": len(receipts),
                "selection_summary": choices["selection_summary"],
                "request_attempts": total_receipt_value("request_attempts"),
                "elapsed_ms": total_receipt_value("elapsed_ms"),
                "reported_input_tokens": total_receipt_value("reported_input_tokens"),
                "reported_output_tokens": total_receipt_value("reported_output_tokens"),
            },
        )
        self.db.flush()
        return TargetMemoryRetrievalResult(
            context=[self._render_context(item) for item in selected],
            evidence=TargetMemoryRetrievalEvidence(
                retrieval_id=retrieval.id, run_id=run_id, test_id=test.test_id,
                strategy=strategy, selected_memory_ids=list(retrieval.selected_memory_ids),
                ranking_evidence=evidence_rows, final_response_id=None, created_at=retrieval.created_at,
            ),
        )

    def _record_retrieval_agent_stage(self, run_id: str, test_id: str) -> None:
        stage = getattr(self.retrieval_agent, "last_observation", None)
        if not isinstance(stage, dict):
            return
        from app.services.agent_trace import record_agent_execution
        refs = dict(stage.get("input_refs") or {})
        refs["test_id"] = test_id
        receipt = stage.get("execution") or {}
        row = record_agent_execution(
            self.db,
            role="target_memory_retrieval",
            provider=stage.get("provider") or self.retrieval_agent.provider,
            model=stage.get("model") or self.retrieval_agent.model,
            prompt_template_version=stage.get("prompt_template_version") or AgentMemoryRetriever.VERSION,
            instructions=stage.get("instructions") or "",
            prompt=stage.get("prompt") or "",
            schema=stage.get("schema"),
            input_payload=stage.get("input_payload") or {},
            input_refs=refs,
            output_data=stage.get("output_data"),
            status=stage.get("status") or "failed",
            execution=receipt,
            error_code=stage.get("error_code"),
            error_summary=stage.get("error_summary"),
            run_id=run_id,
            handoff_from=self._last_agent_execution_id,
        )
        if self._last_agent_execution_id:
            from app.models import AgentExecutionModel
            previous = self.db.get(AgentExecutionModel, self._last_agent_execution_id)
            if previous:
                previous.handoff_to = row.id
        self._last_retrieval_agent_execution_id = row.id
        self._last_agent_execution_id = row.id

    def _record_target_memory_writer_stage(self, run_id: str, conversation_id: str) -> None:
        stage = getattr(self.extractor, "last_observation", None)
        if not isinstance(stage, dict):
            return
        from app.models import AgentExecutionModel
        from app.services.agent_trace import record_agent_execution
        latest = self.db.scalar(select(AgentExecutionModel).where(
            AgentExecutionModel.run_id == run_id,
        ).order_by(AgentExecutionModel.created_at.desc(), AgentExecutionModel.id.desc()).limit(1))
        row = record_agent_execution(
            self.db,
            role="target_memory_writing",
            provider=stage.get("provider") or getattr(self.extractor, "provider", "unknown"),
            model=stage.get("model") or getattr(self.extractor, "model", "unknown"),
            prompt_template_version=stage.get("prompt_template_version") or self.writer_version,
            instructions=stage.get("instructions") or "",
            prompt=stage.get("prompt") or "",
            schema=stage.get("schema"),
            input_payload=stage.get("input_payload") or {},
            input_refs={**(stage.get("input_refs") or {}), "conversation_id": conversation_id},
            output_data=stage.get("output_data"),
            status=stage.get("status") or "failed",
            execution=stage.get("execution"),
            error_code=stage.get("error_code"),
            error_summary=stage.get("error_summary"),
            conversation_id=conversation_id,
            run_id=run_id,
            handoff_from=latest.id if latest else None,
        )
        if latest:
            latest.handoff_to = row.id
        self._last_agent_execution_id = row.id

    def _filter_profile_candidates(self, candidates: list[dict], test: TestCase) -> list[dict]:
        requested = named_projects(test.prompt)
        retained = []
        historical = bool(re.search(r"\b(?:previous|previously|before|formerly|historical|past|earlier|used to)\b", test.prompt, re.I))
        for item in candidates:
            projects = named_projects(item["record"].canonical_value)
            if self.profile.isolate_project_scope and requested and projects and not requested.intersection(projects):
                item["reason"] += ", profile_excluded_other_project"
                continue
            if self.profile.prefer_current_state and not historical and item["record"].lifecycle_state == "SUPERSEDED":
                item["reason"] += ", profile_excluded_superseded_current_query"
                continue
            retained.append(item)
        return retained

    def _apply_profile(self, selected: list[dict], test: TestCase, strategy: MemoryStrategy) -> list[dict]:
        """Apply only target-side budget, never auditor support IDs or answers."""
        retained = selected
        # Ranking policies order from low to high priority. Keep the strongest
        # records without reversing the supplied chronology/order.
        priority = retained if strategy in {MemoryStrategy.FULL_CONTEXT, MemoryStrategy.WEAK_FIRST_HIT} else list(reversed(retained))
        source_coverage = self.profile.retrieve_message_context and strategy == MemoryStrategy.STRONG_RULE_BASED
        if source_coverage:
            priority = self._source_coverage_priority(priority, test)
        # Preserve explicit target-owned conflict pairs as atomic budget units.
        # Delivering just one side can imply a resolved constraint. Do not
        # exceed either budget when a pair cannot fit; preserve an evidence gap.
        peers = {item["record"].id: item for item in retained}
        conflict_peers: dict[str, set[str]] = {}
        if strategy == MemoryStrategy.STRONG_RULE_BASED:
            for item in retained:
                for target in item.get("conflict_targets", []):
                    if target in peers:
                        conflict_peers.setdefault(item["record"].id, set()).add(target)
                        conflict_peers.setdefault(target, set()).add(item["record"].id)
        chosen = set()
        chosen_items: list[dict] = []
        characters = 0
        considered: set[str] = set()
        for item in priority:
            identity = item["record"].id
            if identity in considered:
                continue
            group_ids = {identity}
            pending = [identity]
            while pending:
                for peer in conflict_peers.get(pending.pop(), set()) - group_ids:
                    group_ids.add(peer)
                    pending.append(peer)
            if len(group_ids) > 1:
                group = [other for other in priority if other["record"].id in group_ids]
                considered.update(group_ids)
                cost = sum(len(self._render_context(other)) + 3 for other in group)
                if (len(chosen) + len(group_ids) > self.profile.max_retrieved_records
                    or characters + cost > self.profile.context_character_budget):
                    for other in group:
                        other["reason"] += ", profile_conflict_group_budget_excluded"
                    continue
                chosen.update(group_ids)
                chosen_items.extend(group)
                characters += cost
                for other in group:
                    other["reason"] += ", profile_complete_conflict_group"
                continue
            if source_coverage and any(self._source_text_covers(other, item) for other in chosen_items):
                item["reason"] += ", profile_text_covered_by_selected_source_record"
                continue
            cost = len(self._render_context(item)) + 3
            if len(chosen) >= self.profile.max_retrieved_records or characters + cost > self.profile.context_character_budget:
                item["reason"] += ", profile_context_budget_excluded"
                item["reason"] += (", profile_record_limit_excluded" if len(chosen) >= self.profile.max_retrieved_records
                                   else ", profile_character_limit_excluded")
                continue
            chosen.add(item["record"].id)
            chosen_items.append(item)
            characters += cost
        result = [item for item in retained if item["record"].id in chosen]
        if self.profile.retrieve_message_context:
            result.sort(key=lambda item: (self._time_value(item["record"]), item["record"].write_order))
        return result

    @staticmethod
    def _source_group_key(item: dict) -> tuple:
        """A delivery provenance group, never an entity or event equivalence."""
        record = item["record"]
        sources = tuple(record.source_message_ids)
        return (sources, record.observed_at) if sources else ((), record.id)

    @classmethod
    def _source_text_covers(cls, container: dict, item: dict) -> bool:
        """Skip only text already delivered from the exact same observation.

        A longer quoted context can carry a retained fact and its antecedent.
        This does not consolidate store records or infer a relationship. Facts
        with relationship evidence remain independently selectable.
        """
        if (container is item or cls._source_group_key(container) != cls._source_group_key(item)
                or item.get("relationship_types")):
            return False
        value = " ".join(item["record"].canonical_value.split()).casefold().rstrip(". ")
        text = " ".join(container["record"].canonical_value.split()).casefold()
        return len(value) >= 12 and value in text and len(text) > len(value) + 1

    def _source_coverage_priority(self, priority: list[dict], test: TestCase) -> list[dict]:
        """Pack query evidence across observations before repeated fragments.

        Density remains a tie-breaker, not a reason to fill the entire context
        with short plans and neighboring fragments. Provenance coverage does
        not estimate an event count: multiple noncontained facts from one
        source remain candidates in later rounds. No original messages,
        reviewer IDs, expected answers or inferred identity groups are read.
        """
        question = re.split(r"\nQuestion date:", getattr(test, "prompt", ""), flags=re.I)[0]
        prospective_query = bool(re.search(
            r"\b(?:plan\w*|intend\w*|future|want\w*|hope\w*|wish\w*|will|would|should|"
            r"recommend\w*|suggest\w*)\b|\bgoing\s+to\b", question, re.I))
        prospective_opening = re.compile(
            r"^(?:(?:by the way|for [^,.]{1,80}),?\s*)?"
            r"(?:i(?:['’]m| am)\s+(?:planning|hoping|going to)|"
            r"i\s+(?:want|wish|hope|intend|plan|would|think\s+i(?:['’]ll| will| should)|"
            r"would\s+like)|i['’]d\s+like)\b", re.I)
        personal_query = bool(re.search(r"\b(?:I|my|me|we|our)\b", question, re.I))
        assistant_recall = assistant_history_intent(question)
        buckets: dict[tuple, dict[tuple, list[tuple[int, dict]]]] = {}
        for position, item in enumerate(priority):
            prospective = not prospective_query and bool(prospective_opening.search(item["record"].canonical_value))
            direct = item.get("direct_relevance", item.get("relevance", 0)) > 0
            support = (3 if direct else 2) if not prospective else (1 if direct else 0)
            roles = item.get("source_roles", set())
            # Long assistant suggestions must not crowd direct user facts out
            # of a personal-fact answer. Explicit assistant-history questions
            # reverse that preference. No role is removed or exempted from
            # the same delivered-character/record budget.
            role_priority = (int(roles == {"assistant"}) if assistant_recall
                             else int(roles == {"user"}) if personal_query else 0)
            # Keep coverage tiers finite: continuous content scores already
            # order the incoming ranking. Reusing them as outer bucket keys
            # would split one observation across near-unique tiers and exhaust
            # repeated fragments before another source gets its first turn.
            # A window match is a retrieval hint, never an asserted event date.
            tier = (item.get("policy_score", 20),
                    bool(item.get("temporal_window_match")), role_priority, support)
            bucket = buckets.setdefault(tier, {})
            bucket.setdefault(self._source_group_key(item), []).append((position, item))
        result: list[dict] = []
        for tier in sorted(buckets, reverse=True):
            groups = list(buckets[tier].values())
            for group in groups:
                # Prefer a verbatim context that actually contains another
                # candidate fact; its extra source clauses must still pay the
                # ordinary delivered-character and record budgets.
                members = tuple(group)
                group.sort(key=lambda row: (
                    -sum(self._source_text_covers(row[1], other[1]) for other in members), row[0],
                ))
            groups.sort(key=lambda group: min(row[0] for row in group))
            depth = 0
            while any(depth < len(group) for group in groups):
                for group in groups:
                    if depth < len(group):
                        item = group[depth][1]
                        item["reason"] += ", profile_source_coverage"
                        result.append(item)
                depth += 1
        return result

    def _render_context(self, item: dict) -> str:
        record = item["record"]
        if not self.profile.retrieve_message_context:
            return record.canonical_value
        # Metadata belongs to delivery, not fact text, fingerprints or matching.
        payload = {"source_observed_at": record.observed_at.isoformat() if record.observed_at else None,
                   "source_message_ids": record.source_message_ids, "content": record.canonical_value}
        if temporal_question(item.get("test_prompt", "")):
            references = temporal_references(record.canonical_value, record.observed_at)
            if references:
                payload["relative_time_reference_only"] = [
                    {key: ref[key] for key in (
                        "phrase", "resolved_start", "resolved_end", "precision", "approximate",
                        "range_kind", "ambiguity", "candidate_ranges", "weekend_convention",
                        *(("caution",) if ref["precision"] == "weekend" else ()),
                    ) if key in ref}
                    for ref in references[:6]
                ]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _include_topic_neighborhood(candidates: list[dict]) -> None:
        """Recall related retained content; never assert a factual relation.

        The pure helper freezes original lexical anchors and proposes only
        bounded one-hop neighbors. Its score cannot bypass lifecycle filters
        or the ordinary final record/character budgets.
        """
        by_id = {item["record"].id: item for item in candidates}
        for proposal in topic_neighborhood_proposals(candidates):
            item = by_id[proposal.memory_id]
            item["relevance"] = max(item["relevance"], proposal.relevance)
            item["context_score"] = max(item.get("context_score", 0), proposal.context_score)
            item["reason"] += ", " + proposal.reason
            item["topic_neighborhood"] = {
                "anchor_memory_id": proposal.anchor_memory_id,
                "shared_terms": list(proposal.shared_terms),
                "shared_weight": proposal.shared_weight,
                "neighbor_content_coverage": proposal.neighbor_content_coverage,
                "anchor_source_roles": list(proposal.anchor_source_roles),
                "validation_scope": proposal.validation_scope,
            }

    @staticmethod
    def _annotate_lexical_strength(candidates: list[dict]) -> None:
        """Weight retained content matches without reading source or gold.

        Document frequency uses the same eligible private store on each query.
        Repeated mentions of a common word contribute less than distinctive
        content. This affects packing, never canonical text or identity.
        """
        available = [item for item in candidates if item["eligible"]]
        frequencies = Counter(term for item in available for term in item.get("_memory_terms", set()))
        for item in available:
            shared = item.get("_query_terms", set()) & item.get("_memory_terms", set())
            score = sum(1 + math.log((len(available) + 1) / (frequencies[term] + 1)) for term in sorted(shared))
            if item.get("category_match"):
                score += 3
            if not item.get("_query_terms"):
                score = item.get("direct_relevance", item.get("relevance", 0))
            item["direct_context_score"] = score
            item["context_score"] = score

    @staticmethod
    def _include_message_context(candidates: list[dict]) -> None:
        """Recover active sibling fragments without consulting original text or gold.

        Use a single hop from directly matching records. Never revive unavailable
        records. Normal profile filters and budgets still apply after expansion.
        """
        anchors: dict[str, float] = {}
        strengths: dict[str, float] = {}
        for item in candidates:
            if item["eligible"] and item["relevance"] > 0:
                for source_id in item["record"].source_message_ids:
                    anchors[source_id] = max(anchors.get(source_id, 0), item["relevance"])
                    strengths[source_id] = max(strengths.get(source_id, 0), item.get("direct_context_score", item["relevance"]))
        for item in candidates:
            if not item["eligible"]:
                continue
            score = max((anchors.get(s, 0) for s in item["record"].source_message_ids), default=0)
            if score > item["relevance"]:
                item["relevance"] = score
                item["reason"] += ", same_message_context"
            strength = max((strengths.get(s, 0) for s in item["record"].source_message_ids), default=0) * 0.85
            item["context_score"] = max(item.get("context_score", item["relevance"]), strength)

    @staticmethod
    def _include_temporal_neighborhood(candidates: list[dict], prompt: str) -> None:
        """Recover temporal context with bounded, attenuated stored-fact links.

        IDF preserves discriminative names over generic event words. Personal
        event questions use user statements; explicitly requested assistant
        history remains available. All expansion is one hop from direct query
        matches, never from gold or unstored source text.
        """
        question = re.split(r"\nQuestion date:", prompt, flags=re.I)[0]
        personal = bool(re.search(r"\b(?:I|my|we|our)\b", question, re.I))
        assistant_recall = assistant_history_intent(question)
        # Assistant text may locate a nearby user statement without itself
        # becoming evidence that the user attended an event.
        bridge_candidates = [item for item in candidates if item["eligible"]]
        if personal and not assistant_recall:
            for item in candidates:
                if item.get("source_roles") == {"assistant"}:
                    item["eligible"] = False
                    item["reason"] += ", assistant_history_not_user_event_evidence"
        available = [item for item in candidates if item["eligible"]]
        frequencies = Counter(term for item in bridge_candidates for term in item.get("_memory_terms", set()))
        for item in bridge_candidates:
            score = sum(1 + math.log((len(bridge_candidates) + 1) / (frequencies[term] + 1))
                        for term in sorted(item.get("_query_terms", set()) & item.get("_memory_terms", set())))
            if item.get("category_match"):
                score += 3
            if not item.get("_query_terms"):
                score = item.get("direct_relevance", 0)
            item["direct_context_score"] = score
            item["context_score"] = score
        anchors = [item for item in bridge_candidates if item.get("direct_relevance", 0) > 0]
        rare_limit = max(3, int(len(available) * 0.05))
        window = query_window(prompt)
        for item in available:
            best = item["context_score"]
            raw = item["relevance"]
            for anchor in anchors:
                strength = 0.0
                if set(item["record"].source_message_ids) & set(anchor["record"].source_message_ids):
                    strength = 1.0
                else:
                    shared = item.get("_memory_terms", set()) & anchor.get("_memory_terms", set())
                    rare_shared = sum(frequencies[term] <= rare_limit and not term.isdigit() for term in shared)
                    for pos_a, time_a in item.get("source_context_points", []):
                        for pos_b, time_b in anchor.get("source_context_points", []):
                            if time_a != time_b:
                                continue
                            distance = abs(pos_a - pos_b)
                            if distance <= 6:
                                strength = max(strength, 0.5)
                            # Explicit shared content can link a name to a date
                            # across up to six dialogue exchanges, still one hop.
                            if distance <= 12 and rare_shared >= 2:
                                strength = max(strength, 0.8)
                best = max(best, strength * anchor["direct_context_score"])
                raw = max(raw, strength * anchor["direct_relevance"])
            if raw > item["relevance"]:
                item["relevance"] = raw
                item["reason"] += ", bounded_temporal_source_neighborhood"
            item["context_score"] = best
            if not window or item["relevance"] <= 0:
                continue
            record = item["record"]
            references = temporal_references(record.canonical_value, record.observed_at)
            dates = [interval for ref in references for interval in _reference_ranges(ref)]
            if record.observed_at:
                observed = record.observed_at.date().isoformat()
                dates.append((observed, observed))
            if any(start <= window_end and end >= window_start
                   for start, end in dates for window_start, window_end in _reference_ranges(window)):
                item["temporal_window_match"] = True
                item["reason"] += ", query_temporal_window_match"

    def _select(self, candidates: list[dict], strategy: MemoryStrategy) -> list[dict]:
        if not candidates:
            return []
        if strategy == MemoryStrategy.NO_MEMORY:
            return []
        if strategy == MemoryStrategy.FULL_CONTEXT:
            # Replay the active store in source/write order. This is an
            # intentionally simple reference baseline, not a ranking policy.
            return sorted(candidates, key=lambda item: (
                self._time_value(item["record"]), item["record"].write_order,
            ))
        if strategy == MemoryStrategy.WEAK_FIRST_HIT:
            # The weak baseline persists every write but returns its first
            # relevant record, deliberately lacking update reconciliation.
            return [min(candidates, key=lambda item: item["record"].write_order)]
        if strategy == MemoryStrategy.STRONG_RULE_BASED:
            return sorted(candidates, key=lambda item: (
                bool(item.get("temporal_window_match")) if self.profile.retrieve_message_context else False,
                # A requirement in an unrelated typed domain must not displace
                # the queried fact merely because it has an override label.
                bool(item.get("category_match")),
                item["policy_score"],
                (item.get("context_score", item["relevance"]) / math.sqrt(len(self._render_context(item)) + 3))
                if self.profile.retrieve_message_context else 0,
                self._time_value(item["record"]), item["record"].write_order,
            ))
        if strategy == MemoryStrategy.SCOPE_AWARE:
            return self._select_scope_aware(candidates)
        if strategy == MemoryStrategy.TEMPORAL_IMPORTANCE:
            return self._select_temporal_importance(candidates)
        return sorted(candidates, key=lambda item: (
            item["relevance"] * 10 + item["policy_score"],
            self._time_value(item["record"]), item["record"].write_order,
        ))

    def _select_scope_aware(self, candidates: list[dict]) -> list[dict]:
        """Retrieve a small, intent-matched private context.

        ``project_requirement`` wins for a prompt about the current task. A
        preference or profile record wins only for an explicitly matching
        preference/profile question.  The final order remains low-to-high
        priority so all existing target connectors preserve their contract of
        treating the last strong-context record as the decision record.
        """
        requested_projects = named_projects(candidates[0]["test_prompt"])
        if requested_projects:
            retained = []
            for item in candidates:
                record_projects = named_projects(item["record"].canonical_value)
                if record_projects and not requested_projects.intersection(record_projects):
                    item["reason"] += ", excluded_other_named_project"
                else:
                    retained.append(item)
            candidates = retained
            if not candidates:
                return []
        preferred_scope, intent_reason = _preferred_scope(candidates[0]["test_prompt"])
        for item in candidates:
            record_scope = TargetMemoryScope(item["record"].scope)
            scope_bonus = _scope_bonus(record_scope, preferred_scope)
            item["scope_bonus"] = scope_bonus
            item["scope_match"] = record_scope == preferred_scope if preferred_scope else False
            item["policy_score"] += scope_bonus
            item["reason"] = f"{item['reason']}, {intent_reason}, scope={record_scope.value}, scope_bonus={scope_bonus}"

        # A matching scope creates a deliberately narrow context. This avoids
        # giving a task question a generic profile/preference instruction, and
        # avoids letting an explicit preference question be answered by an
        # unrelated current project constraint. Multiple matching project
        # requirements remain available so unresolved conflicts stay visible.
        preferred = [item for item in candidates if item["scope_match"]]
        if preferred:
            # A scope can contain unrelated project requirements.  When the
            # prompt identifies a topic (for example programming language),
            # retain only matching topic records rather than accidentally
            # handing a database constraint to a language question.
            topic_preferred = [item for item in preferred if item["category_match"]]
            candidates = topic_preferred or preferred
        else:
            # Update/freshness prompts have no preference scope, but their
            # named topic still makes a narrower context possible.
            topic_matched = [item for item in candidates if item["category_match"]]
            if topic_matched:
                candidates = topic_matched

        # A conflict-resolution test about an explicit UPDATE must see that
        # relationship pair, not unrelated memories that merely share its
        # topic. This keeps the evidence condition honest and inspectable.
        resolution_history = [item for item in candidates if item.get("resolution_history")]
        if resolution_history:
            candidates = resolution_history

        return sorted(candidates, key=lambda item: (
            item["relevance"] * 10 + item["policy_score"],
            self._time_value(item["record"]), item["record"].write_order,
        ))

    def _select_temporal_importance(self, candidates: list[dict]) -> list[dict]:
        """Rank relevant records using only relative source chronology.

        The highest rank is made available last, preserving the controlled
        target connector contract used by the other strong policies.  Absolute
        message timestamps and audit-time clocks are intentionally absent:
        changing the calendar date of an authorised transcript must not change
        this policy's decision.
        """
        for item in candidates:
            importance, components = self._importance(item)
            temporal_score = (item["relevance"] * 100) + importance + item["recency_factor"]
            item["importance_factor"] = importance
            item["importance_components"] = components
            item["temporal_importance_score"] = temporal_score
            item["reason"] = (
                f"{item['reason']}, temporal_chronology={item['relative_chronology']}, "
                f"recency_factor={item['recency_factor']}, importance_factor={importance}"
            )
        return sorted(candidates, key=lambda item: (
            item["temporal_importance_score"], item["record"].write_order,
        ))

    def _candidate(
        self, record: TargetAgentMemoryModel, test: TestCase,
        relations: list[TargetAgentMemoryRelationshipModel],
    ) -> dict:
        # The benchmark appends source chronology for the reader. That footer
        # is not part of the substantive question's lexical retrieval intent.
        question = re.sub(r"\nQuestion date: [^\n]+$", "", test.prompt)
        prompt_terms = _retrieval_tokens(question, normalise_inflections=self.profile.retrieve_message_context)
        value_terms = _retrieval_tokens(record.canonical_value, normalise_inflections=self.profile.retrieve_message_context)
        if self.profile.retrieve_message_context and temporal_question(question):
            # Temporal scaffolding is not an event's topic. Otherwise "weeks"
            # can retrieve arbitrary facts and seed unrelated neighborhoods.
            prompt_terms -= {"ago", "day", "week", "month", "year", "past", "last", "first",
                             "earliest", "latest", "order", "starting", "activity", "related", "device",
                             "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                             "ten", "eleven", "twelve", "set", "up", "passed", "attended", "attend", "event",
                             "this", "current", "calendar", "how", "many", "number"}
            prompt_terms = {term for term in prompt_terms if not term.isdigit()}
        overlap = len(prompt_terms & value_terms)
        category_match = int(bool(_category(test.prompt) and _category(test.prompt) == _category(record.canonical_value)))
        relevance = overlap + (3 * category_match)
        relationship_types = sorted(relation.relationship_type for relation in relations)
        policy_score = 20
        reasons = [f"lexical_overlap={overlap}"]
        if category_match:
            reasons.append("topic_category_match")
        if record.lifecycle_state == TargetMemoryLifecycleState.SUPERSEDED.value:
            policy_score = 0
            reasons.append("superseded_record")
        if (
            RelationshipType.UPDATE.value in relationship_types
            and self.maintenance_policy == TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION
        ):
            policy_score = max(policy_score, 40)
            reasons.append("explicit_update")
        elif RelationshipType.UPDATE.value in relationship_types:
            reasons.append("update_link_retained_without_consolidation")
        if RelationshipType.CONTEXTUAL_OVERRIDE.value in relationship_types:
            policy_score = max(policy_score, 60)
            reasons.append("contextual_override")
        if RelationshipType.CONFLICT.value in relationship_types or record.lifecycle_state == TargetMemoryLifecycleState.CONFLICTED.value:
            policy_score = max(policy_score, 30)
            reasons.append("unresolved_conflict")
        return {
            "record": record, "relevance": relevance, "direct_relevance": relevance,
            "_query_terms": prompt_terms, "_memory_terms": value_terms,
            "category_match": bool(category_match),
            "resolution_history": False,
            "policy_score": policy_score, "relationship_types": relationship_types,
            "conflict_targets": [relation.target_memory_id for relation in relations
                                 if relation.relationship_type == RelationshipType.CONFLICT.value],
            "reason": ", ".join(reasons), "test_prompt": test.prompt,
            # Ingested source IDs are resolved against the authorised
            # conversation in ``_annotate_relative_chronology``.
            "relative_chronology": 0.0,
            "chronology_basis": "pending_authorised_conversation_order",
            "recency_factor": 0.0,
            "eligible": True,
        }

    @staticmethod
    def _include_update_history_for_question_context(
        candidates: list[dict], relations: list[TargetAgentMemoryRelationshipModel],
        question: str, strategy: MemoryStrategy,
    ) -> None:
        """Expose an UPDATE's prior side when the question asks for its history.

        The retrieval policy sees only the target-visible question and its own
        stored records.  It must not use the auditor's test-dimension label to
        decide which evidence to provide.  Current-state questions continue to
        use the normal recency/update policy; explicit requests about earlier
        values or change history may need both endpoints of an UPDATE.
        """
        if strategy != MemoryStrategy.SCOPE_AWARE or not _question_requests_update_history(question):
            return
        by_id = {item["record"].id: item for item in candidates}
        for relation in relations:
            if relation.relationship_type != RelationshipType.UPDATE.value:
                continue
            current = by_id.get(relation.memory_id)
            prior = by_id.get(relation.target_memory_id)
            if not current or not prior or not current["category_match"]:
                continue
            current["resolution_history"] = True
            prior["resolution_history"] = True
            prior["eligible"] = True
            prior["relevance"] = max(prior["relevance"], current["relevance"])
            prior["reason"] = f"{prior['reason']}, update_history_included_for_question_context"

    @staticmethod
    def _annotate_relative_chronology(candidates: list[dict], conversation: Conversation) -> None:
        """Attach reproducible chronology without consulting wall-clock time.

        A record takes the latest position of its cited source messages in the
        authorised conversation.  Writer order is only a deterministic
        fallback for a custom writer that supplied no valid source IDs.
        """
        source_position = {
            message.message_id: position
            for position, message in enumerate(conversation.messages, start=1)
        }
        source_times = {message.message_id: message.timestamp.isoformat() for message in conversation.messages}
        source_roles = {message.message_id: message.role.strip().lower() for message in conversation.messages}
        message_total = max(len(conversation.messages), 1)
        fallback_total = max((item["record"].write_order for item in candidates), default=1)
        for item in candidates:
            record = item["record"]
            positions = [source_position[item_id] for item_id in record.source_message_ids if item_id in source_position]
            item["source_positions"] = positions
            item["source_roles"] = {source_roles[source_id] for source_id in record.source_message_ids
                                    if source_id in source_roles}
            item["source_time_keys"] = [source_times[source_id] for source_id in record.source_message_ids
                                        if source_id in source_times]
            item["source_context_points"] = [(source_position[source_id], source_times[source_id])
                                              for source_id in record.source_message_ids
                                              if source_id in source_times]
            if positions:
                position = max(positions)
                denominator = message_total
                basis = "authorised_conversation_message_order"
            else:
                position = record.write_order
                denominator = fallback_total
                basis = "deterministic_writer_order_fallback"
            relative = round(position / max(denominator, 1), 6)
            item["relative_chronology"] = relative
            item["chronology_basis"] = basis
            # A deliberately bounded factor leaves lexical relevance and
            # semantic importance visible rather than reducing the policy to
            # a latest-write-only baseline.
            item["recency_factor"] = round(relative * 30, 6)

    @staticmethod
    def _importance(item: dict) -> tuple[float, list[str]]:
        """Return an explainable, source-independent retention importance."""
        record = item["record"]
        scope = TargetMemoryScope(record.scope)
        scope_weights = {
            TargetMemoryScope.EPISODIC: 10.0,
            TargetMemoryScope.PREFERENCE: 20.0,
            TargetMemoryScope.PROFILE: 30.0,
            TargetMemoryScope.PROJECT_REQUIREMENT: 45.0,
        }
        importance = scope_weights[scope]
        components = [f"scope:{scope.value}={scope_weights[scope]:g}"]
        relationships = set(item["relationship_types"])
        if RelationshipType.UPDATE.value in relationships:
            importance += 15.0
            components.append("update_link=15")
        if RelationshipType.CONTEXTUAL_OVERRIDE.value in relationships:
            importance += 25.0
            components.append("contextual_override=25")
        if RelationshipType.CONFLICT.value in relationships or record.lifecycle_state == TargetMemoryLifecycleState.CONFLICTED.value:
            importance += 20.0
            components.append("unresolved_conflict=20")
        return importance, components

    def _mark_retrieval_eligibility(
        self,
        candidates: list[dict],
        strategy: MemoryStrategy,
        evicted_ids: set[str],
    ) -> None:
        """Keep excluded records in evidence while withholding their context.

        Weak-first-hit intentionally retains stale UPDATE observations as a
        baseline. Every stronger strategy excludes superseded records. Capacity
        evictions are excluded under every strategy, because the private Agent
        no longer has them in its active store.
        """
        for item in candidates:
            record = item["record"]
            if (
                record.id in evicted_ids
                or record.lifecycle_state in {TargetMemoryLifecycleState.EVICTED.value, TargetMemoryLifecycleState.DIAGNOSTIC_ONLY.value}
            ):
                item["eligible"] = False
                exclusion = "diagnostic_packet_excluded" if record.lifecycle_state == TargetMemoryLifecycleState.DIAGNOSTIC_ONLY.value else "capacity_evicted_excluded"
                item["reason"] = f"{item['reason']}, {exclusion}"
            elif (
                record.lifecycle_state == TargetMemoryLifecycleState.SUPERSEDED.value
                and strategy != MemoryStrategy.WEAK_FIRST_HIT
            ):
                item["eligible"] = False
                item["reason"] = f"{item['reason']}, superseded_excluded_by_strategy"

    def _apply_capacity_limit(self, run_id: str) -> None:
        """Apply explainable retention without deleting historical evidence.

        An eviction receives the explicit ``EVICTED`` lifecycle state and a
        durable maintenance event. The record stays in the private trace,
        which makes capacity effects reviewable while retrieval treats it as
        unavailable.
        """
        if self.max_active_records is None:
            return
        records = self._records(run_id)
        relation_by_memory: dict[str, list[TargetAgentMemoryRelationshipModel]] = {}
        for relation in self._relationships(run_id):
            relation_by_memory.setdefault(relation.memory_id, []).append(relation)
        evicted_ids = self._evicted_memory_ids(run_id)
        retained = [
            record for record in records
            if record.id not in evicted_ids
            and record.lifecycle_state not in {
                TargetMemoryLifecycleState.SUPERSEDED.value,
                TargetMemoryLifecycleState.EVICTED.value,
                TargetMemoryLifecycleState.DIAGNOSTIC_ONLY.value,
            }
        ]
        protected = [
            record for record in retained
            if record.lifecycle_state == TargetMemoryLifecycleState.CONFLICTED.value
        ]
        if len(protected) > self.max_active_records:
            self._event(
                run_id, None, TargetMemoryEventType.MAINTENANCE_APPLIED,
                details={
                    "maintenance_action": "capacity_soft_limit_preserved_conflict",
                    "max_active_records": self.max_active_records,
                    "retained_record_count": len(retained),
                    "protected_conflicted_memory_ids": [record.id for record in protected],
                },
            )
            return

        if self.profile.retention_policy == "source_coverage" and len(retained) > self.max_active_records:
            # Prospective batch selection over available written records only.
            # Previous evictions above are unavailable, even if their text is
            # retained in the diagnostic database. Both retrieval arms use this
            # same frozen ingestion choice and the original record capacity.
            decision = select_retention_coverage([
                RetentionCoverageCandidate(
                    memory_id=record.id, lifecycle_state=record.lifecycle_state,
                    retention_priority=self._retention_rank(record, relation_by_memory.get(record.id, []))[0],
                    observed_at=record.observed_at.isoformat() if record.observed_at else None,
                    observed_order=self._time_value(record), write_order=record.write_order,
                    source_message_ids=tuple(record.source_message_ids), canonical_value=record.canonical_value,
                ) for record in retained
            ], capacity=self.max_active_records, representative_policy="content_information")
            by_id = {record.id: record for record in retained}
            trace = {row["memory_id"]: row for row in decision.decisions}
            self._event(run_id, None, TargetMemoryEventType.MAINTENANCE_APPLIED, details={
                "maintenance_action": "capacity_source_coverage_selection",
                "retention_policy": self.profile.retention_policy, "selector_version": decision.version,
                "max_active_records": self.max_active_records,
                "retained_record_count": len(decision.retained_memory_ids),
                "priority_counts": list(decision.priority_counts),
                "decisions": list(decision.decisions),
                "scope": "provenance_and_observation_coverage_not_event_identity_or_lossless_retention",
            })
            for memory_id in decision.evicted_memory_ids:
                record = by_id[memory_id]
                record.lifecycle_state = TargetMemoryLifecycleState.EVICTED.value
                self._event(run_id, record.id, TargetMemoryEventType.MAINTENANCE_APPLIED,
                    source_message_ids=list(record.source_message_ids), details={
                        "maintenance_action": "capacity_evicted_record",
                        "max_active_records": self.max_active_records, "evicted_memory_id": record.id,
                        "canonical_fingerprint": _canonical_fingerprint(record.canonical_value),
                        "scope": record.scope, "exclusion": "all_retrieval_strategies",
                        "selector_version": decision.version, "retention_decision": trace[memory_id],
                    })
            return

        evictable = [record for record in retained if record not in protected]
        while len(retained) > self.max_active_records and evictable:
            record = min(
                evictable,
                key=lambda item: self._retention_rank(item, relation_by_memory.get(item.id, [])),
            )
            record.lifecycle_state = TargetMemoryLifecycleState.EVICTED.value
            retained.remove(record)
            evictable.remove(record)
            self._event(
                run_id, record.id, TargetMemoryEventType.MAINTENANCE_APPLIED,
                source_message_ids=list(record.source_message_ids),
                details={
                    "maintenance_action": "capacity_evicted_record",
                    "max_active_records": self.max_active_records,
                    "evicted_memory_id": record.id,
                    "canonical_fingerprint": _canonical_fingerprint(record.canonical_value),
                    "scope": record.scope,
                    "exclusion": "all_retrieval_strategies",
                },
            )

    def _retention_rank(
        self,
        record: TargetAgentMemoryModel,
        relations: list[TargetAgentMemoryRelationshipModel],
    ) -> tuple[int, float, int]:
        """Lower values are first to evict: episodic, old, weakly linked."""
        scope_weight = {
            TargetMemoryScope.EPISODIC.value: 0,
            TargetMemoryScope.PREFERENCE.value: 10,
            TargetMemoryScope.PROFILE.value: 20,
            TargetMemoryScope.PROJECT_REQUIREMENT.value: 30,
        }.get(record.scope, 0)
        relationship_weight = 40 if any(
            relation.relationship_type == RelationshipType.CONTEXTUAL_OVERRIDE.value
            for relation in relations
        ) else 0
        return scope_weight + relationship_weight, self._time_value(record), record.write_order

    def _evicted_memory_ids(self, run_id: str) -> set[str]:
        events = self.db.scalars(
            select(TargetAgentMemoryEventModel)
            .where(TargetAgentMemoryEventModel.run_id == run_id)
            .where(TargetAgentMemoryEventModel.event_type == TargetMemoryEventType.MAINTENANCE_APPLIED.value)
        ).all()
        return {
            str(event.details["evicted_memory_id"])
            for event in events
            if event.details.get("maintenance_action") == "capacity_evicted_record"
            and event.details.get("evicted_memory_id")
        }

    def _has_relationship(self, memory_id: str) -> bool:
        return self.db.scalar(
            select(TargetAgentMemoryRelationshipModel.id)
            .where(TargetAgentMemoryRelationshipModel.memory_id == memory_id)
            .limit(1)
        ) is not None

    def _records(self, run_id: str) -> list[TargetAgentMemoryModel]:
        return self.db.scalars(
            select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == run_id)
            .order_by(TargetAgentMemoryModel.write_order)
        ).all()

    def _relationships(self, run_id: str) -> list[TargetAgentMemoryRelationshipModel]:
        return self.db.scalars(
            select(TargetAgentMemoryRelationshipModel)
            .where(TargetAgentMemoryRelationshipModel.run_id == run_id)
        ).all()

    def _write_events(self, run_id: str) -> list[TargetAgentMemoryEventModel]:
        return self.db.scalars(
            select(TargetAgentMemoryEventModel)
            .where(TargetAgentMemoryEventModel.run_id == run_id)
            .where(TargetAgentMemoryEventModel.event_type != TargetMemoryEventType.RETRIEVED.value)
            .order_by(TargetAgentMemoryEventModel.created_at, TargetAgentMemoryEventModel.id)
        ).all()

    def _event(
        self, run_id: str, memory_id: str | None, event_type: TargetMemoryEventType,
        source_message_ids: list[str] | None = None, details: dict | None = None,
        created_at: datetime | None = None,
    ) -> TargetAgentMemoryEventModel:
        event = TargetAgentMemoryEventModel(
            id=_ident("TE"), run_id=run_id, memory_id=memory_id,
            event_type=event_type.value, source_message_ids=source_message_ids or [],
            details=details or {}, created_at=created_at or datetime.now(timezone.utc),
        )
        self.db.add(event)
        return event

    def _record_schema(self, record: TargetAgentMemoryModel) -> TargetAgentMemoryRecord:
        relationships = self.db.scalars(
            select(TargetAgentMemoryRelationshipModel)
            .where(TargetAgentMemoryRelationshipModel.memory_id == record.id)
        ).all()
        return TargetAgentMemoryRecord(
            memory_id=record.id, run_id=record.run_id,
            source_conversation_id=record.source_conversation_id,
            canonical_value=record.canonical_value,
            scope=record.scope,
            lifecycle_state=record.lifecycle_state,
            source_message_ids=list(record.source_message_ids), observed_at=record.observed_at,
            write_order=record.write_order,
            relationships=[
                MemoryRelationship(type=item.relationship_type, target_memory_id=item.target_memory_id)
                for item in relationships
            ],
        )

    @staticmethod
    def _event_schema(event: TargetAgentMemoryEventModel) -> TargetMemoryWriteEvidence:
        return TargetMemoryWriteEvidence(
            event_id=event.id, run_id=event.run_id, memory_id=event.memory_id,
            event_type=event.event_type, source_message_ids=list(event.source_message_ids),
            details=dict(event.details), created_at=event.created_at,
        )

    @staticmethod
    def _time_value(record: TargetAgentMemoryModel) -> float:
        if record.observed_at is None:
            return float(record.write_order)
        # SQLite commonly returns naive UTC datetimes even when writes were
        # timezone-aware. Treat both forms as UTC so retention order is stable
        # across databases and hosts with different local time zones.
        observed_at = record.observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        return observed_at.timestamp()


def _tokens(text: str) -> set[str]:
    return {term.lower() for term in _WORDS.findall(text) if term.lower() not in _STOP}


def _retrieval_tokens(text: str, *, normalise_inflections: bool = False) -> set[str]:
    # Shared contraction cleanup applies to both arms. Optional morphology
    # remains controlled by the declared message-context profile. Canonical
    # signatures continue using _tokens above without this retrieval helper.
    return retrieval_tokens(text, normalise_inflections=normalise_inflections,
                            stop_words=_STOP | _RETRIEVAL_STOP)


def _canonical_fingerprint(value: str) -> str:
    """Normalise only case/spacing/punctuation for traceable exact deduping."""
    return fact_fingerprint(value)


def _near_duplicate_signature(value: str) -> frozenset[str]:
    """Content-only signature used for a deliberately narrow near-merge.

    Word order is ignored only after removing the existing retrieval stop
    words. This accepts superficial changes such as adding ``the`` or moving
    ``currently`` while preserving content-bearing tokens for audit evidence.
    """
    return frozenset(_tokens(value))


def _is_conservative_near_duplicate(value: str) -> bool:
    """Reject near merging whenever wording may imply a changed fact."""
    words = {term.lower() for term in _WORDS.findall(value)}
    # A bag of words cannot preserve which entity owns each quantity/date.
    # Numeric facts may still exact-deduplicate, with their token order intact.
    return not bool(words & _NEGATION_OR_CHANGE_CUES) and not any(
        any(character.isdigit() for character in word) for word in words
    )


def _preferred_scope(prompt: str) -> tuple[TargetMemoryScope | None, str]:
    """Infer a retrieval intent solely from the user-facing test prompt."""
    text = prompt.lower()
    if re.search(r"\b(?:deployment|policies|policy|secrets?|credentials?)\b", text):
        return TargetMemoryScope.PROJECT_REQUIREMENT, "intent=project_policy"
    if re.search(r"\b(?:this|current|currently|for\s+the)\s+(?:assignment|project|task)\b|\b(?:must|required|requirement|mandatory)\b", text):
        return TargetMemoryScope.PROJECT_REQUIREMENT, "intent=current_project_requirement"
    if re.search(r"\b(?:prefer|preference|favour(?:ite)?|favorite|usually\s+use)\b", text):
        return TargetMemoryScope.PREFERENCE, "intent=general_preference"
    if re.search(r"\b(?:location|based|live|located|name|background|profile|city)\b|\bwhere\b.*\b(?:user|you|i|we)\b", text):
        return TargetMemoryScope.PROFILE, "intent=profile_fact"
    return None, "intent=general_relevance"


def _scope_bonus(scope: TargetMemoryScope, preferred: TargetMemoryScope | None) -> int:
    """Stable policy weights; positive values make the record later/higher."""
    if preferred is None:
        return 0
    if scope == preferred:
        return 80
    if preferred == TargetMemoryScope.PROJECT_REQUIREMENT and scope == TargetMemoryScope.PREFERENCE:
        return -40
    # Unrelated scope remains eligible only for requirement prompts, where
    # freshness/conflict evidence may still be useful alongside the decision.
    return -10


def _category(value: str) -> str | None:
    text = value.lower()
    if re.search(r"\b(?:mysql|postgres(?:ql)?|mongodb|sqlite|database|sql)\b", text):
        return "database"
    if re.search(r"\b(?:logs?|logging|object storage|storage bucket)\b", text):
        return "log-storage"
    if re.search(r"\b(?:secrets?|credentials?|environment variables?|config(?:uration)? files?)\b", text):
        return "secret-configuration"
    if is_meeting_platform_topic(text):
        return "meeting-platform"
    if is_language_topic(text):
        return "programming-language"
    if re.search(r"\b(?:sydney|melbourne|london|location|city|based (?:in|now)|located (?:in|now)|live in|(?:moved|relocated)\s+to|relocat)\b", text):
        return "location"
    if re.search(r"\b(?:remote|from home|office|hybrid)\b", text):
        return "working-arrangement"
    return None
