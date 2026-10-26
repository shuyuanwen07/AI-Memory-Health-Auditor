"""Synthetic isolation contracts; no real provider calls or human labels."""
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from app.api.routes import audit_schema, conversation_schema
from app.models import AuditRunModel, ConversationModel, MemoryModel, TestCaseModel, TargetAgentMemoryModel
from app.schemas import TestCase, TargetResponse
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.target_ai.providers import HttpTargetAIConnector
from test_quality_workflows import client as workflow_client, run

client = workflow_client


@pytest.mark.parametrize("record_limit", [1, 3])
def test_target_owned_replay_never_queries_auditor_memories_or_passes_answers(client, monkeypatch, record_limit):
    source, _ = run(client)
    package = client.post(f"/api/v1/audits/{source['run_id']}/interventions").json()
    rid = next(item['run_id'] for item in package['runs'] if item['label'] == 'Supplement source evidence')
    seen = []

    def target(self, case, audit):
        assert case.expected_behavior == '' and case.supporting_memory_ids == []
        seen.extend(case.target_memory_context)
        return TargetResponse(response_id='R-ISOLATION', test_id=case.test_id, run_id=audit.run_id,
                              response_text='Synthetic transport only.', model=audit.model, temperature=0, created_at=datetime.now(timezone.utc))

    monkeypatch.setattr(HttpTargetAIConnector, 'execute', target)
    with client.sessions() as db:
        audit = audit_schema(db.get(AuditRunModel, rid))
        audit.target_memory_profile.max_retrieved_records = record_limit
        audit.reproducibility.target_memory_profile.max_retrieved_records = record_limit
        conversation = conversation_schema(db, db.get(ConversationModel, audit.conversation_id))
        saved = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == rid))
        case = TestCase(test_id=saved.id, run_id=rid, dimension=saved.dimension, prompt=saved.prompt,
                        expected_behavior='AUDITOR_PRIVATE_EXPECTATION',
                        supporting_memory_ids=saved.supporting_memory_ids, generator_version=saved.generator_version)
        for memory in db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == audit.conversation_id)):
            memory.canonical_value = 'AUDITOR_PRIVATE_GOLD'
        db.commit()

        def forbid_ground_truth_reads(state):
            assert not any(d.get('entity') is MemoryModel for d in getattr(state.statement, 'column_descriptions', [])), 'Target stage read auditor ground truth'

        event.listen(db, 'do_orm_execute', forbid_ground_truth_reads)
        try:
            adapter = ControlledTargetSystemAdapter(db, audit)
            adapter.ingest(conversation)
            packets = db.scalars(select(TargetAgentMemoryModel).where(TargetAgentMemoryModel.run_id == rid,
                                 TargetAgentMemoryModel.lifecycle_state == 'DIAGNOSTIC_ONLY')).all()
            assert len(packets) == 1
            assert packets[0].source_message_ids == [m.message_id for m in conversation.messages if m.role.strip().lower() == 'user']
            adapter.answer(case, audit)
            assert len(seen) <= record_limit
            assert sum(map(len, seen)) <= audit.target_memory_profile.context_character_budget
            assert seen[0].startswith('Authorised user source history:')
            assert all(m.content in seen[0] for m in conversation.messages if m.role.strip().lower() == 'user')
            assert 'AUDITOR_PRIVATE_GOLD' not in str(seen)
            assert 'AUDITOR_PRIVATE_EXPECTATION' not in str(seen)
        finally:
            event.remove(db, 'do_orm_execute', forbid_ground_truth_reads)


def test_source_replay_without_user_messages_is_explicitly_rejected_before_ingest(client, monkeypatch):
    source, _ = run(client)
    package = client.post(f"/api/v1/audits/{source['run_id']}/interventions").json()
    rid = next(item['run_id'] for item in package['runs'] if item['label'] == 'Supplement source evidence')
    with client.sessions() as db:
        audit = audit_schema(db.get(AuditRunModel, rid))
        conversation = conversation_schema(db, db.get(ConversationModel, audit.conversation_id))
        assistant_only = conversation.model_copy(update={'messages': [m.model_copy(update={'role': 'assistant'}) for m in conversation.messages]})
        adapter = ControlledTargetSystemAdapter(db, audit)
        monkeypatch.setattr(adapter.store, 'ingest', lambda *args: pytest.fail('Unsupported replay must be rejected before ingest.'))
        with pytest.raises(HTTPException) as denied:
            adapter.ingest(assistant_only)
        assert denied.value.status_code == 422
        assert 'requires authorised user messages' in denied.value.detail
        assert db.scalar(select(TargetAgentMemoryModel.id).where(TargetAgentMemoryModel.run_id == rid)) is None


def test_oversized_source_replay_is_rejected_before_ingest_or_model_work(client, monkeypatch):
    source, _ = run(client)
    package = client.post(f"/api/v1/audits/{source['run_id']}/interventions").json()
    rid = next(item['run_id'] for item in package['runs'] if item['label'] == 'Supplement source evidence')
    with client.sessions() as db:
        audit = audit_schema(db.get(AuditRunModel, rid))
        audit.target_memory_profile.context_character_budget = 256
        audit.reproducibility.target_memory_profile.context_character_budget = 256
        conversation = conversation_schema(db, db.get(ConversationModel, audit.conversation_id))
        adapter = ControlledTargetSystemAdapter(db, audit)
        monkeypatch.setattr(adapter.store, 'ingest', lambda *args: pytest.fail('Oversized replay must not start memory ingestion.'))
        with pytest.raises(HTTPException) as denied:
            adapter.ingest(conversation)
        assert denied.value.status_code == 422
        assert 'memory context budget' in denied.value.detail
        assert db.scalar(select(TargetAgentMemoryModel.id).where(TargetAgentMemoryModel.run_id == rid)) is None


def test_target_ingest_requires_permission_before_preparing_replay(client, monkeypatch):
    source, _ = run(client)
    package = client.post(f"/api/v1/audits/{source['run_id']}/interventions").json()
    rid = next(item['run_id'] for item in package['runs'] if item['label'] == 'Supplement source evidence')
    with client.sessions() as db:
        audit = audit_schema(db.get(AuditRunModel, rid))
        conversation = conversation_schema(db, db.get(ConversationModel, audit.conversation_id)).model_copy(update={'authorised':False})
        adapter = ControlledTargetSystemAdapter(db, audit)
        monkeypatch.setattr(adapter.store, 'ingest', lambda *args: pytest.fail('Unapproved data must not reach ingestion.'))
        with pytest.raises(HTTPException) as denied:
            adapter.ingest(conversation)
        assert denied.value.status_code == 403
        assert db.scalar(select(TargetAgentMemoryModel.id).where(TargetAgentMemoryModel.run_id == rid)) is None
