from app.database.session import get_db
from app.main import app
from test_trace_and_test_review import _client, _conversation_and_experiment


def _comparison_rows(db, test, assessment_and_answer_rows):
    """Relational test double for the two batched, exact-association reads."""
    from types import SimpleNamespace as NS
    from unittest.mock import Mock
    batches = []
    for run_id, evaluation, response in [('before', *assessment_and_answer_rows[:2]), ('after', *assessment_and_answer_rows[2:])]:
        test_id, response_id = f'test-{run_id}', f'reply-{run_id}'
        question = NS(**{**vars(test), 'id':test_id})
        assessment = NS(**{**vars(evaluation), 'test_id':test_id, 'response_id':response_id})
        answer = NS(**{**vars(response), 'id':response_id, 'test_id':test_id, 'run_id':run_id})
        for rows in ([question], [assessment], [answer]):
            cursor = Mock()
            cursor.all.return_value = rows
            batches.append(cursor)
    db.scalars.side_effect = batches


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


def test_structured_writer_runtime_changes_are_visible_and_cannot_be_called_repeats():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence
    shared = dict(memory_strategy='strong_rule_based', target_configuration='strong',
                  reproducibility_metadata={}, experiment_id='same', provider='ollama',model='qwen',
                  target_memory_writer='llm_structured', target_memory_writer_version='writer-v1')
    db=Mock();db.scalars.return_value.all.return_value=[]
    before=NS(id='before',pipeline_provider='openrouter',pipeline_model='writer-small',**shared)
    after=NS(id='after',pipeline_provider='openai',pipeline_model='writer-large',**shared)
    report=compare_audit_evidence(db,before,after)
    changes={row['field']:row for row in report['setting_differences']}
    assert changes['memory_writer_provider']['before']=='openrouter'
    assert changes['memory_writer_model']['after']=='writer-large'
    assert any('stored-memory evidence' in text for text in report['warnings'])
    assert not any('repeat comparison' in text for text in report['warnings'])


def test_missing_model_writer_runtime_is_not_assumed_equivalent_and_rule_writers_ignore_generation_runtime():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence
    shared=dict(memory_strategy='strong_rule_based',target_configuration='strong',reproducibility_metadata={},
                experiment_id='same',provider='ollama',model='qwen')
    db=Mock();db.scalars.return_value.all.return_value=[]
    before=NS(id='before',target_memory_writer='llm_structured',pipeline_provider=None,pipeline_model=None,**shared)
    after=NS(id='after',target_memory_writer='llm_structured',pipeline_provider=None,pipeline_model=None,**shared)
    unknown=compare_audit_evidence(db,before,after)
    assert any('Writer equivalence cannot be established' in text for text in unknown['warnings'])
    assert not any('repeat comparison' in text for text in unknown['warnings'])
    before.target_memory_writer=after.target_memory_writer='rule_based'
    before.pipeline_provider='rule_based';after.pipeline_provider='openrouter';after.pipeline_model='generator-model'
    deterministic=compare_audit_evidence(db,before,after)
    assert not any(row['field'].startswith('memory_writer_') for row in deterministic['setting_differences'])
    assert not any('Model-written memory' in text for text in deterministic['warnings'])
    assert any('repeat comparison' in text for text in deterministic['warnings'])


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
        ('llm-judge-openrouter-v5', 'llm-judge-openrouter-v5', None, None),
        ('llm-judge-openrouter-v6', 'llm-judge-openrouter-v6', None, None),
        ('llm-judge-gemini-v6', 'llm-judge-gemini-v6', {}, {}),
        ('llm-judge-openrouter-v6', 'llm-judge-openrouter-v6',
         {'cross_check_version': 'rule-based-v53'}, None),
        ('llm-judge-ollama-v2', 'llm-judge-ollama-v3',
         {'cross_check_version': 'rule-based-v30'}, {'cross_check_version': 'rule-based-v30'}),
    ]:
        _comparison_rows(db, test, [NS(response_id='reply', passed=False, evaluator=old_version, reason='Old', judge_execution=old_meter), response,
                                 NS(response_id='reply', passed=True, evaluator=new_version, reason='New', judge_execution=new_meter), response])
        result = compare_audit_evidence(db, before, after)
        assert result['shared_question_count'] == 1
        assert result['decided_shared_question_count'] == 1
        assert result['comparable_decided_question_count'] == 0
        assert not any('No identical frozen' in warning for warning in result['warnings'])
        assert result['paired_tests'] == []
        assert result['counts']['fixed'] == 0
        assert result['paired_delta_percentage_points'] is None
        assert result['excluded_assessments'][0]['before_response'] == 'Dubbo'
        assert result['excluded_assessments'][0]['after_response'] == 'Dubbo'

    # Timing and verdict values can change without changing the scoring protocol.
    for version in ('llm-judge-ollama-v2', 'llm-judge-openrouter-v6'):
        _comparison_rows(db, test, [NS(response_id='reply', passed=False, evaluator=version, reason='Old',
                                   judge_execution={'cross_check_version': 'rule-based-v29', 'elapsed_ms': 10}), response,
                                 NS(response_id='reply', passed=True, evaluator=version, reason='New',
                                    judge_execution={'cross_check_version': 'rule-based-v29', 'elapsed_ms': 20}), response])
        comparable = compare_audit_evidence(db, before, after)
        assert comparable['counts']['fixed'] == 1
        assert comparable['excluded_assessments'] == []
        assert comparable['paired_delta_percentage_points'] == 100


