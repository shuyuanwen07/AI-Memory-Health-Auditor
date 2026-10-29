"""Recovery must preserve source validation and retain both attempt receipts."""
from datetime import datetime, timezone

import pytest

from app.extraction.llm import PipelineRequestError
from app.extraction.relationship_agent import RelationshipAnalysisAgent
from app.schemas import Conversation, ConversationMessage, Memory, MemoryStatus


def fixture_inputs():
    now = datetime.now(timezone.utc)
    conversation = Conversation(conversation_id="C", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id="S1", role="user", content="I live in Perth.", timestamp=now),
        ConversationMessage(message_id="S2", role="user", content="I now live in Brisbane.", timestamp=now),
    ])
    memories = [
        Memory(memory_id="M001", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="I live in Perth.", source_message_ids=["S1"]),
        Memory(memory_id="M002", conversation_id="C", status=MemoryStatus.CANDIDATE,
               canonical_value="I now live in Brisbane.", source_message_ids=["S2"]),
    ]
    return conversation, memories


def edge(prior_evidence):
    return {"relationships": [{"current_memory_id": "M002", "prior_memory_id": "M001",
        "type": "UPDATE", "current_evidence_message_ids": ["S2"],
        "prior_evidence_message_ids": [prior_evidence], "confidence": .9,
        "rationale": "The new office location explicitly replaces the prior location."}]}


class SequencedClient:
    provider = "test"
    model = "fixture"
    last_execution = None

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return result


def test_evidence_mismatch_retries_once_and_preserves_receipts():
    conversation, memories = fixture_inputs()
    client = SequencedClient([edge("S2"), edge("S1")])
    agent = RelationshipAnalysisAgent(client)
    result = agent.analyze(conversation, memories)
    assert len(client.calls) == 2
    assert "endpoint_evidence_mismatch" in client.calls[1]["prompt"]
    assert [entry["status"] for entry in agent.attempt_observations] == ["failed", "completed"]
    assert len(result["relationships"]) == 1 and len(memories[1].relationships) == 1
    assert result["relationships"][0]["evidence_message_ids"] == ["S1", "S2"]


def test_second_invalid_reply_still_fails_closed():
    conversation, memories = fixture_inputs()
    client = SequencedClient([edge("S2"), edge("S2")])
    agent = RelationshipAnalysisAgent(client)
    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation, memories)
    assert len(client.calls) == 2
    assert [entry["status"] for entry in agent.attempt_observations] == ["failed", "failed"]
    assert all(not memory.relationships for memory in memories)


def test_topic_mismatch_retry_never_attaches_the_rejected_edge():
    conversation, memories = fixture_inputs()
    memories[0].canonical_value = "I live in Adelaide."
    memories[1].canonical_value = "The Maple backend uses PostgreSQL."
    client = SequencedClient([edge("S1"), {"relationships": []}])
    agent = RelationshipAnalysisAgent(client)
    result = agent.analyze(conversation, memories)
    assert len(client.calls) == 2
    assert "topic_mismatch" in client.calls[1]["prompt"]
    assert [entry["status"] for entry in agent.attempt_observations] == ["failed", "completed"]
    assert result["relationships"] == []
    assert all(not memory.relationships for memory in memories)


def test_provider_unavailable_does_not_retry():
    conversation, memories = fixture_inputs()
    client = SequencedClient([PipelineRequestError("provider could not be reached")])
    agent = RelationshipAnalysisAgent(client)
    with pytest.raises(PipelineRequestError):
        agent.analyze(conversation, memories)
    assert len(client.calls) == 1
    assert agent.attempt_observations[0]["error_code"] == "provider_unavailable"
