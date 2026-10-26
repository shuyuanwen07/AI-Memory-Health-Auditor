"""Safe failure diagnostics for the independent memory-review Agent."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import Base
from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.extraction.memory_review_agent import IndependentMemoryReviewAgent, _review_output_token_budget
from app.extraction.relationship_agent import RelationshipAnalysisAgent
from app.models import AgentExecutionModel
from app.schemas import AgentExecution, Conversation, ConversationMessage, Memory, MemoryStatus
from app.services.agent_trace import agent_execution_schema, record_agent_execution


def _source_and_memory():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        conversation_id="C-DIAGNOSTICS", created_at=now, authorised=True,
        messages=[ConversationMessage(
            message_id="SYN101", role="user", content="I live in Adelaide.", timestamp=now,
        )],
    )
    memory = Memory(
        memory_id="M001", conversation_id=conversation.conversation_id,
        canonical_value="I live in Adelaide.", status=MemoryStatus.CANDIDATE,
        source_message_ids=["SYN101"], confidence=0.9,
    )
    return conversation, [memory]


class _FakeClient:
    provider = "ollama"
    model = "qwen3:1.7b"

    def __init__(self, result=None, error=None, execution=None):
        self.result = result
        self.error = error
        self.last_execution = execution or {
            "provider": self.provider, "model": self.model,
            "status": "parsed", "reported_done_reason": "stop",
        }

    def complete_json(self, **_kwargs):
        if self.error:
            raise self.error
        return self.result


def _finding(**overrides):
    return {
        "kind": "uncertain",
        "memory_ids": ["M001"],
        "evidence_message_ids": ["SYN101"],
        "suggested_memory": None,
        "reason": "The source context may need further review.",
        "confidence": 0.4,
        **overrides,
    }


def test_schema_validation_receipt_keeps_only_safe_location_and_type():
    conversation, memories = _source_and_memory()
    raw_model_text = "PRIVATE_RAW_MODEL_OUTPUT"
    agent = IndependentMemoryReviewAgent(_FakeClient(result={
        "findings": [_finding(kind=raw_model_text)],
    }))

    with pytest.raises(PipelineRequestError):
        agent.review(conversation, memories)

    observation = agent.last_observation
    assert observation["error_diagnostics"] == {
        "phase": "schema_validation",
        "category": "structured_output_validation",
        "provider_done_reason": "stop",
        "validation_errors": [{"location": ["findings", 0, "kind"], "type": "literal_error"}],
    }
    assert raw_model_text not in json.dumps(observation["error_diagnostics"])
    assert observation["output_data"] is None


def test_invalid_source_reference_is_categorized_without_relaxing_evidence_checks():
    conversation, memories = _source_and_memory()
    agent = IndependentMemoryReviewAgent(_FakeClient(result={
        "findings": [_finding(evidence_message_ids=["OUTSIDE-SOURCE"])],
    }))

    with pytest.raises(PipelineRequestError):
        agent.review(conversation, memories)

    assert agent.last_observation["error_diagnostics"] == {
        "phase": "evidence_reference_validation",
        "category": "invalid_message_reference",
        "provider_done_reason": "stop",
    }
    assert agent.last_observation["output_data"] is None


def test_provider_length_failure_receipt_includes_done_reason():
    conversation, memories = _source_and_memory()
    client = _FakeClient(
        error=PipelineRequestError("The local pipeline model did not complete a usable answer."),
        execution={
            "provider": "ollama", "model": "qwen3:1.7b", "status": "failed",
            "error_code": "PipelineRequestError", "reported_done_reason": "length",
        },
    )
    agent = IndependentMemoryReviewAgent(client)

    with pytest.raises(PipelineRequestError):
        agent.review(conversation, memories)

    assert agent.last_observation["error_diagnostics"] == {
        "phase": "provider_completion",
        "category": "length_terminated",
        "provider_done_reason": "length",
    }


def test_memory_review_output_budget_scales_with_input_and_stays_bounded():
    conversation, memories = _source_and_memory()
    client = _FakeClient(result={"findings": []})
    requested = {}
    client.complete_json = lambda **kwargs: requested.update(kwargs) or {"findings": []}

    IndependentMemoryReviewAgent(client).review(conversation, memories)

    assert requested["max_output_tokens"] == 2048
    assert _review_output_token_budget(100, 100) == 4096
    assert _review_output_token_budget(-2, -5) == 2048


def test_ollama_done_reason_is_retained_on_incomplete_structured_reply(monkeypatch):
    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(lambda *_args: {
        "model": "qwen3:1.7b", "done": False, "done_reason": "length",
        "message": {"content": "{}"},
    }))
    for role, expected in (
        ("independent_memory_review", "length"),
        ("memory_extraction", None),
        ("relationship_analysis", None),
    ):
        client = PipelineLLMClient("ollama", "qwen3:1.7b")
        with pytest.raises(PipelineRequestError):
            client.complete_json(
                instructions="Return JSON.", prompt="{}", schema_name="review",
                schema={"type": "object"}, agent_role=role,
            )
        assert client.last_execution["status"] == "failed"
        assert client.last_execution.get("reported_done_reason") == expected


def test_relationship_analysis_receipt_does_not_retain_done_reason(monkeypatch):
    monkeypatch.setattr(PipelineLLMClient, "_post", staticmethod(lambda *_args: {
        "model": "qwen3:1.7b", "done": True, "done_reason": "stop",
        "message": {"content": json.dumps({"relationships": []})},
    }))
    conversation, memories = _source_and_memory()
    agent = RelationshipAnalysisAgent(PipelineLLMClient("ollama", "qwen3:1.7b"))

    assert agent.analyze(conversation, memories) == {"relationships": []}
    assert "reported_done_reason" not in agent.last_observation["execution"]


def test_agent_execution_persists_safe_failure_diagnostics():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    diagnostics = {
        "phase": "schema_validation", "category": "structured_output_validation",
        "validation_errors": [{"location": ["findings", 0, "kind"], "type": "literal_error"}],
        "provider_done_reason": "stop",
    }
    with Session(engine) as db:
        row = record_agent_execution(
            db, role="independent_memory_review", provider="ollama", model="qwen3:1.7b",
            prompt_template_version="independent-memory-review-agent-v1",
            instructions="", prompt="", schema=None, input_payload={}, input_refs={},
            output_data=None, status="failed", error_code="ValidationError",
            error_summary="The independent memory review could not be validated.",
            error_diagnostics=diagnostics,
        )
        db.commit()
        saved = db.get(AgentExecutionModel, row.id)
        response = AgentExecution.model_validate(agent_execution_schema(saved))
        assert response.error_diagnostics == diagnostics
    engine.dispose()
