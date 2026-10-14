"""Contract fixtures are simulated; none establishes empirical ranking agreement."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.benchmarks.live import LiveBenchmarkRunner
from app.research.ranking_agreement import RankingAgreementService, suite_result
from app.schemas.benchmark import LiveBenchmarkRequest
from app.schemas.ranking_agreement import RankingAgreementRequest
from app.target_ai.providers import HttpTargetAIConnector
from test_live_benchmark import PROVENANCE


@pytest.fixture
def package(monkeypatch):
    # Only simulated transport is used; no real credential or model call.
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test-key')
    monkeypatch.setattr(HttpTargetAIConnector, '_execute_provider', lambda *a: 'The information is incomplete.')
    source = [dict(question_id='fixture_abs', question_type='single-session-user', question='What is my birth year?',
        answer='The birth year is not present in the history.', messages=[{'role':'user','content':'I like Python.'}]),
        dict(question_id='fixture-two', question_type='knowledge-update', question='What database now?',
        answer='PostgreSQL', messages=[{'role':'user','content':'The backend now uses PostgreSQL.'}])]
    evidence = LiveBenchmarkRunner().run(LiveBenchmarkRequest(target_memory_profile={'output_token_limit':256},payload=source, source_authorised=True,dataset_provenance=PROVENANCE)).model_dump(mode='json')
    return dict(source=source, source_authorised=True, evidence=evidence, strategy='weak_first_hit', evaluator_revision='0'*40,
        rows=[dict(question_id='fixture_abs', hypothesis='The information is incomplete.',
            autoeval_label=dict(model='contract-fixture-no-model-call', label=True))])


@pytest.fixture
def ranking(package, monkeypatch):
    from app.research import ranking_agreement
    package['rows'].append(dict(question_id='fixture-two', hypothesis='The information is incomplete.',
        autoeval_label=dict(model='contract-fixture-no-model-call', label=False)))
    right = deepcopy(package)
    right['strategy'] = 'strong_rule_based'
    right['rows'][1]['autoeval_label']['label'] = True
    evidence = package['evidence']
    shared = dict(status='COMPLETED', provider=evidence['provider'], model=evidence['model'], random_seed=evidence['random_seed'],
        temperature=evidence['temperature'], target_configuration=evidence['reader_configuration'],
        target_memory_capacity=evidence['target_memory_capacity'], target_memory_writer_version=evidence['writer_version'],
        target_system_adapter_version=evidence['target_adapter_version'], target_system_adapter='controlled-memory',
        target_memory_writer='rule_based', memory_maintenance_policy='update_aware_consolidation',
        reproducibility_metadata={'target_memory_profile':evidence['target_memory_profile'], 'audit_runtime_signature':evidence['audit_runtime_signature']}, experiment_id='frozen')
    runs = [SimpleNamespace(id='before', memory_strategy='weak_first_hit', **deepcopy(shared)),
            SimpleNamespace(id='after', memory_strategy='strong_rule_based', **deepcopy(shared))]
    db = Mock()
    db.get.side_effect = lambda model, identity: next((run for run in runs if run.id == identity), None)
    db.scalar.return_value = 4
    db.scalars.return_value.all.return_value = [SimpleNamespace(model=evidence['model'], temperature=evidence['temperature'],
        execution_metadata=deepcopy(case['execution_metadata'])) for case in evidence['conditions'][0]['cases'] * 2]
    comparison = {'setting_differences':[], 'paired_tests':[
        {'dimension':'accuracy', 'before':{'passed':False}, 'after':{'passed':True}},
        {'dimension':'freshness', 'before':{'passed':True}, 'after':{'passed':True}},
        {'dimension':'conflict_resolution', 'before':{'passed':False}, 'after':{'passed':False}},
        {'dimension':'appropriate_use', 'before':{'passed':False}, 'after':{'passed':False}}]}
    monkeypatch.setattr(ranking_agreement, 'compare_audit_evidence', lambda *a: comparison)
    body = dict(reference_run_id='before', candidate_run_id='after', reference_benchmark=package, candidate_benchmark=right)
    return db, runs, comparison, body


def analyse(ranking):
    db, _, _, body = ranking
    return RankingAgreementService().analyse(db, RankingAgreementRequest(**body))


def test_relative_ordering_binds_exact_semantic_files_and_creates_no_records(ranking):
    report = analyse(ranking)
    assert report.agreement == 'consistent'
    assert [(s.reference_correct,s.candidate_correct,s.total) for s in report.suites] == [(1,2,4),(1,2,2)]
    assert report.suites[0].score_basis == 'dimension_macro_average'
    assert report.suites[0].reference_percentage == 25
    assert len(report.benchmark_evidence_fingerprint_sha256) == 64
    assert report.dataset_provenance.dataset_version=='synthetic-fixture-v1'
    assert len(report.source_fingerprint_sha256)==64
    assert len(report.adapter_fingerprint_sha256)==64 and report.compatibility_limitations
    assert 'not a comparison of absolute scores' in report.notice
    ranking[0].add.assert_not_called()
    ranking[0].commit.assert_not_called()


def test_ranking_agreement_requires_current_source_authorisation(ranking):
    ranking[3]['reference_benchmark']['source_authorised'] = False
    with pytest.raises(ValueError, match='source authorisation'):
        analyse(ranking)
    ranking[0].get.assert_not_called()


def test_optional_scope_aware_ablation_cannot_be_reported_as_experiment_c(ranking):
    ranking[1][1].memory_strategy = 'scope_aware'
    ranking[3]['candidate_benchmark']['strategy'] = 'scope_aware'
    with pytest.raises(ValueError, match='requires the frozen Weak first-hit and Strong rule-based policy pair'):
        analyse(ranking)


@pytest.mark.parametrize('audit,benchmark,expected',[(2,1,'consistent'),(0,1,'reversed'),(1,1,'inconclusive_tie'),(1,0,'both_tied')])
def test_ordering_and_ties_are_distinct(ranking,audit,benchmark,expected):
    ranking[2]['paired_tests']=[{'dimension':'accuracy','before':{'passed':True},'after':{'passed':audit>0}},
                              {'dimension':'freshness','before':{'passed':False},'after':{'passed':audit>1}},
                              {'dimension':'conflict_resolution','before':{'passed':False},'after':{'passed':False}},
                              {'dimension':'appropriate_use','before':{'passed':False},'after':{'passed':False}}]
    ranking[3]['candidate_benchmark']['rows'][1]['autoeval_label']['label']=bool(benchmark)
    assert analyse(ranking).agreement == expected


@pytest.mark.parametrize('field,value,match',[
    ('model','another-model','Target model'),('temperature',1,'Target model'),
    ('random_seed',7,'same recorded seed'),
    ('status','EXECUTED','must be complete'),('experiment_id','other','frozen experiment'),
    ('target_memory_writer_version',None,'implementation versions'),
    ('target_system_adapter','external-http','controlled target'),
    ('memory_maintenance_policy','append_only','preparation policy'),
])
def test_incompatible_settings_are_rejected(ranking,field,value,match):
    setattr(ranking[1][1],field,value)
    with pytest.raises(ValueError,match=match):analyse(ranking)


@pytest.mark.parametrize('mutate,match',[
    (lambda r:r[3].update(candidate_run_id='missing'), 'saved audits'),
    (lambda r:r[1][0].reproducibility_metadata.pop('target_memory_profile'), 'no frozen memory settings'),
    (lambda r:r[1][0].reproducibility_metadata.pop('audit_runtime_signature'), 'same saved software snapshot'),
    (lambda r:r[1][0].reproducibility_metadata.update(assessment_source_run_id='original'), 'original target executions'),
    (lambda r:r[3]['candidate_benchmark']['rows'].pop(), 'Complete semantic'),
    (lambda r:r[3]['candidate_benchmark']['rows'][0].update(hypothesis='altered'), 'exact saved reply'),
    (lambda r:r[3]['candidate_benchmark'].update(evaluator_revision='1'*40), 'same semantic evaluator'),
    (lambda r:r[3]['candidate_benchmark']['evidence'].update(model='altered'), 'same complete saved comparison'),
    (lambda r:r[2]['paired_tests'].pop(), 'Every frozen audit question'),
    (lambda r:r[2]['setting_differences'].append({'field':'temperature'}), 'more than memory strategy'),
])
def test_missing_or_changed_evidence_cannot_establish_agreement(ranking,mutate,match):
    mutate(ranking)
    with pytest.raises(ValueError,match=match):analyse(ranking)


def test_absolute_scores_remain_separate_for_unequal_suites():
    audit=suite_result('Audit',4,1,2)
    benchmark=suite_result('Benchmark',10,6,7)
    assert audit.ordering == benchmark.ordering == 'candidate_higher'
    assert audit.candidate_percentage == 50
    assert benchmark.candidate_percentage == 70


def test_auditor_ordering_uses_dimension_macro_average_when_question_counts_are_unequal():
    from app.research.ranking_agreement import audit_suite_result
    pairs = [{'dimension':'accuracy','before':{'passed':True},'after':{'passed':False}} for _ in range(9)]
    pairs += [{'dimension':dimension,'before':{'passed':False},'after':{'passed':True}}
              for dimension in ('freshness','conflict_resolution','appropriate_use')]
    result = audit_suite_result(pairs)
    assert (result.reference_correct, result.candidate_correct) == (9, 3)
    assert (result.reference_percentage, result.candidate_percentage) == (25, 75)
    assert result.ordering == 'candidate_higher'
    assert result.score_basis == 'dimension_macro_average'


def test_missing_auditor_dimension_is_unmeasured_and_cannot_establish_agreement(ranking):
    ranking[2]['paired_tests'][-1]['dimension'] = 'accuracy'
    report = analyse(ranking)
    assert report.agreement == 'inconclusive_missing_dimensions'
    assert report.suites[0].ordering == 'unmeasured'
    assert report.suites[0].reference_percentage is None
    missing = next(row for row in report.suites[0].dimensions if row.dimension.value == 'appropriate_use')
    assert missing.total == 0 and missing.reference_percentage is None


@pytest.mark.parametrize('field,value,match',[
    ('dataset_provenance',None,'dataset version, licence and citation'),
    ('adapter_fingerprint_sha256',None,'adapter version and implementation fingerprint'),
    ('compatibility_limitations',[],'declared compatibility limitations'),
])
def test_experiment_c_cannot_qualify_without_source_provenance(ranking,field,value,match):
    for condition in ('reference_benchmark','candidate_benchmark'):
        ranking[3][condition]['evidence'][field]=value
    with pytest.raises(ValueError,match=match):
        analyse(ranking)


def test_route_is_read_only_and_does_not_call_target(ranking,monkeypatch):
    from fastapi.testclient import TestClient
    from app.database.session import get_db
    from app.main import app
    from app.target_ai.providers import HttpTargetAIConnector
    # Only simulated transport is used; no real credential or model call.
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test-key')
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',lambda *a:pytest.fail('unexpected target call'))
    def supplied_db():
        yield ranking[0]
    app.dependency_overrides[get_db]=supplied_db
    try:
        with TestClient(app) as client:
            result=client.post('/api/v1/research/benchmarks/longmemeval/ranking-agreement',json=ranking[3])
            assert result.status_code == 200
            assert result.json()['agreement'] == 'consistent'
            ranking[3]['candidate_benchmark']['rows'].pop()
            assert client.post('/api/v1/research/benchmarks/longmemeval/ranking-agreement',json=ranking[3]).status_code == 422
        ranking[0].commit.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db,None)


def test_route_rejects_missing_source_authorisation_before_service(ranking,monkeypatch):
    from copy import deepcopy
    from fastapi.testclient import TestClient
    from app.database.session import get_db
    from app.main import app
    from app.api import research_routes
    payload=deepcopy(ranking[3])
    payload['reference_benchmark']['source_authorised']=False
    payload['candidate_benchmark']['source_authorised']=False
    monkeypatch.setattr(research_routes.RankingAgreementService,'analyse',lambda *args:pytest.fail('service must not process unauthorised source'))
    def supplied_db():
        yield ranking[0]
    app.dependency_overrides[get_db]=supplied_db
    try:
        with TestClient(app) as client:
            response=client.post('/api/v1/research/benchmarks/longmemeval/ranking-agreement',json=payload)
        assert response.status_code == 422
        assert 'source_authorised=true' in response.json()['detail']
        ranking[0].get.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db,None)


@pytest.mark.parametrize('field,value,match',[
    ('requested_output_token_limit',None,'length limits are unknown'),
    ('requested_output_token_limit',512,'length limits differ'),
    ('response_source','shared_saved_answer','original model-call receipts'),
    ('request_attempts',0,'original model-call receipts'),
    ('shared_source_response_id','earlier','original model-call receipts'),
])
def test_actual_receipts_prevent_unknown_budget_or_reused_reply_comparisons(ranking,field,value,match):
    ranking[0].scalars.return_value.all.return_value[0].execution_metadata[field]=value
    with pytest.raises(ValueError,match=match):analyse(ranking)


def test_changed_actual_reply_model_cannot_be_hidden_by_run_settings(ranking):
    ranking[0].scalars.return_value.all.return_value[0].model='different-model'
    with pytest.raises(ValueError,match='saved answer used different model'):analyse(ranking)


def test_receipt_query_uses_assessed_attempt_and_excludes_wrong_run(tmp_path,monkeypatch):
    from sqlalchemy import select
    from app.database.session import get_db
    from app.main import app
    from app.models import EvaluationResultModel, TargetResponseModel, TestCaseModel
    from test_trace_and_test_review import _client, _conversation_and_experiment
    monkeypatch.setenv('PIPELINE_PROVIDER','rule_based')
    monkeypatch.setenv('EVALUATOR_PROVIDER','rule_based')
    with _client(tmp_path) as client:
        try:
            run, other=_conversation_and_experiment(client)
            client.post(f"/api/v1/audits/{run['run_id']}/generate-tests")
            client.post(f"/api/v1/audits/{run['run_id']}/execute")
            client.post(f"/api/v1/audits/{run['run_id']}/evaluate")
            session=app.dependency_overrides[get_db]()
            db=next(session)
            try:
                test=db.scalar(select(TestCaseModel).where(TestCaseModel.run_id==run['run_id']))
                assessment=db.scalar(select(EvaluationResultModel).where(EvaluationResultModel.test_id==test.id))
                first=db.get(TargetResponseModel,assessment.response_id)
                original_id=first.id
                chosen=TargetResponseModel(id='selected-ranking-attempt',run_id=first.run_id,test_id=first.test_id,
                    response_text=first.response_text,model=first.model,temperature=first.temperature,
                    execution_metadata={'requested_output_token_limit':512})
                db.add(chosen);db.flush();assessment.response_id=chosen.id;db.commit()
                ids={r.id for r in RankingAgreementService._evaluated_responses(db,run['run_id'])}
                assert chosen.id in ids and original_id not in ids
                chosen.run_id=other['run_id'];db.commit()
                assert chosen.id not in {r.id for r in RankingAgreementService._evaluated_responses(db,run['run_id'])}
            finally:
                session.close()
        finally:
            app.dependency_overrides.pop(get_db,None)
