"""Private persistent memory lifecycle for a controlled target agent.

The auditor's ``memories`` table remains human-confirmed ground truth.  This
module instead models what a target agent would remember after seeing the
authorised conversation, so the target never receives reviewer-approved facts
as its memory store.  It provides a small deterministic baseline now and a
stable replacement seam for a future agent memory backend.
"""
from __future__ import annotations

import re
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


_WORDS = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]*")
_STOP = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "what", "which",
    "should", "would", "about", "user", "memory", "remembered", "does", "use",
    "used", "using", "now", "current", "currently", "please", "tell", "me",
})
_NEGATION_OR_CHANGE_CUES = frozenset({
    "not", "never", "without", "instead", "except", "former", "previous",
    "formerly", "before", "after", "until", "no", "different",
})


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
    if re.search(r"\b(?:prefer(?:s|red|ence)?|favour(?:s|ed|ite)?|favorite|favourite|rather\s+than)\b", value):
        return TargetMemoryScope.PREFERENCE
    if re.search(r"\b(?:i\s+am|my\s+name|based\s+in|live\s+in|located\s+in|work\s+as|(?:my|the)\s+backend|i\s+(?:now\s+)?use)\b", value):
        return TargetMemoryScope.PROFILE
    return TargetMemoryScope.EPISODIC


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
        self.db = db
        self.extractor = extractor or RuleBasedMemoryExtractor()
        self.writer_version = getattr(self.extractor, "VERSION", self.extractor.__class__.__name__)
        self.maintenance_policy = TargetMemoryMaintenancePolicy(maintenance_policy)
        self.max_active_records = resolved_capacity

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

        extracted = self.extractor.extract(conversation)
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
            scope = infer_target_memory_scope(candidate.canonical_value)
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
        strategy: MemoryStrategy,
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
        self._mark_retrieval_eligibility(candidates, strategy, evicted_ids)
        eligible = [item for item in candidates if item["eligible"] and item["relevance"] > 0]
        selected = self._select(eligible, strategy)
        selected_ids = {choice["record"].id for choice in selected}
        evidence_rows = [
            {
                "memory_id": item["record"].id,
                "relevance": item["relevance"],
                "policy_score": item["policy_score"],
                "lifecycle_state": item["record"].lifecycle_state,
                "scope": item["record"].scope,
                "relationship_types": item["relationship_types"],
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
            context=[item["record"].canonical_value for item in selected],
            evidence=TargetMemoryRetrievalEvidence(
                retrieval_id=retrieval.id, run_id=run_id, test_id=test.test_id,
                strategy=strategy, selected_memory_ids=list(retrieval.selected_memory_ids),
                ranking_evidence=evidence_rows, created_at=retrieval.created_at,
            ),
        )

    def _select(self, candidates: list[dict], strategy: MemoryStrategy) -> list[dict]:
        if not candidates:
            return []
        if strategy == MemoryStrategy.WEAK_FIRST_HIT:
            # The weak baseline persists every write but returns its first
            # relevant record, deliberately lacking update reconciliation.
            return [min(candidates, key=lambda item: item["record"].write_order)]
        if strategy == MemoryStrategy.STRONG_RULE_BASED:
            return sorted(candidates, key=lambda item: (
                item["policy_score"], self._time_value(item["record"]), item["record"].write_order,
            ))
        if strategy == MemoryStrategy.SCOPE_AWARE:
            return self._select_scope_aware(candidates)
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
            candidates = preferred

        return sorted(candidates, key=lambda item: (
            item["relevance"] * 10 + item["policy_score"],
            self._time_value(item["record"]), item["record"].write_order,
        ))

    def _candidate(
        self, record: TargetAgentMemoryModel, test: TestCase,
        relations: list[TargetAgentMemoryRelationshipModel],
    ) -> dict:
        prompt_terms = _tokens(test.prompt)
        value_terms = _tokens(record.canonical_value)
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
            "record": record, "relevance": relevance,
            "policy_score": policy_score, "relationship_types": relationship_types,
            "reason": ", ".join(reasons), "test_prompt": test.prompt,
            "eligible": True,
        }

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
                or record.lifecycle_state == TargetMemoryLifecycleState.EVICTED.value
            ):
                item["eligible"] = False
                item["reason"] = f"{item['reason']}, capacity_evicted_excluded"
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
        return record.observed_at.timestamp() if record.observed_at else float(record.write_order)


def _tokens(text: str) -> set[str]:
    return {term.lower() for term in _WORDS.findall(text) if term.lower() not in _STOP}


def _canonical_fingerprint(value: str) -> str:
    """Normalise only case/spacing/punctuation for traceable exact deduping."""
    return " ".join(_WORDS.findall(value.lower()))


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
    return not bool(words & _NEGATION_OR_CHANGE_CUES)


def _preferred_scope(prompt: str) -> tuple[TargetMemoryScope | None, str]:
    """Infer a retrieval intent solely from the user-facing test prompt."""
    text = prompt.lower()
    if re.search(r"\b(?:this|current|currently|for\s+the)\s+(?:assignment|project|task)\b|\b(?:must|required|requirement|mandatory)\b", text):
        return TargetMemoryScope.PROJECT_REQUIREMENT, "intent=current_project_requirement"
    if re.search(r"\b(?:prefer|preference|favour(?:ite)?|favorite|usually\s+use)\b", text):
        return TargetMemoryScope.PREFERENCE, "intent=general_preference"
    if re.search(r"\b(?:where|location|based|live|located|name|background|profile)\b", text):
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
    if re.search(r"\b(?:python|java|rust|javascript|typescript|(?:programming|scripting)\s+languages?)\b", text):
        return "programming-language"
    if re.search(r"\b(?:sydney|melbourne|london|based in|located in|live in|relocat)\b", text):
        return "location"
    if re.search(r"\b(?:remote|from home|office|hybrid)\b", text):
        return "working-arrangement"
    return None
