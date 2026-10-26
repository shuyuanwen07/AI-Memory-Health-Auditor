"""Target identity analysis is optional, attributed, bounded and reference-blind."""
from datetime import datetime, timezone
import hashlib
import json

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database.session import Base
from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.models import AgentExecutionModel, AuditRunModel, ConversationModel, MemoryModel, TargetAgentMemoryModel
from app.schemas import AuditRun, Conversation, ConversationMessage, TargetConfiguration, TestCase as Case
from app.schemas.target_profile import TargetMemoryProfile
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import memory_input_evidence, private_context_instruction
from app.target_systems.controlled import ControlledTargetSystemAdapter


def setup_target(*, mode="evidence_links", weak=False):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2027, 4, 12, tzinfo=timezone.utc)
    conversation = Conversation(conversation_id="C-ID", created_at=now, authorised=True, messages=[
        ConversationMessage(message_id="S1", role="user", timestamp=now,
                            content="I attended my friend Ada's exhibition in the glass pavilion."),
        ConversationMessage(message_id="S2", role="user", timestamp=now,
                            content="My colleague Ada's exhibition had a glass pavilion and blue banners."),
    ])
    db.add(ConversationModel(id=conversation.conversation_id, authorised=True))
    db.add(AuditRunModel(id="R-ID", conversation_id=conversation.conversation_id, status="CREATED",
                        target_configuration="weak" if weak else "strong", provider="openrouter",
                        model="openai/gpt-6-luna", temperature=0, random_seed=42, test_budget=1,
                        prompt_template_version="identity-test", memory_strategy="weak_first_hit" if weak else "strong_rule_based"))
    db.flush()
    audit = AuditRun(run_id="R-ID", conversation_id=conversation.conversation_id, status="CREATED",
                     target_configuration="weak" if weak else "strong", provider="openrouter",
                     model="openai/gpt-6-luna", temperature=0, random_seed=42, test_budget=1,
                     prompt_template_version="identity-test", created_at=now,
                     memory_strategy="weak_first_hit" if weak else "strong_rule_based",
                     target_memory_profile=TargetMemoryProfile(retrieve_message_context=True,
                                                               identity_analysis=mode, output_token_limit=4096))
    case = Case(test_id="T-ID", run_id=audit.run_id, dimension="accuracy",
                prompt="How many exhibitions have I attended?", expected_behavior="EVALUATOR_PRIVATE_SECRET",
                supporting_memory_ids=["GOLD_ID_SECRET"], generator_version="test",
                target_identity_evidence={"malicious_prior_condition": "EVALUATOR_PRIVATE_SECRET"})
    adapter = ControlledTargetSystemAdapter(db, audit)
    adapter.ingest(conversation)
    return db, audit, case, adapter


def install_transport(monkeypatch, *, invalid=False):
    seen = {"analysis": [], "answer": []}
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-not-a-real-key")

    def analysis(self, **request):
        seen["analysis"].append(request)
        data = json.loads(request["prompt"])
        assert "EVALUATOR_PRIVATE_SECRET" not in str(data)
        assert "GOLD_ID_SECRET" not in str(data)
        assert request["agent_role"] == "target_identity_evidence"
        assert request["max_output_tokens"] == 4096
        self.last_execution = {"provider": "openrouter", "model": "openai/gpt-6-luna",
                               "reported_model": "openai/gpt-6-luna", "status": "parsed",
                               "request_attempts": 1, "reported_input_tokens": 100,
                               "reported_output_tokens": 90, "reported_total_tokens": 190}
        records = data["selected_records"]
        return {"quotes": [{"quote_id": f"Q{i}",
                            "candidate_id": "C999999" if invalid else next(c["candidate_id"] for c in data["quote_candidates"] if c["record_index"] == i and c["quote"] == record["content"])}
                           for i, record in enumerate(records[:2], 1)],
                "mentions": [{"mention_id": "M1", "quote_id": "Q1"}, {"mention_id": "M2", "quote_id": "Q2"}],
                "relations": [{"relation_id": "R1", "left_mention_id": "M1", "right_mention_id": "M2",
                               "level": "likely", "evidence_quote_ids": ["Q1", "Q2"],
                               "cues": ["shared_participant", "distinctive_detail"],
                               "caveat": "A plausible link, not an explicit identity equation."}],
                "limitations": "The event date and unique identity remain uncertain."}

    def answer(self, audit, case, instructions, credential):
        assert case.expected_behavior == "" and case.supporting_memory_ids == []
        assert "EVALUATOR_PRIVATE_SECRET" not in instructions
        assert "GOLD_ID_SECRET" not in instructions
        seen["answer"].append((case, instructions))
        return "These are likely descriptions of one exhibition, with unresolved identity."

    monkeypatch.setattr(PipelineLLMClient, "complete_json", analysis)
    monkeypatch.setattr(HttpTargetAIConnector, "_execute_provider", answer)
    return seen


