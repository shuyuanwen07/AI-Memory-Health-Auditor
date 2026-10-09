"""The deterministic, persisted controlled target used by Foundation."""
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import uuid4
from app.models import MemoryModel, TargetAgentMemoryModel, TargetAgentRetrievalModel

from app.memory_agent import SqlTargetMemoryStore, get_target_memory_writer
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
    version = "controlled-memory-v2"

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
        )
        self._conversation: Conversation | None = None
        self._last_retrieval_id: str | None = None

    def ingest(self, conversation: Conversation) -> None:
        self.store.ingest(self.audit.run_id, conversation)
        self._conversation = conversation

    def answer(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        if self._conversation is None:
            raise RuntimeError("The target system must ingest its authorised conversation before answering.")
        retrieval = self.store.retrieve(
            self.audit.run_id, self._conversation, test, MemoryStrategy(audit.memory_strategy)
        )
        self._last_retrieval_id = retrieval.evidence.retrieval_id
        intervention = audit.reproducibility.intervention
        if intervention == "remove_memory":
            retrieval.context = []
            retrieval.evidence.selected_memory_ids = []
        elif intervention == "supplement_source_evidence":
            # Oracle diagnostic intervention only: source excerpts, never the
            # evaluator's expected answer. Normal target operation never reads
            # reviewed memories. This run is explicitly marked exploratory.
            memories = self.db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == self._conversation.conversation_id,
                                                                MemoryModel.id.in_(test.supporting_memory_ids))).all()
            source_ids = {key for memory in memories for key in memory.source_message_ids}
            messages = [message for message in self._conversation.messages if message.message_id in source_ids]
            if messages:
                # One source packet is prioritised without changing the frozen
                # retrieval strategy or target configuration. Weak targets still
                # receive exactly one record; the intervention changes its content.
                value = "Authorised source evidence:\n" + "\n".join(
                    f"Source statement ({message.timestamp.isoformat()}): {message.content}" for message in messages
                )
                record = self.db.scalar(select(TargetAgentMemoryModel).where(
                    TargetAgentMemoryModel.run_id == audit.run_id, TargetAgentMemoryModel.canonical_value == value))
                if not record:
                    record = TargetAgentMemoryModel(id=f"TM{uuid4().hex[:20].upper()}", run_id=audit.run_id,
                        source_conversation_id=self._conversation.conversation_id, canonical_value=value,
                        scope="episodic", lifecycle_state="DIAGNOSTIC_ONLY", source_message_ids=[message.message_id for message in messages],
                        observed_at=messages[-1].timestamp, write_order=10000)
                    self.db.add(record)
                    self.db.flush()
                retrieval.context = [value] + retrieval.context
                retrieval.evidence.selected_memory_ids = [record.id] + retrieval.evidence.selected_memory_ids
        if intervention:
            row = self.db.get(TargetAgentRetrievalModel, self._last_retrieval_id)
            row.selected_memory_ids = list(retrieval.evidence.selected_memory_ids)
            row.ranking_evidence = [{**item, "selected": item["memory_id"] in row.selected_memory_ids} for item in row.ranking_evidence]
            self.db.flush()
        private_test = test.model_copy(update={"target_memory_context": retrieval.context})
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
