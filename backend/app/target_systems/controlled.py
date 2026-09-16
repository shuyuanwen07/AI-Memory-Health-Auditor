"""The deterministic, persisted controlled target used by Foundation."""
from sqlalchemy.orm import Session

from app.memory_agent import SqlTargetMemoryStore, get_target_memory_writer
from app.schemas import (
    AuditRun, Conversation, MemoryStrategy, TargetMemoryMaintenancePolicy,
    TargetResponse, TestCase,
)
from app.target_ai.providers import HttpTargetAIConnector
from app.target_systems.interfaces import TargetSystemAdapter


class ControlledTargetSystemAdapter(TargetSystemAdapter):
    """Wrap the built-in private memory store behind the target-system seam."""

    adapter_id = "controlled-memory"
    version = "controlled-memory-v1"

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
        )
        self._conversation: Conversation | None = None

    def ingest(self, conversation: Conversation) -> None:
        self.store.ingest(self.audit.run_id, conversation)
        self._conversation = conversation

    def answer(self, test: TestCase, audit: AuditRun) -> TargetResponse:
        if self._conversation is None:
            raise RuntimeError("The target system must ingest its authorised conversation before answering.")
        retrieval = self.store.retrieve(
            self.audit.run_id, self._conversation, test, MemoryStrategy(audit.memory_strategy)
        )
        private_test = test.model_copy(update={"target_memory_context": retrieval.context})
        return HttpTargetAIConnector().execute(private_test, audit)

    def trace(self) -> dict:
        return {"adapter_id": self.adapter_id, "adapter_version": self.version, "run_id": self.audit.run_id}

    def reset(self) -> None:
        # Run-scoped persistence is intentional.  The database lifecycle owns
        # deletion; this method simply drops the in-process session reference.
        self._conversation = None
