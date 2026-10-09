"""Contract checks: fixture labels are not evidence of model performance."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.benchmarks.live import LiveBenchmarkRunner
from app.benchmarks.semantic_review import SemanticReviewService
from app.main import app
from app.schemas.benchmark import LiveBenchmarkRequest
from app.schemas.semantic_review import SemanticReviewRequest
from app.target_ai.providers import HttpTargetAIConnector


@pytest.fixture
def package(monkeypatch):
    monkeypatch.setattr(HttpTargetAIConnector, '_execute_provider', lambda *a: 'The information is incomplete.')
    source = [dict(question_id='fixture_abs', question_type='single-session-user', question='What is my birth year?',
        answer='The birth year is not present in the history.', messages=[{'role':'user','content':'I like Python.'}]),
        dict(question_id='fixture-two', question_type='knowledge-update', question='What database now?',
        answer='PostgreSQL', messages=[{'role':'user','content':'The backend now uses PostgreSQL.'}])]
    evidence = LiveBenchmarkRunner().run(LiveBenchmarkRequest(payload=source, source_authorised=True)).model_dump(mode='json')
    return dict(source=source, evidence=evidence, strategy='weak_first_hit', evaluator_revision='0'*40,
        rows=[dict(question_id='fixture_abs', hypothesis='The information is incomplete.',
            autoeval_label=dict(model='contract-fixture-no-model-call', label=True))])


def analyse(package):
    return SemanticReviewService().analyse(SemanticReviewRequest(**package))


def test_partial_assessment_keeps_missing_unknown_and_binds_all_provenance(package):
    report = analyse(package)
    assert (report.total, report.reviewed, report.correct, report.pending, report.percentage) == (2,1,1,1,None)
    assert report.lexical_disagreements == 1
    assert report.cases[0].semantic_correct is True
    assert report.cases[1].semantic_correct is None
    assert len(report.evidence_fingerprint_sha256) == len(report.evaluation_fingerprint_sha256) == 64
    assert 'not independently verified' in report.notice
    categories = {c.category:c for c in report.categories}
    assert categories['single-session-user'].percentage == 100
    assert categories['knowledge-update'].percentage is None


def test_complete_assessment_counts_false_as_reviewed_not_missing(package):
    package['rows'].append(dict(question_id='fixture-two',hypothesis='The information is incomplete.',
        autoeval_label=dict(model='contract-fixture-no-model-call',label=False)))
    first=analyse(package)
    package['rows'].reverse()
    second=analyse(package)
    assert (first.reviewed, first.pending, first.percentage) == (2,0,50)
    assert first.cases == second.cases
    assert first.cases[1].semantic_correct is False


@pytest.mark.parametrize('mutate,match',[
    (lambda p:p['source'][0].update(answer='changed'), 'source file does not match'),
    (lambda p:p.update(strategy='missing'), 'Choose a condition'),
    (lambda p:p['rows'].append(deepcopy(p['rows'][0])), 'duplicate question'),
    (lambda p:p['rows'][0].update(question_id='missing'), 'question absent'),
    (lambda p:p['rows'][0].update(hypothesis='The information is incomplete. '), 'exact saved reply'),
    (lambda p:p['evidence']['conditions'].append(deepcopy(p['evidence']['conditions'][0])), 'duplicate conditions'),
    (lambda p:p['evidence']['conditions'][0]['cases'].pop(), 'each source question'),
    (lambda p:p['evidence']['conditions'][1]['cases'].append(deepcopy(p['evidence']['conditions'][1]['cases'][0])), 'each source question'),
    (lambda p:p['evidence']['conditions'][1]['cases'][0].update(expected_answer='corrupted'), 'differ from the source'),
    (lambda p:p['evidence']['conditions'][1]['cases'][0].update(category='knowledge-update'), 'differ from the source'),
    (lambda p:p['evidence']['conditions'][1]['cases'][0].update(lexical_match=True), 'lexical assessments'),
    (lambda p:p['rows'].append(dict(question_id='fixture-two',hypothesis='The information is incomplete.',autoeval_label=dict(model='different',label=False))), 'one evaluator model'),
])
def test_rejects_mixed_tampered_or_ambiguous_files(package,mutate,match):
    mutate(package)
    with pytest.raises(ValueError, match=match):analyse(package)


@pytest.mark.parametrize('label',['false','yes',0,1,None])
def test_labels_are_strict_booleans(package,label):
    package['rows'][0]['autoeval_label']['label']=label
    with pytest.raises(ValidationError):SemanticReviewRequest(**package)


def test_import_endpoint_has_no_database_or_provider_dependencies(package,monkeypatch):
    # This fixture's simulated replies are already frozen; importing must not
    # start another inference or touch the operational audit store.
    monkeypatch.setattr(HttpTargetAIConnector,'_execute_provider',lambda *a:pytest.fail('unexpected model call'))
    with TestClient(app) as client:
        response=client.post('/api/v1/research/benchmarks/longmemeval/semantic-review',json=package)
        assert response.status_code == 200
        assert response.json()['pending'] == 1
        package['rows'][0]['hypothesis']='wrong condition'
        assert client.post('/api/v1/research/benchmarks/longmemeval/semantic-review',json=package).status_code == 422