def test_identity_stage_uses_selected_content_only_and_never_consolidates_memories(monkeypatch):
    seen = install_transport(monkeypatch)
    db, audit, case, adapter = setup_target()
    records_before = [(r.id, r.canonical_value, r.lifecycle_state)
                      for r in db.scalars(select(TargetAgentMemoryModel)).all()]

    def deny_reference_reads(state):
        assert not any(d.get("entity") is MemoryModel for d in getattr(state.statement, "column_descriptions", []))

    event.listen(db, "do_orm_execute", deny_reference_reads)
    try:
        response = adapter.answer(case, audit)
        assert len(seen["analysis"]) == len(seen["answer"]) == 1
        private_case, instructions = seen["answer"][0]
        assert "UNTRUSTED ADVISORY" in instructions
        assert private_case.target_identity_evidence["relations"][0]["level"] == "likely"
        metadata = response.execution_metadata.identity_analysis
        assert metadata["execution"]["reported_total_tokens"] == 190
        assert metadata["relation_count"] == 1
        row = db.scalar(select(AgentExecutionModel))
        assert row.role == "target_identity_evidence" and row.status == "completed"
        assert row.error_diagnostics["total_tokens"] == 190
        assert row.input_refs["test_id"] == case.test_id
        assert records_before == [(r.id, r.canonical_value, r.lifecycle_state)
                                  for r in db.scalars(select(TargetAgentMemoryModel)).all()]
        receipt = response.execution_metadata.memory_input
        expected = json.dumps(private_case.target_identity_evidence, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))
        assert receipt.identity_advisory_sha256 == hashlib.sha256(expected.encode()).hexdigest()
        assert receipt.instruction_sha256 == hashlib.sha256(instructions.encode()).hexdigest()
        assert len(receipt.sent_memory_ids) == 2
    finally:
        event.remove(db, "do_orm_execute", deny_reference_reads)
        db.close()


@pytest.mark.parametrize("mode,weak", [("off", False), ("evidence_links", True)])
def test_disabled_and_weak_conditions_do_not_make_an_extra_call_or_inherit_advisory(monkeypatch, mode, weak):
    seen = install_transport(monkeypatch)
    db, audit, case, adapter = setup_target(mode=mode, weak=weak)
    try:
        response = adapter.answer(case, audit)
        assert seen["analysis"] == []
        assert seen["answer"][0][0].target_identity_evidence is None
        assert "UNTRUSTED ADVISORY" not in seen["answer"][0][1]
        assert response.execution_metadata.memory_input.identity_advisory_sha256 is None
        assert db.scalar(select(AgentExecutionModel)) is None
    finally:
        db.close()


def test_invalid_quote_is_recorded_and_prevents_answering_without_a_silent_fallback(monkeypatch):
    seen = install_transport(monkeypatch, invalid=True)
    db, audit, case, adapter = setup_target()
    try:
        with pytest.raises(PipelineRequestError):
            adapter.answer(case, audit)
        assert len(seen["analysis"]) == 1 and seen["answer"] == []
        row = db.scalar(select(AgentExecutionModel))
        assert row.status == "failed" and row.error_code == "invalid_identity_contract"
        assert row.error_diagnostics["phase"] == "output_validation"
        assert len(db.scalars(select(TargetAgentMemoryModel)).all()) == 2
    finally:
        db.close()


def test_advisory_changes_input_receipt_but_does_not_leak_into_weak_or_public_case():
    from app.schemas.domain import TestCasePublic
    case = Case(test_id="T", run_id="R", dimension="accuracy", prompt="How many events?",
                expected_behavior="PRIVATE", supporting_memory_ids=[], generator_version="test",
                target_memory_context=["I attended a recital."],
                target_identity_evidence={"relations": [{"level": "possible", "caveat": "uncertain"}]})
    strong = private_context_instruction(case, TargetConfiguration.STRONG)
    weak = private_context_instruction(case, TargetConfiguration.WEAK)
    assert "UNTRUSTED ADVISORY" in strong and "UNTRUSTED ADVISORY" not in weak
    assert memory_input_evidence(case, TargetConfiguration.STRONG, strong).identity_advisory_sha256
    public = TestCasePublic.model_validate(case.model_dump()).model_dump()
    assert "target_identity_evidence" not in public and "target_memory_context" not in public