def test_uncertain_assessments_do_not_erase_unchanged_shared_questions():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence

    common = dict(memory_strategy='scope_aware', target_configuration='strong',
                  reproducibility_metadata={}, experiment_id='same', provider='ollama',
                  model='qwen', evaluator_provider='rule_based', evaluator_model=None)
    before, after = NS(id='before', **common), NS(id='after', **common)
    test = NS(comparison_test_id='frozen', suite_test_id='frozen', id='test',
              prompt='Where is the user based?', expected_behavior='Dubbo', dimension='accuracy',
              supporting_memory_ids=['memory'])
    db = Mock()
    db.scalars.return_value.all.return_value = [test]
    response = NS(response_text='Dubbo')
    _comparison_rows(db, test, [NS(response_id='reply', passed=None), response,
                             NS(response_id='reply', passed=True), response])
    result = compare_audit_evidence(db, before, after)
    assert result['shared_question_count'] == 1
    assert result['decided_shared_question_count'] == 0
    assert result['comparable_decided_question_count'] == 0
    assert result['paired_delta_percentage_points'] is None
    assert not result['excluded_assessments']


def test_comparison_reads_the_evaluated_response_not_an_unassessed_attempt(tmp_path, monkeypatch):
    from sqlalchemy import select
    from app.models import EvaluationResultModel, TargetResponseModel, TestCaseModel

    monkeypatch.setenv('PIPELINE_PROVIDER', 'rule_based')
    monkeypatch.setenv('EVALUATOR_PROVIDER', 'rule_based')
    with _client(tmp_path) as client:
        try:
            before, after = _conversation_and_experiment(client)
            client.post(f"/api/v1/audits/{before['run_id']}/generate-tests")
            for run in (before, after):
                assert client.post(f"/api/v1/audits/{run['run_id']}/execute").status_code == 200
                assert client.post(f"/api/v1/audits/{run['run_id']}/evaluate").status_code == 200
            baseline_result = client.get(f"/api/v1/audits/{before['run_id']}/results").json()
            session = app.dependency_overrides[get_db]()
            db = next(session)
            try:
                test = db.scalar(select(TestCaseModel).where(TestCaseModel.run_id == before['run_id']))
                selected_test_id = test.id
                evaluation = db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id == test.id))
                first = db.get(TargetResponseModel, evaluation.response_id)
                saved_text = first.response_text
                chosen = TargetResponseModel(id='R_EXACT_ASSESSED_ATTEMPT', run_id=first.run_id,
                    test_id=first.test_id, response_text=saved_text, model=first.model,
                    temperature=first.temperature, execution_metadata=first.execution_metadata)
                first.response_text = 'Unassessed first attempt.'
                db.add(chosen); db.flush()
                evaluation.response_id = chosen.id
                db.commit()
            finally:
                session.close()
            payload = client.get('/api/v1/audit-comparisons', params={
                'before': before['run_id'], 'after': after['run_id'],
            }).json()
            item = next(row for row in payload['paired_tests'] if row['suite_test_id'] == selected_test_id)
            assert item['before']['response_text'] == saved_text

            result = client.get(f"/api/v1/audits/{before['run_id']}/results").json()
            unassessed = next(
                answer for answer in result['answers']
                if answer['response']['response_text'] == 'Unassessed first attempt.'
            )
            assert unassessed['outcome'] == 'unassessed'
            assert unassessed['evaluation'] is None
            # The paired comparison selects the uniquely assessed response,
            # and adding another saved response cannot change the run score.
            for key in (
                'overall_score', 'tests_passed', 'tests_total', 'uncertain_count',
                'evaluated_count', 'expected_tests', 'dimensions',
            ):
                assert result[key] == baseline_result[key]
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_saved_answer_provenance_warns_even_without_study_role():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence

    for key in ('assessment_source_run_id', 'shared_answer_source_run_id'):
        db = Mock()
        db.scalars.return_value.all.return_value = []
        shared = dict(memory_strategy='strong_rule_based', target_configuration='strong',
                      experiment_id='same', provider='ollama', model='qwen')
        before = SimpleNamespace(id='before', reproducibility_metadata={}, **shared)
        after = SimpleNamespace(id='after', reproducibility_metadata={key: 'before'}, **shared)
        result = compare_audit_evidence(db, before, after)
        assert result['answer_provenance'] == 'unknown_saved_answers'
        assert any('provenance is incomplete or mixed' in text for text in result['warnings'])


