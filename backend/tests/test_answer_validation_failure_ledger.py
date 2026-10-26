"""Synthetic route receipt check; no provider or external calls."""
from fastapi import HTTPException
from sqlalchemy import select
from app.api import routes
from app.models import AgentExecutionModel, AuditRunModel, TargetResponseModel
from app.services.agent_trace import record_agent_execution


def test_review_failure_is_chain_failure_and_not_third_provider_request(saved_suite, monkeypatch):
    client, sessions, runs, _ = saved_suite
    original = routes.get_target_system_adapter

    class FailedReview:
        def __init__(self, db, audit):
            self.db, self.audit = db, audit
            self.delegate = original(db, audit)
        def ingest(self, conversation):
            return self.delegate.ingest(conversation)
        def trace(self):
            return self.delegate.trace()
        def reset(self):
            return self.delegate.reset()
        def answer(self, test, audit):
            common = dict(provider=audit.provider.value, model=audit.model,
                prompt_template_version='synthetic-ledger', instructions='', prompt='', schema=None,
                input_payload={}, input_refs={'test_id': test.test_id}, output_data=None,
                run_id=audit.run_id, conversation_id=audit.conversation_id)
            draft = record_agent_execution(self.db, role='target_answer_draft', status='completed',
                execution={'request_attempts': 1}, **common)
            review = record_agent_execution(self.db, role='target_answer_validation', status='failed',
                execution={'request_attempts': 1}, **common)
            error = HTTPException(502, 'The required target answer validation failed.')
            error.target_execution = dict(test_id=test.test_id, provider=audit.provider.value,
                model=audit.model, reported_model=audit.model, request_attempts=1,
                failure_stage='target_answer_validation', primary_status='completed',
                draft_execution_id=draft.id, answer_validation={'execution_id': review.id},
                error_summary='The completed draft failed its required source review.')
            raise error

    monkeypatch.setattr(routes, 'get_target_system_adapter', FailedReview)
    response = client.post(f'/api/v1/audits/{runs[0]}/execute')
    assert response.status_code == 502
    with sessions() as db:
        rows = db.scalars(select(AgentExecutionModel).where(AgentExecutionModel.run_id == runs[0])).all()
        draft = next(row for row in rows if row.role == 'target_answer_draft')
        review = next(row for row in rows if row.role == 'target_answer_validation')
        chain = next(row for row in rows if row.role == 'target_answer_chain')
        assert chain.status == 'failed' and chain.attempt_count == 0
        assert chain.error_code == 'TargetAnswerValidationFailed'
        assert chain.input_refs['draft_execution_id'] == draft.id
        assert chain.input_refs['validation_execution_id'] == review.id
        assert chain.input_refs['execution_origin'] == 'chain_failure_no_additional_request'
        assert chain.handoff_from == 'target_answer_validation'
        assert not any(row.role == 'target_answer' for row in rows)
        assert db.get(AuditRunModel, runs[0]).status == 'FAILED'
        assert db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id == runs[0])) is None
