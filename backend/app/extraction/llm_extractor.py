"""LLM-backed memory extraction with local, strict contract validation."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.schemas import Conversation, Memory, MemoryRelationship, MemoryStatus, RelationshipType
from app.services.interfaces import MemoryExtractor


class _RelationshipPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    type: RelationshipType
    target_memory_id: Annotated[str, Field(pattern=r"^M\d{3}$")]


class _MemoryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    memory_id: Annotated[str, Field(pattern=r"^M\d{3}$")]
    canonical_value: Annotated[str, Field(min_length=3, max_length=2000)]
    source_message_ids: Annotated[list[str], Field(min_length=1)]
    timestamp: datetime | None = None
    relationships: list[_RelationshipPayload] = Field(default_factory=list)


class _ExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memories: list[_MemoryPayload]


_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["memories"],
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["memory_id", "canonical_value", "source_message_ids", "timestamp", "relationships"],
                "properties": {
                    "memory_id": {"type": "string", "pattern": "^M[0-9]{3}$"},
                    "canonical_value": {"type": "string"},
                    "source_message_ids": {"type": "array", "items": {"type": "string"}},
                    "timestamp": {"type": ["string", "null"]},
                    "relationships": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["type", "target_memory_id"],
                        "properties": {
                            "type": {"type": "string", "enum": [item.value for item in RelationshipType]},
                            "target_memory_id": {"type": "string", "pattern": "^M[0-9]{3}$"},
                        },
                    }},
                },
            },
        },
    },
}


class LLMMemoryExtractor(MemoryExtractor):
    """Extract candidate memories using a configured backend-only LLM provider."""

    VERSION = "llm-structured-v1"

    def __init__(self, client: PipelineLLMClient | None = None) -> None:
        self.client = client or PipelineLLMClient()

    def extract(self, conversation: Conversation) -> list[Memory]:
        if not conversation.authorised:
            raise PipelineRequestError("Authorisation is required before conversation data can be processed.", 422)
        messages = [message for message in conversation.messages if message.role.strip().lower() == "user"]
        prompt = self._prompt(messages)
        payload = self.client.complete_json(
            instructions=(
                "You extract durable user memories for an AI memory audit. Use only user-authored "
                "messages supplied in the request; never infer facts. Return only the requested JSON object. "
                "A relationship points from a newer/current memory to an earlier memory: UPDATE for "
                "supersession, CONFLICT for incompatible facts, CONTEXTUAL_OVERRIDE for a current "
                "requirement overriding a general preference."
            ),
            prompt=prompt,
            schema_name="memory_extraction",
            schema=_EXTRACTION_SCHEMA,
        )
        try:
            extracted = _ExtractionPayload.model_validate(payload)
        except ValidationError as exc:
            raise PipelineRequestError("The configured pipeline model returned memory data that does not match the required contract.") from exc
        self._validate_references(extracted.memories, messages)
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
        import json
        serialised = [
            {"message_id": message.message_id, "timestamp": message.timestamp.isoformat(), "content": message.content}
            for message in messages
        ]
        return (
            "Extract only useful long-term user memories from these chronological messages. Assign unique "
            "IDs M001, M002, etc. Preserve source_message_ids and use timestamps only when supported by "
            "the source. Return {\"memories\":[...]} exactly.\n\nUSER MESSAGES:\n"
            f"{json.dumps(serialised, ensure_ascii=False)}"
        )

    @staticmethod
    def _validate_references(memories: list[_MemoryPayload], messages: list[Any]) -> None:
        ids = [memory.memory_id for memory in memories]
        message_ids = {message.message_id for message in messages}
        if len(ids) != len(set(ids)):
            raise PipelineRequestError("The configured pipeline model returned duplicate memory IDs.")
        for memory in memories:
            if not set(memory.source_message_ids).issubset(message_ids):
                raise PipelineRequestError("The configured pipeline model referenced a message outside the authorised conversation.")
            for relationship in memory.relationships:
                if relationship.target_memory_id == memory.memory_id or relationship.target_memory_id not in ids:
                    raise PipelineRequestError("The configured pipeline model returned an invalid memory relationship reference.")
