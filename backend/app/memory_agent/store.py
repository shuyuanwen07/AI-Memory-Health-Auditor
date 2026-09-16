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
    TargetMemoryRetrievalEvidence,
    TargetMemoryRetrievalResult,
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


def _ident(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:10].upper()}"


class SqlTargetMemoryStore(TargetMemoryStore):
    """SQLAlchemy implementation of one target memory store per audit run.

    ``ingest`` is idempotent: retries use the previously written state rather
    than changing the target's observed history.  ``retrieve`` is intentionally
    append-only, keeping every retrieval decision available for review while
    keeping it off public test endpoints.
    """

    def __init__(self, db: Session, extractor: MemoryExtractor | None = None):
        self.db = db
        self.extractor = extractor or RuleBasedMemoryExtractor()
        self.writer_version = getattr(self.extractor, "VERSION", self.extractor.__class__.__name__)

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
        now = datetime.now(timezone.utc)
        self._event(
            run_id, None, TargetMemoryEventType.INGESTED,
            details={"conversation_id": conversation.conversation_id, "message_count": len(conversation.messages), "writer_version": self.writer_version},
            created_at=now,
        )
        for position, candidate in enumerate(extracted, start=1):
            record = TargetAgentMemoryModel(
                id=_ident("TM"), run_id=run_id,
                source_conversation_id=conversation.conversation_id,
                canonical_value=candidate.canonical_value,
                lifecycle_state=TargetMemoryLifecycleState.ACTIVE.value,
                source_message_ids=list(candidate.source_message_ids),
                observed_at=candidate.timestamp, write_order=position,
            )
            self.db.add(record)
            extracted_ids[candidate.memory_id] = record
            self._event(
                run_id, record.id, TargetMemoryEventType.WRITTEN,
                source_message_ids=list(candidate.source_message_ids),
                details={"write_order": position, "canonical_value": candidate.canonical_value},
            )

        # IDs are generated client-side, so references can be written before a
        # flush.  The relationship direction is the same as ground truth:
        # current/new record -> related earlier record.
        for candidate in extracted:
            record = extracted_ids[candidate.memory_id]
            for relation in candidate.relationships:
                target = extracted_ids.get(relation.target_memory_id)
                if not target:
                    continue
                self.db.add(TargetAgentMemoryRelationshipModel(
                    id=_ident("TMR"), run_id=run_id, memory_id=record.id,
                    relationship_type=relation.type.value, target_memory_id=target.id,
                ))
                if relation.type == RelationshipType.UPDATE:
                    target.lifecycle_state = TargetMemoryLifecycleState.SUPERSEDED.value
                    self._event(
                        run_id, record.id, TargetMemoryEventType.UPDATED,
                        source_message_ids=list(record.source_message_ids),
                        details={"supersedes_memory_id": target.id},
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

        candidates = [
            self._candidate(record, test, relation_by_memory.get(record.id, []))
            for record in records
        ]
        candidates = [item for item in candidates if item["relevance"] > 0]
        selected = self._select(candidates, strategy)
        evidence_rows = [
            {
                "memory_id": item["record"].id,
                "relevance": item["relevance"],
                "policy_score": item["policy_score"],
                "lifecycle_state": item["record"].lifecycle_state,
                "relationship_types": item["relationship_types"],
                "selected": item["record"].id in {choice["record"].id for choice in selected},
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
                     "selected_memory_ids": retrieval.selected_memory_ids},
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
        if RelationshipType.UPDATE.value in relationship_types:
            policy_score = max(policy_score, 40)
            reasons.append("explicit_update")
        if RelationshipType.CONTEXTUAL_OVERRIDE.value in relationship_types:
            policy_score = max(policy_score, 60)
            reasons.append("contextual_override")
        if RelationshipType.CONFLICT.value in relationship_types or record.lifecycle_state == TargetMemoryLifecycleState.CONFLICTED.value:
            policy_score = max(policy_score, 30)
            reasons.append("unresolved_conflict")
        return {
            "record": record, "relevance": relevance,
            "policy_score": policy_score, "relationship_types": relationship_types,
            "reason": ", ".join(reasons),
        }

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
