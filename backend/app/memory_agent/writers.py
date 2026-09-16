"""Independent writers for a controlled target agent's private memory store.

These writers intentionally operate on the authorised conversation, never on
human-reviewed ground truth.  The store owns persistence and retrieval; a
writer only decides which records the target Agent writes while ingesting a
conversation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.extraction.llm_extractor import _EXTRACTION_SCHEMA, _ExtractionPayload
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.schemas import Conversation, Memory, MemoryRelationship, MemoryStatus, RelationshipType, TargetMemoryWriterKind
from app.services.interfaces import MemoryExtractor


class LLMTargetMemoryWriter(MemoryExtractor):
    """Structured LLM writer for the memory system under test.

    It is deliberately not the Auditor's ``LLMMemoryExtractor``: its prompt
    says it is a target Agent deciding what to retain, and it is selected only
    for that Agent's private store.  The returned structure is still checked
    locally for source and relationship integrity before persistence.
    """

    VERSION = "llm-target-memory-writer-v1"

    def __init__(self, provider: str, model: str | None = None, client: PipelineLLMClient | None = None):
        self.client = client or PipelineLLMClient(provider, model)

    def extract(self, conversation: Conversation) -> list[Memory]:
        if not conversation.authorised:
            raise PipelineRequestError("Authorisation is required before a target Agent can ingest conversation data.", 422)
        messages = [message for message in conversation.messages if message.role.strip().lower() == "user"]
        payload = self.client.complete_json(
            instructions=(
                "You operate the private long-term memory of a conversational target Agent. "
                "Write only durable or currently relevant facts explicitly stated by the user. "
                "Do not see or use an Auditor, ground truth, tests, expected answers, or reviewer labels. "
                "When a later fact replaces an earlier fact, link the newer record to the older record with UPDATE. "
                "For incompatible unresolved records use CONFLICT; for a narrow current requirement overriding a "
                "general preference use CONTEXTUAL_OVERRIDE. Return only the requested JSON."
            ),
            prompt=self._prompt(messages), schema_name="target_agent_memory_write", schema=_EXTRACTION_SCHEMA,
        )
        try:
            extracted = _ExtractionPayload.model_validate(payload)
        except Exception as exc:
            raise PipelineRequestError("The target memory writer returned data that does not match the required contract.") from exc
        self._validate(extracted.memories, messages)
        return [
            Memory(
                memory_id=item.memory_id, conversation_id=conversation.conversation_id,
                canonical_value=item.canonical_value, status=MemoryStatus.CANDIDATE,
                source_message_ids=item.source_message_ids, timestamp=item.timestamp,
                relationships=[MemoryRelationship(type=relation.type, target_memory_id=relation.target_memory_id) for relation in item.relationships],
            )
            for item in extracted.memories
        ]

    @staticmethod
    def _prompt(messages: list[Any]) -> str:
        serialised = [
            {"message_id": message.message_id, "timestamp": message.timestamp.isoformat(), "content": message.content}
            for message in messages
        ]
        return "Ingest these chronological authorised user messages into your private memory. Return {\"memories\":[...]} exactly.\n\nUSER MESSAGES:\n" + json.dumps(serialised, ensure_ascii=False)

    @staticmethod
    def _validate(memories: list[Any], messages: list[Any]) -> None:
        ids = [memory.memory_id for memory in memories]
        message_ids = {message.message_id for message in messages}
        if len(ids) != len(set(ids)):
            raise PipelineRequestError("The target memory writer returned duplicate memory IDs.")
        for memory in memories:
            if not set(memory.source_message_ids).issubset(message_ids):
                raise PipelineRequestError("The target memory writer referenced a message outside the authorised conversation.")
            for relationship in memory.relationships:
                if relationship.target_memory_id == memory.memory_id or relationship.target_memory_id not in ids:
                    raise PipelineRequestError("The target memory writer returned an invalid relationship reference.")


def default_target_memory_writer_kind() -> TargetMemoryWriterKind:
    """Read the environment only while a new AuditRun is being created."""
    choice = os.getenv("TARGET_MEMORY_WRITER", "rule_based").strip().lower()
    try:
        return TargetMemoryWriterKind(choice)
    except ValueError as exc:
        raise PipelineRequestError(
            "TARGET_MEMORY_WRITER must be rule_based or llm_structured.", 500
        ) from exc


def get_target_memory_writer(
    provider: str,
    model: str | None = None,
    writer_kind: TargetMemoryWriterKind | str | None = None,
) -> MemoryExtractor:
    """Resolve a writer from a persisted AuditRun configuration.

    ``writer_kind`` should always be supplied by execution code.  The optional
    fallback is retained solely for API compatibility with older callers and
    resolves the environment default; it must not be used once a run exists.
    """
    choice = (TargetMemoryWriterKind(writer_kind).value if writer_kind is not None
              else default_target_memory_writer_kind().value)
    if choice == "rule_based":
        return RuleBasedMemoryExtractor()
    if choice == "llm_structured":
        if provider == "rule_based":
            raise PipelineRequestError("A structured LLM target-memory writer requires an OpenAI, DeepSeek, or Gemini pipeline provider.", 422)
        return LLMTargetMemoryWriter(provider, model)
    # The enum validation above makes this unreachable, but keep a clear
    # boundary error if an untyped implementation calls this in future.
    raise PipelineRequestError("Target memory writer must be rule_based or llm_structured.", 500)
