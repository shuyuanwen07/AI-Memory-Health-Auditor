"""End-to-end preparation in disposable SQLite, with synthetic human fixtures."""
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.entities import Base
from app.models import AuditRunModel, TestCaseModel
from app.schemas import AuditRun
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS, target_settings_sha256
from app.services.ac3_prepare_system import prepare_staged_ac3
from app.memory_agent.writers import RuleBasedTargetMemoryWriter
from app.target_systems.controlled import ControlledTargetSystemAdapter
from test_ac3_reviewed_source_import import fixture_plan


def test_prepares_all_reviewed_sources_and_audits_idempotently(fixture_plan):
    frozen,digest,base_compile = fixture_plan
    engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
    audit=AuditRun(run_id='fixture',conversation_id='fixture',status='CREATED',target_configuration='strong',
        provider='openrouter',model='openai/gpt-6-luna',temperature=0,random_seed=42,test_budget=1,
        prompt_template_version='fixture',memory_strategy='strong_rule_based',created_at=datetime.now(timezone.utc),
        target_memory_profile={'output_token_limit':256}, target_memory_writer_version=RuleBasedTargetMemoryWriter.VERSION,
        target_system_adapter_version=ControlledTargetSystemAdapter.version)
    setup=audit.model_dump(mode='json',include=_SETTINGS_FIELDS)
    def compile_fake(path, expected, reservation, snapshot=None):
        plan=base_compile(path,expected,reservation,snapshot)
        plan['model_configuration'].update({'audit_setup':setup,'target_provider':setup['provider'],'target_model':setup['model'],
            'evaluator_provider':setup['evaluator_provider'],'evaluator_model':setup['evaluator_model'],
            'pipeline_provider':setup['pipeline_provider'],'pipeline_model':setup['pipeline_model'],
            'target_strategy':setup['memory_strategy'],'target_output_token_limit':256,'target_settings_sha256':target_settings_sha256(audit)})
        return plan
    with patch('app.services.ac3_prepare_system.compile_mock',side_effect=compile_fake), \
         patch('app.services.ac3_reviewed_source_import.compile_mock',side_effect=compile_fake), \
         patch('scripts.ac3_database_mapping.compile_mock',side_effect=compile_fake):
        result=prepare_staged_ac3(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')
        assert result['status']=='staged' and result['history_count']==8 and result['test_count']==8
        assert prepare_staged_ac3(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0')['staging_status']=='already_staged'
    with Session(engine) as db:
        assert len(db.scalars(select(AuditRunModel)).all())==8
        assert len(db.scalars(select(TestCaseModel)).all())==8
        assert all(row.status=='RESEARCH_STAGED' for row in db.scalars(select(AuditRunModel)))
    engine.dispose()