def test_saved_answer_provenance_uses_receipts_and_exact_text_not_equal_answer_words():
    from types import SimpleNamespace as NS
    from unittest.mock import Mock
    from app.services.audit_comparison import compare_audit_evidence
    common = dict(memory_strategy='scope_aware', target_configuration='strong', experiment_id=None,
                  provider='ollama', model='qwen', evaluator_provider='rule_based', evaluator_model=None)
    before = NS(id='before', reproducibility_metadata={'assessment_source_run_id':'source-left'}, **common)
    after = NS(id='after', reproducibility_metadata={'assessment_source_run_id':'source-right'}, **common)
    test = NS(comparison_test_id='frozen', suite_test_id='frozen', id='test', prompt='Where?',
              expected_behavior='Dubbo', dimension='accuracy', supporting_memory_ids=['memory'])
    def response(source, text='Dubbo'):
        return NS(id=source, response_text=text, execution_metadata={
            'response_source':'shared_target_answer','shared_source_run_id':'original', 'shared_source_response_id':source})
    for left, right, expected in [
        (response('one'), response('one'), 'same_saved_answers'),
        (response('one'), response('two'), 'different_saved_executions'),
        (response('one'), response('one', 'A changed answer'), 'unknown_saved_answers'),
        (response('one'), NS(id='cloned', response_text='Dubbo', execution_metadata={}), 'unknown_saved_answers'),
    ]:
        db = Mock(); db.scalars.return_value.all.return_value = [test]
        evaluation = NS(response_id='reply', passed=True, reason='Fixture assessment', evaluator='rule-based-v48', judge_execution=None)
        _comparison_rows(db, test, [evaluation, left, evaluation, right])
        assert compare_audit_evidence(db, before, after)['answer_provenance'] == expected
