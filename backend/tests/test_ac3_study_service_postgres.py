"""Full synthetic study: real app/database code with fixed fake provider only."""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from sqlalchemy import text
from app.schemas import AuditRun
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.test_generator.rule_based import RuleBasedTestGenerator
from app.memory_agent.writers import RuleBasedTargetMemoryWriter
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.services.ac3_controlled_runner import _SETTINGS_FIELDS, target_settings_sha256
from app.services.ac3_schema import ac3_schema_migration_sha256
from app.services.formal_freeze import formal_runtime_signature
from app.services.ac3_study_service import run_study
from scripts.ac3_fixed_suite_adapter import sha
from test_ac3_atomic_settlement_postgres import prepared, pytestmark
from test_ac3_reviewed_source_import import fixture_plan


def test_full_preparation_run_and_blind_export_with_fake_provider(prepared, fixture_plan, tmp_path, monkeypatch):
    engine, _, _ = prepared
    original, _, base_compile = fixture_plan
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE ac3_attempt_receipts'))
        conn.execute(text('DROP TABLE ac3_attempt_scopes'))
    audit=AuditRun(run_id='fixture',conversation_id='fixture',status='CREATED',target_configuration='strong',
        provider='openrouter',model='openai/gpt-6-luna',temperature=0,random_seed=42,test_budget=1,
        prompt_template_version='fixture',memory_strategy='strong_rule_based',created_at=datetime.now(timezone.utc),
        target_memory_profile={'output_token_limit':256}, target_memory_writer_version=RuleBasedTargetMemoryWriter.VERSION,
        target_system_adapter_version=ControlledTargetSystemAdapter.version)
    setup=audit.model_dump(mode='json',include=_SETTINGS_FIELDS)
    cfg={'audit_setup':setup, 'target_provider':setup['provider'],'target_model':setup['model'],
         'evaluator_provider':setup['evaluator_provider'],'evaluator_model':setup['evaluator_model'],
         'pipeline_provider':setup['pipeline_provider'],'pipeline_model':setup['pipeline_model'],
         'target_strategy':setup['memory_strategy'],'target_output_token_limit':256,
         'target_settings_sha256':target_settings_sha256(audit),'ledger_schema_sha256':ac3_schema_migration_sha256(),
         'runtime_source_sha256':formal_runtime_signature()['source_sha256'],
         'evaluator_implementation_version':RuleBasedBehaviourEvaluator.VERSION,
         'pipeline_implementation_version':RuleBasedTestGenerator.VERSION,
         'synthetic_source_timestamp_utc':'2000-01-01T00:00:00Z'}
    suite=json.loads(original.read_text())['suite']
    frozen=tmp_path/'full-synthetic-frozen.json'
    frozen.write_text(json.dumps({'suite':suite,'format':'ac3-prospective-frozen-suite-v1',
        'frozen_at_utc':'2000-01-01T00:00:00+00:00','protocol':{'model_configuration':cfg,
        'budget':{'max_new_estimated_usd':1},
        'thresholds':{'failure_detection_recall_min':0.75,'failure_classification_accuracy_min':0.8,
                      'test_validity_min':0.9,'false_positive_rate_max':0.1},
        'minimum_decided_coverage':0.8,'minimum_human_pass_count':1,'minimum_human_failure_count':1,
        'minimum_independent_histories':1}}))
    digest=sha(frozen.read_bytes())
    def compile_fake(path, expected, reservation, snapshot=None):
        # Test-only plan and declarations; no user review is implied.
        plan=base_compile(original,sha(original.read_bytes()),reservation,snapshot)
        plan.update(frozen_sha256=expected,model_called=False,max_new_estimated_usd='1')
        plan['model_configuration'].update(cfg)
        return plan
    calls=[]
    def post(_url,**kwargs):
        calls.append(kwargs['json']['messages'])
        return httpx.Response(200,json={'model':'openai/gpt-6-luna',
          'choices':[{'finish_reason':'stop','message':{'content':'synthetic answer'}}], 'usage':{'cost':0.001}})
    monkeypatch.setenv('OPENROUTER_API_KEY','fixture-only')
    monkeypatch.setattr('app.target_ai.providers.httpx.post',post)
    modules=('app.services.ac3_study_service','app.services.ac3_prepare_system','app.services.ac3_reviewed_source_import',
        'scripts.ac3_database_mapping','scripts.ac3_fixed_suite_adapter','app.services.ac3_budget_guard',
        'app.services.ac3_controlled_runner','app.services.ac3_atomic_settlement','scripts.export_ac3_blind_review',
        'scripts.analyze_ac3_heldout')
    from contextlib import ExitStack
    with ExitStack() as stack:
        for module in modules: stack.enter_context(patch(module+'.compile_mock',side_effect=compile_fake))
        result=run_study(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0.002',results_root=tmp_path)
        assert result['status']=='awaiting_human_review', result
        assert result['completed']==8 and len(calls)==8
        again=run_study(engine,frozen_path=frozen,frozen_sha256=digest,reservation='0.002',results_root=tmp_path)
        assert again['status']=='awaiting_human_review' and len(calls)==8
        # Simulate two independently completed human reviews; no real human is
        # claimed. The real aggregate analyzer must receive these records.
        folder=Path(result['review_dir'])
        docs=[json.loads((folder/f'reviewer-{i}.json').read_text()) for i in (1,2)]
        for slot,doc in enumerate(docs,1):
            doc['reviewer_declaration'].update(reviewer_label=f'synthetic-{slot}',completed_by_human=True,
                completed_independently=True,has_seen_automatic_results=False,used_ai_assistance=False)
            for entry in doc['decisions']:
                entry.update(verdict='pass',failure_dimension=None,rationale='Synthetic test rationale')
        monkeypatch.setenv('AC3_SOURCE_ROOT',str(tmp_path)); monkeypatch.setenv('AC3_RESULTS_ROOT',str(tmp_path))
        from app.api.ac3_study_routes import ReviewSubmission, submit_blind_reviews, get_study_summary
        outcome=submit_blind_reviews(digest,ReviewSubmission(reviewer_1_json=json.dumps(docs[0]),reviewer_2_json=json.dumps(docs[1])))
        assert outcome['status']=='reviewed'
        summary=get_study_summary(digest)
        assert summary['cases']==8 and 'history_bootstrap' in summary and 'evidence_sufficiency' in summary
        assert 'synthetic answer' not in json.dumps(summary)
    folder=Path(result['review_dir'])
    assert json.loads((folder/'reviewer-1.json').read_text())['reviewer_declaration']['completed_by_human'] is False
    assert len(json.loads((folder/'blind-packet.json').read_text())['cases'])==8
