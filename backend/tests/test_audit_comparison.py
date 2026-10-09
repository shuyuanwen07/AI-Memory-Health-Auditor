from app.database.session import get_db
from app.main import app
from test_trace_and_test_review import _client, _conversation_and_experiment


def test_comparison_pairs_saved_frozen_tests_and_rejects_identical_runs(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PIPELINE_PROVIDER", "rule_based")
    monkeypatch.setenv("EVALUATOR_PROVIDER", "rule_based")
    with _client(tmp_path) as client:
        try:
            before, after = _conversation_and_experiment(client)
            client.post(f"/api/v1/audits/{before['run_id']}/generate-tests")
            pending = client.get(
                "/api/v1/audit-comparisons",
                params={"before": before["run_id"], "after": after["run_id"]},
            )
            assert pending.status_code == 409
            for run in (before, after):
                assert (
                    client.post(f"/api/v1/audits/{run['run_id']}/execute").status_code
                    == 200
                )
                assert (
                    client.post(f"/api/v1/audits/{run['run_id']}/evaluate").status_code
                    == 200
                )
            payload = client.get(
                "/api/v1/audit-comparisons",
                params={"before": before["run_id"], "after": after["run_id"]},
            ).json()
            assert payload["paired_tests"]
            assert any(item["field"] == "target_configuration" and item["before"] == "weak" and item["after"] == "strong" for item in payload["setting_differences"])
            assert any("does not isolate retrieval" in warning for warning in payload["warnings"])
            assert sum(payload["counts"].values()) == len(payload["paired_tests"])
            assert payload["unpaired_before"] == payload["unpaired_after"] == 0
            assert all(
                row["before"]["response_text"] and row["after"]["response_text"]
                for row in payload["paired_tests"]
            )
            assert (
                client.get(
                    "/api/v1/audit-comparisons",
                    params={"before": before["run_id"], "after": before["run_id"]},
                ).status_code
                == 422
            )
            # A separate experiment with the same text must never be paired by string matching.
            unrelated, _ = _conversation_and_experiment(client)
            client.post(f"/api/v1/audits/{unrelated['run_id']}/generate-tests")
            client.post(f"/api/v1/audits/{unrelated['run_id']}/execute")
            client.post(f"/api/v1/audits/{unrelated['run_id']}/evaluate")
            mismatch = client.get(
                "/api/v1/audit-comparisons",
                params={"before": before["run_id"], "after": unrelated["run_id"]},
            ).json()
            assert not mismatch["paired_tests"]
            assert mismatch["paired_delta_percentage_points"] is None
            assert mismatch["warnings"]
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_model_comparison_is_not_described_as_repeat():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence

    db = Mock()
    db.scalars.return_value.all.return_value = []
    shared = dict(memory_strategy='strong_rule_based', target_configuration='strong',
                  reproducibility_metadata={}, experiment_id='same', provider='ollama')
    before = SimpleNamespace(id='before', model='qwen-small', **shared)
    after = SimpleNamespace(id='after', model='qwen-large', **shared)
    result = compare_audit_evidence(db, before, after)
    assert any('different target models' in text for text in result['warnings'])
    assert not any('repeat comparison' in text for text in result['warnings'])


def test_changed_assessment_standard_cannot_create_apparent_improvement():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence

    shared = dict(memory_strategy='scope_aware', target_configuration='strong',
                  reproducibility_metadata={}, experiment_id='same', provider='ollama',
                  model='qwen', evaluator_provider='rule_based', evaluator_model=None)
    before, after = NS(id='before', **shared), NS(id='after', **shared)
    test = NS(comparison_test_id='frozen', suite_test_id='frozen', id='test',
              prompt='Where do I live?', expected_behavior='Dubbo', dimension='accuracy',
              supporting_memory_ids=['memory'])
    response = NS(response_text='Dubbo')
    db = Mock()
    db.scalars.return_value.all.return_value = [test]
    for old_version, new_version, old_meter, new_meter in [
        ('rule-based-v28', 'rule-based-v29', None, None),
        ('llm-judge-ollama-v2', 'llm-judge-ollama-v2',
         {'cross_check_version': 'rule-based-v28'}, {'cross_check_version': 'rule-based-v29'}),
        ('llm-judge-ollama-v2', 'llm-judge-ollama-v2', None, None),
        ('llm-judge-ollama-v3', 'llm-judge-ollama-v3', None, None),
        ('llm-judge-ollama-v2', 'llm-judge-ollama-v3',
         {'cross_check_version': 'rule-based-v30'}, {'cross_check_version': 'rule-based-v30'}),
    ]:
        db.scalar.side_effect = [NS(passed=False, evaluator=old_version, reason='Old', judge_execution=old_meter), response,
                                 NS(passed=True, evaluator=new_version, reason='New', judge_execution=new_meter), response]
        result = compare_audit_evidence(db, before, after)
        assert result['paired_tests'] == []
        assert result['counts']['fixed'] == 0
        assert result['paired_delta_percentage_points'] is None
        assert result['excluded_assessments'][0]['before_response'] == 'Dubbo'
        assert result['excluded_assessments'][0]['after_response'] == 'Dubbo'

    # Timing and verdict values can change without changing the scoring protocol.
    db.scalar.side_effect = [NS(passed=False, evaluator='llm-judge-ollama-v2', reason='Old',
                               judge_execution={'cross_check_version': 'rule-based-v29', 'elapsed_ms': 10}), response,
                             NS(passed=True, evaluator='llm-judge-ollama-v2', reason='New',
                                judge_execution={'cross_check_version': 'rule-based-v29', 'elapsed_ms': 20}), response]
    comparable = compare_audit_evidence(db, before, after)
    assert comparable['counts']['fixed'] == 1
    assert comparable['excluded_assessments'] == []
    assert comparable['paired_delta_percentage_points'] == 100
