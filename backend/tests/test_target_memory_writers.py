from datetime import datetime, timezone

import pytest

from app.memory_agent.writers import LLMTargetMemoryWriter, get_target_memory_writer
from app.extraction.llm import PipelineRequestError
from app.schemas import Conversation, ConversationMessage


class FakeClient:
    def complete_json(self, **_: object):
        return {"memories": [{
            "memory_id": "M001", "canonical_value": "The user is based in Sydney.",
            "source_message_ids": ["MSG001"], "timestamp": None, "relationships": [],
        }]}


def conversation() -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(conversation_id="C-WRITER", authorised=True, created_at=now, messages=[
        ConversationMessage(message_id="MSG001", role="user", content="I am based in Sydney.", timestamp=now),
    ])


def test_llm_writer_uses_only_authorised_source_and_returns_valid_records():
    records = LLMTargetMemoryWriter("openai", client=FakeClient()).extract(conversation())
    assert [record.canonical_value for record in records] == ["The user is based in Sydney."]
    assert records[0].source_message_ids == ["MSG001"]


def test_writer_mode_defaults_to_deterministic_and_rejects_invalid_mode(monkeypatch):
    monkeypatch.delenv("TARGET_MEMORY_WRITER", raising=False)
    assert get_target_memory_writer("rule_based").__class__.__name__ == "RuleBasedMemoryExtractor"
    monkeypatch.setenv("TARGET_MEMORY_WRITER", "llm_structured")
    with pytest.raises(PipelineRequestError):
        get_target_memory_writer("rule_based")
    monkeypatch.setenv("TARGET_MEMORY_WRITER", "not-a-writer")
    with pytest.raises(PipelineRequestError):
        get_target_memory_writer("openai")
