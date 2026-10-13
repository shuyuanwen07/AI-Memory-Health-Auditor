"""Method ablations share reviewed facts; reviewer ablations share questions."""
from types import SimpleNamespace

from app.api.routes import eval_schema
from app.database.session import get_db
from app.main import app
from test_input_and_relationship_guards import client_for


def test_explicit_reviewer_ablation_preserves_shared_questions_and_real_configuration(tmp_path, monkeypatch):
    from app.test_generator.rule_based import RuleBasedTestGenerator
    generated = []

    def generator(provider, model, semantic_review_provider=None, semantic_review_model=None):
        generated.append((provider, model, semantic_review_provider, semantic_review_model))
        return RuleBasedTestGenerator()

    monkeypatch.setattr('app.api.routes.get_test_generator', generator)
    with client_for(tmp_path) as client:
        try:
            cid = client.post('/api/v1/conversations', json={'authorised': True, 'pasted_text': '[User] I used MySQL before, but now use PostgreSQL.'}).json()['conversation_id']
            memories = client.post(f'/api/v1/conversations/{cid}/extract', json={'provider': 'rule_based'}).json()
            provenance = client.get(f'/api/v1/conversations/{cid}').json()['extraction_provenance']
            assert provenance['provider'] == 'rule_based'
            client.post(f'/api/v1/conversations/{cid}/confirm-ground-truth', json={'confirmed_memory_ids': [m['memory_id'] for m in memories]})
            exp = client.post('/api/v1/experiments', json={'conversation_id': cid, 'label': 'Reviewer ablation', 'test_suite_configuration': {
                'pipeline_provider': 'openrouter', 'pipeline_model': 'fixture/generator', 'compare_evaluators': True,
                'evaluator_provider': 'openrouter', 'evaluator_model': 'fixture/judge', 'test_budget': 4,
            }}).json()
            runs = []
            for evaluator in ('rule_based', 'openrouter'):
                r = client.post('/api/v1/audits', json={'conversation_id': cid, 'experiment_id': exp['experiment_id'],
                    'provider': 'rule_based', 'target_configuration': 'strong', 'evaluator_provider': evaluator,
                    'evaluator_model': 'fixture/judge',
                    **({'shared_answer_source_run_id': runs[0]['run_id']} if runs else {})})
                assert r.status_code == 201, r.text
                runs.append(r.json())
            assert [r['evaluator_provider'] for r in runs] == ['rule_based', 'openrouter']
            assert all(r['reproducibility']['extraction_provenance'] == provenance for r in runs)
            assert [r['reproducibility']['auditor_method'] for r in runs] == ['model_generation', 'hybrid']
            a = client.post(f"/api/v1/audits/{runs[0]['run_id']}/generate-tests")
            assert a.status_code == 200, a.text
            b = client.get(f"/api/v1/audits/{runs[1]['run_id']}/test-review")
            assert b.status_code == 200, b.text
            assert len(generated) == 1
            assert sorted((t['prompt'], t['expected_behavior']) for t in a.json()) == sorted((t['prompt'], t['expected_behavior']) for t in b.json()['tests'])
            from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
            monkeypatch.setattr('app.api.routes.get_behaviour_evaluator', lambda *_: RuleBasedBehaviourEvaluator())
            source_id, destination_id = [run['run_id'] for run in runs]
            blocked = client.post(f'/api/v1/audits/{destination_id}/execute')
            assert blocked.status_code == 409
            source = client.post(f'/api/v1/audits/{source_id}/execute')
            assert source.status_code == 200, source.text
            copied = client.post(f'/api/v1/audits/{destination_id}/execute')
            assert copied.status_code == 200, copied.text
            originals = {row['response_id']: row for row in source.json()}
            for row in copied.json():
                receipt = row['execution_metadata']
                assert row['response_text'] == originals[receipt['shared_source_response_id']]['response_text']
                assert receipt['shared_source_run_id'] == source_id
                assert receipt['request_attempts'] == receipt['total_tokens'] == 0
                assert receipt['memory_input'] == originals[receipt['shared_source_response_id']]['execution_metadata']['memory_input']
            repeated = client.post(f'/api/v1/audits/{destination_id}/reuse-answers', json={'source_run_id': source_id})
            assert {row['response_id'] for row in repeated.json()} == {row['response_id'] for row in copied.json()}
            assert client.post(f'/api/v1/audits/{destination_id}/evaluate').status_code == 200
            trace = client.get(f'/api/v1/audits/{destination_id}/target-memory-trace')
            assert trace.status_code == 200, trace.text
            assert trace.json()['shared_answer_source_run_id'] == source_id
            assert trace.json()['retrievals']
            result=client.get(f'/api/v1/audits/{destination_id}/results').json()
            assert result['retrieval_quality']['tests_measured']==len(copied.json())
            diagnosis = client.get(f'/api/v1/audits/{destination_id}/diagnosis')
            assert diagnosis.status_code == 200, diagnosis.text
            assert client.post(f'/api/v1/audits/{source_id}/reuse-answers', json={'source_run_id': destination_id}).status_code == 409

        finally:
            app.dependency_overrides.pop(get_db, None)


def test_historical_category_is_preserved_in_storage_but_not_reported_as_diagnosed():
    row = SimpleNamespace(id='E1', test_id='T1', response_id='R1', passed=False, failure_type='freshness',
        reason='Historical verdict', evidence_memory_ids=[], evaluator='rule-based-v35', judge_execution=None,
        failure_classification=None)
    result = eval_schema(row)
    assert result.failure_type is None
    assert result.failure_classification.status == 'legacy_test_dimension'
    assert row.failure_type == 'freshness'


def test_shared_answer_settings_guard_rejects_different_memory_policies():
    import pytest
    from fastapi import HTTPException
    from app.services.shared_answers import validate_shared_target
    fields = dict(conversation_id='C', provider='rule_based', model='same', temperature=0, random_seed=42,
                  target_configuration='strong', memory_strategy='scope_aware', memory_maintenance_policy='append_only',
                  target_memory_capacity=50, target_memory_writer='rule_based', target_memory_writer_version='v1',
                  target_system_adapter='controlled-memory', target_system_adapter_version='v1', test_budget=4,
                  prompt_template_version='v1', retrieval_mode='fixed', retrieval_provider=None, retrieval_model=None,
                  reproducibility_metadata={'target_memory_profile': {'label': 'same'}})
    validate_shared_target(SimpleNamespace(**fields), SimpleNamespace(**fields))
    with pytest.raises(HTTPException):
        validate_shared_target(SimpleNamespace(**fields), SimpleNamespace(**{**fields, 'memory_strategy': 'weak_first_hit'}))
    with pytest.raises(HTTPException):
        validate_shared_target(SimpleNamespace(**fields), SimpleNamespace(**{**fields, 'reproducibility_metadata': {'target_memory_profile': {'label': 'different'}}}))
