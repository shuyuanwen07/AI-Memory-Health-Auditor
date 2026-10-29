"""One guarded real-code-path test against disposable PostgreSQL and fake HTTP."""
import httpx
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.api.routes import audit_schema
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.models import AuditRunModel, EvaluationResultModel, TargetResponseModel, TargetAgentMemoryModel
from app.services.ac3_controlled_runner import run_controlled_ac3_step, target_settings_sha256
from app.services.formal_freeze import formal_input_signature, formal_runtime_signature
from test_ac3_atomic_settlement_postgres import prepared, pytestmark
from test_ac3_budget_guard import fake_budget_compile


def test_actual_runner_uses_retrieval_and_saves_result(prepared, monkeypatch):
    engine, frozen, digest = prepared
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM ac3_attempt_receipts'))
        conn.execute(text('DELETE FROM ac3_attempt_scopes'))
        for statement in Path('/app/research_migrations/ac3_budget_guard.sql').read_text().split(';'):
            if statement.strip(): conn.execute(text(statement))
    settings = {}
    with Session(engine) as db:
        for row in db.scalars(select(AuditRunModel)).all():
            row.provider = 'openrouter'
            row.model = 'openai/gpt-6-luna'
            metadata = dict(row.reproducibility_metadata)
            metadata['target_memory_profile'] = {'output_token_limit':256, 'identity_analysis':'off', 'answer_validation':'off'}
            row.reproducibility_metadata = metadata
        db.flush()
        for row in db.scalars(select(AuditRunModel)).all():
            metadata = dict(row.reproducibility_metadata)
            stage = dict(metadata['ac3_staged_suite']); stage['input_sha256'] = formal_input_signature(db, row)
            metadata['ac3_staged_suite'] = stage; row.reproducibility_metadata = metadata
        db.flush()
        for row in db.scalars(select(AuditRunModel)).all():
            settings['H' + row.id[1:]] = target_settings_sha256(audit_schema(row))
        db.add(TargetAgentMemoryModel(id='TM-FIXTURE', run_id='R0', source_conversation_id='C0',
            canonical_value='Fixture fact 0', scope='episodic', lifecycle_state='ACTIVE',
            source_message_ids=['Q0'], write_order=1))
        db.commit()
    runtime = formal_runtime_signature()['source_sha256']
    def compile_fake(path, expected, reservation, snapshot=None):
        plan = fake_budget_compile(path, expected, reservation, snapshot)
        plan['model_configuration'].update(target_provider='openrouter', target_model='openai/gpt-6-luna',
            evaluator_implementation_version=RuleBasedBehaviourEvaluator.VERSION, target_settings_sha256=settings,
            target_output_token_limit=256, runtime_source_sha256=runtime)
        return plan
    seen = []
    def post(_url, **kwargs):
        seen.append(kwargs['json']['messages'])
        return httpx.Response(200, json={'model':'openai/gpt-6-luna',
            'choices':[{'finish_reason':'stop','message':{'content':'Fixture fact 0'}}], 'usage':{'cost':0.001}})
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-fixture-only')
    monkeypatch.setattr('app.target_ai.providers.httpx.post',post)
    with patch('app.services.ac3_controlled_runner.compile_mock', side_effect=compile_fake), \
         patch('scripts.ac3_fixed_suite_adapter.compile_mock', side_effect=compile_fake), \
         patch('app.services.ac3_budget_guard.compile_mock', side_effect=compile_fake), \
         patch('scripts.ac3_database_mapping.compile_mock', side_effect=compile_fake), \
         patch('app.services.ac3_atomic_settlement.compile_mock', side_effect=compile_fake):
        result = run_controlled_ac3_step(engine, frozen_path=frozen, frozen_sha256=digest, reservation='0.002', scope='S',
            history_conversations={f'H{i}':f'C{i}' for i in range(8)}, history_runs={f'H{i}':f'R{i}' for i in range(8)},
            frozen_test_id='H0-Q0', request_key='req-1')
        # Simulate interruption after atomic response settlement and before scoring.
        with Session(engine) as db:
            for existing in db.scalars(select(EvaluationResultModel)).all(): db.delete(existing)
            db.commit()
        recovered = run_controlled_ac3_step(engine, frozen_path=frozen, frozen_sha256=digest, reservation='0.002', scope='S',
            history_conversations={f'H{i}':f'C{i}' for i in range(8)}, history_runs={f'H{i}':f'R{i}' for i in range(8)},
            frozen_test_id='H0-Q0', request_key='req-1')
        assert recovered['status'] == 'completed' and len(seen) == 1
    assert result['status'] == 'completed' and len(seen) == 1
    assert 'Fixture fact 0' in str(seen)
    with Session(engine) as db:
        assert db.scalar(select(TargetResponseModel).where(TargetResponseModel.run_id=='R0')) is not None
        assert db.scalar(select(EvaluationResultModel)) is not None
        assert db.execute(text("SELECT response_metadata_json FROM ac3_request_evidence WHERE request_key='req-1'")).scalar_one()
