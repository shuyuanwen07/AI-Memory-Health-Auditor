"""The deterministic, persisted controlled target used by Foundation."""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import uuid4
from app.models import TargetAgentMemoryModel, TargetAgentRetrievalModel

from app.memory_agent import SqlTargetMemoryStore, get_target_memory_writer
from app.memory_agent.retrieval_agent import AgentMemoryRetriever
from app.schemas import (
    AuditRun, Conversation, MemoryStrategy, TargetMemoryMaintenancePolicy,
    TargetResponse, TestCase,
)
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import selected_memory_context
from app.target_systems.interfaces import TargetSystemAdapter


class ControlledTargetSystemAdapter(TargetSystemAdapter):
    """Wrap the built-in private memory store behind the target-system seam."""

    adapter_id = "controlled-memory"
    version = "controlled-memory-v3"

    def __init__(self, db: Session, audit: AuditRun):
        self.db = db
        self.audit = audit
        self.store = SqlTargetMemoryStore(
            db,
            extractor=get_target_memory_writer(
                audit.pipeline_provider, audit.pipeline_model,
                audit.target_memory_writer or "rule_based",
            ),
            maintenance_policy=TargetMemoryMaintenancePolicy(
                audit.memory_maintenance_policy or "update_aware_consolidation"
            ),
            capacity=audit.target_memory_capacity if audit.target_memory_capacity is not None else 50,
            profile=audit.target_memory_profile,
            retrieval_agent=(AgentMemoryRetriever(audit.retrieval_provider, audit.retrieval_model)
                            if audit.retrieval_mode.value == "agent"
                            and audit.retrieval_provider and audit.retrieval_model else None),
        )
        self._conversation: Conversation | None = None
        self._last_retrieval_id: str | None = None
        self._diagnostic_packet_id: str | None = None

    def ingest(self, conversation: Conversation) -> None:
        if not conversation.authorised:
            raise HTTPException(403, "Authorise this conversation before initialising the target memory system.")
        messages = [message for message in conversation.messages if message.role.strip().lower() == "user"]
        if self.audit.reproducibility.intervention == "supplement_source_evidence" and not messages:
            raise HTTPException(422, "Source replay requires authorised user messages; this history has none.")
        replay_value = None
        if self.audit.reproducibility.intervention == "supplement_source_evidence":
            replay_value = "Authorised user source history:\n" + "\n".join(
                f"Source statement ({message.original_timestamp or 'time not recorded'}): {message.content}"
                for message in messages
            )
            if len(replay_value) > self.audit.target_memory_profile.context_character_budget:
                raise HTTPException(422, "The source replay exceeds this run's memory context budget. Prepare a new diagnostic configuration before replaying this history.")
        self.store.ingest(self.audit.run_id, conversation)
        self._conversation = conversation
        self._diagnostic_packet_id = None
        if replay_value is not None:
            # Prepare replay from the target's original input, independently of
            # audit memories, expected answers, question IDs or review labels.
            value = replay_value
            record = self.db.scalar(select(TargetAgentMemoryModel).where(
                TargetAgentMemoryModel.run_id == self.audit.run_id,
                TargetAgentMemoryModel.canonical_value == value,
                TargetAgentMemoryModel.lifecycle_state == "DIAGNOSTIC_ONLY"))
            if record is None:
                record = TargetAgentMemoryModel(id=f"TM{uuid4().hex[:20].upper()}", run_id=self.audit.run_id,
                    source_conversation_id=conversation.conversation_id, canonical_value=value,
                    scope="episodic", lifecycle_state="DIAGNOSTIC_ONLY",
                    source_message_ids=[message.message_id for message in messages],
                    observed_at=messages[-1].timestamp or conversation.created_at, write_order=10000)
                self.db.add(record)
                self.db.flush()
            self._diagnostic_packet_id = record.id

    def answer(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        if self._conversation is None:
            raise RuntimeError("The target system must ingest its authorised conversation before answering.")
        target_test = test.model_copy(update={"expected_behavior": "", "supporting_memory_ids": []})
        retrieval = self.store.retrieve(
            self.audit.run_id, self._conversation, target_test, MemoryStrategy(audit.memory_strategy),
            retrieval_mode=audit.retrieval_mode.value,
        )
        self._last_retrieval_id = retrieval.evidence.retrieval_id
        intervention = audit.reproducibility.intervention
        if intervention == "remove_memory":
            retrieval.context = []
            retrieval.evidence.selected_memory_ids = []
        elif intervention == "supplement_source_evidence" and self._diagnostic_packet_id:
            record = self.db.get(TargetAgentMemoryModel, self._diagnostic_packet_id)
            if record is None or record.run_id != self.audit.run_id:
                raise RuntimeError("The target-owned source replay packet is unavailable.")
            context, selected_ids = [record.canonical_value], [record.id]
            used = len(record.canonical_value)
            profile = self.audit.target_memory_profile
            for value, memory_id in zip(retrieval.context, retrieval.evidence.selected_memory_ids, strict=True):
                if len(context) >= profile.max_retrieved_records:
                    break
                if value in context or used + len(value) > profile.context_character_budget:
                    continue
                context.append(value)
                selected_ids.append(memory_id)
                used += len(value)
            retrieval.context = context
            retrieval.evidence.selected_memory_ids = selected_ids
        if intervention:
            row = self.db.get(TargetAgentRetrievalModel, self._last_retrieval_id)
            row.selected_memory_ids = list(retrieval.evidence.selected_memory_ids)
            row.ranking_evidence = [{**item, "selected": item["memory_id"] in row.selected_memory_ids} for item in row.ranking_evidence]
            self.db.flush()
        private_test = target_test.model_copy(update={"target_memory_context": retrieval.context})
        response = HttpTargetAIConnector().execute(private_test, audit)
        receipt = response.execution_metadata.memory_input
        if receipt is not None:
            # Preserve the same first occurrence and whitespace normalisation
            # as the final provider instruction, including Weak's last trim.
            by_value = {}
            for value, memory_id in zip(retrieval.context, retrieval.evidence.selected_memory_ids, strict=True):
                by_value.setdefault(value.strip(), memory_id)
            receipt.sent_memory_ids = [by_value[value] for value in selected_memory_context(private_test, audit.target_configuration)]
        return response

    def trace(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.version,
            "run_id": self.audit.run_id,
            "last_retrieval_id": self._last_retrieval_id,
        }

    def reset(self) -> None:
        # Run-scoped persistence is intentional.  The database lifecycle owns
        # deletion; this method simply drops the in-process session reference.
        self._conversation = None
        self._last_retrieval_id = None
        self._diagnostic_packet_id = None
