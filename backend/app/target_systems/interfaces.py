"""Stable lifecycle contract for a conversational system being audited."""
from abc import ABC, abstractmethod

from app.schemas import AuditRun, Conversation, TargetResponse, TestCase


class TargetSystemAdapter(ABC):
    """A target system must ingest, answer, expose safe trace metadata and reset.

    ``reset`` is deliberately explicit even though the built-in system keeps a
    durable run-scoped store: an external adapter must never accidentally reuse
    a previous experiment's memory.  Adapter implementations must accept only
    authorised conversations and must not expose credentials to browser code.
    """

    adapter_id: str
    version: str

    @abstractmethod
    def ingest(self, conversation: Conversation) -> None: ...

    @abstractmethod
    def answer(self, test: TestCase, audit: AuditRun) -> TargetResponse: ...

    @abstractmethod
    def trace(self) -> dict: ...

    @abstractmethod
    def reset(self) -> None: ...
