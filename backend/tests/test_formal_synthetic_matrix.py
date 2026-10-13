"""The formal matrix persists only approved synthetic scenarios and frozen suites."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, ConversationModel, ExperimentModel, TestCaseModel
from app.schemas.annotation import AnnotationDataset
from app.schemas.research import annotation_fingerprint


@pytest.mark.parametrize('stage', ['execute', 'evaluate', 'retry'])
@pytest.mark.parametrize('component', ['evaluator', 'writer', 'adapter', 'source', 'legacy'])
def test_formal_matrix_rejects_implementation_drift_before_work(tmp_path, monkeypatch, stage, component):
    from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
    from app.extraction.rule_based import RuleBasedMemoryExtractor
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    from app.services import formal_freeze
    from app.models import TargetResponseModel, EvaluationResultModel
    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            created = client.post('/api/v1/research/exploratory/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
                'conditions': [
                    {'label': 'Scope', 'memory_strategy': 'scope_aware', 'provider': 'rule_based'},
                    {'label': 'Temporal', 'memory_strategy': 'temporal_importance', 'provider': 'rule_based'},
                ],
            })
            assert created.status_code == 201, created.text
            run_id = created.json()['scenarios'][0]['run_ids'][0]
            if stage == 'evaluate':
                assert client.post(f'/api/v1/audits/{run_id}/execute').status_code == 200
            if stage == 'retry':
                with factory() as db:
                    db.get(AuditRunModel, run_id).status = 'FAILED'
                    db.commit()
            if component == 'evaluator':
                monkeypatch.setattr(RuleBasedBehaviourEvaluator, 'VERSION', 'changed-after-freeze')
            elif component == 'writer':
                monkeypatch.setattr(RuleBasedMemoryExtractor, 'VERSION', 'changed-after-freeze')
            elif component == 'adapter':
                monkeypatch.setattr(ControlledTargetSystemAdapter, 'version', 'changed-after-freeze')
            elif component == 'source':
                changed = {**formal_freeze.formal_runtime_signature(), 'source_sha256': 'changed-without-version-bump'}
                monkeypatch.setattr(formal_freeze, 'formal_runtime_signature', lambda: changed)
            else:
                with factory() as db:
                    audit = db.get(AuditRunModel, run_id)
                    audit.reproducibility_metadata = {'formal_matrix_version': 'synthetic-formal-matrix-v1'}
                    db.commit()
            result = client.post(f'/api/v1/audits/{run_id}/{stage}')
            assert result.status_code == 409, result.text
            assert 'frozen' in result.json()['detail'].lower()
            with factory() as db:
                assert db.query(EvaluationResultModel).count() == 0
                if stage != 'evaluate':
                    assert db.query(TargetResponseModel).count() == 0
                expected_status = {'execute': 'TESTS_GENERATED', 'evaluate': 'TESTS_EXECUTED', 'retry': 'FAILED'}[stage]
                assert db.get(AuditRunModel, run_id).status == expected_status
    finally:
        app.dependency_overrides.clear()


def _build_dataset() -> dict:
    """Return a tiny, deterministic fixture that is safe to run in CI.

    The full pilot release is intentionally local and ignored by git.  This
    test exercises the API contract with synthetic records instead of making
    CI depend on that private research artefact being present in a checkout.
    Four dimensions per scenario preserve the formal matrix's paired-suite
    assertions while keeping the fixture small and readable.
    """
    dimensions = [
        ("accuracy", "direct"),
        ("freshness", "contextual"),
        ("conflict_resolution", "indirect"),
        ("appropriate_use", "paraphrased"),
    ]
    conversations = []
    for scenario_number in range(1, 6):
        suffix = f"S{scenario_number}"
        message_id = f"{suffix}-M1"
        memory_id = f"{suffix}-G1"
        value = f"Synthetic fact {scenario_number}."
        tests = [
            {
                "test_id": f"{suffix}-T{test_number}",
                "dimension": dimension,
                "test_type": test_type,
                "prompt": f"What is synthetic fact {scenario_number} ({dimension})?",
                "expected_behavior": f"State {value}",
                "supporting_memory_ids": [memory_id],
                "grounded": True,
                "quality_label": "accept",
                "quality_note": "Inline synthetic CI fixture.",
            }
            for test_number, (dimension, test_type) in enumerate(dimensions, start=1)
        ]
        evaluations = [
            {
                "response_id": f"{suffix}-R{test_number}",
                "test_id": test["test_id"],
                "response_text": value,
                "passed": True,
                "failure_type": None,
                "reason": "Matches the inline synthetic fixture.",
                "evidence_memory_ids": [memory_id],
            }
            for test_number, test in enumerate(tests, start=1)
        ]
        conversations.append(
            {
                "conversation_id": f"SYN-C{scenario_number:03d}",
                "messages": [
                    {
                        "message_id": message_id,
                        "role": "user",
                        "content": value,
                        "timestamp": "2026-01-01T09:00:00Z",
                    }
                ],
                "gold_memories": [
                    {
                        "memory_id": memory_id,
                        "canonical_value": value,
                        "source_message_ids": [message_id],
                    }
                ],
                "gold_tests": tests,
                "gold_evaluations": evaluations,
            }
        )
    return {
        "dataset_id": "ci-inline-synthetic",
        "dataset_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00Z",
        "authorised_for_research": True,
        "data_origin": "Five synthetic CI fixtures with no participant data.",
        "deidentification_note": "Inline synthetic test data only.",
        "conversations": conversations,
    }


def _build_pilot() -> dict:
    """Return complete, matching labels for the formal readiness gate."""
    task_labels = [
        ("memory_inclusion", "include"),
        ("relationship_type", "UPDATE"),
        ("test_validity", "accept"),
        ("evaluator_verdict", "pass"),
        ("failure_dimension", "freshness"),
    ]
    items = [
        {"item_id": f"{task.upper()}-{number:02d}", "task": task}
        for task, _ in task_labels
        for number in range(1, 6)
    ]
    labels_by_task = dict(task_labels)

    def labels():
        return [
            {"item_id": item["item_id"], "task": item["task"], "label": labels_by_task[item["task"]]}
            for item in items
        ]

    adjudications = [
        {
            "item_id": item["item_id"],
            "task": item["task"],
            "label": labels_by_task[item["task"]],
            "basis": "external_reference",
            "decision_note": "Inline synthetic CI reference label.",
        }
        for item in items
    ]
    return {
        "pilot_id": "ci-inline-pilot",
        "dataset_id": "ci-inline-synthetic",
        "dataset_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00Z",
        "authorised_for_research": True,
        "data_origin": "Synthetic CI fixture with no participant data.",
        "deidentification_note": "Inline synthetic labels only.",
        "annotation_mode": "human_double_annotation",
        "minimum_paired_items_per_task": 5,
        "minimum_kappa": 0.6,
        "items": items,
        "annotators": [
            {"annotator_id": "yc", "labels": labels()},
            {"annotator_id": "sd", "labels": labels()},
        ],
        "adjudications": adjudications,
    }


DATASET = _build_dataset()
PILOT = _build_pilot()
CRITERIA = {'failure_detection_recall_min_percent':80, 'failure_classification_accuracy_min_percent':75, 'test_validity_min_percent':90, 'false_positive_rate_max_percent':10}

PILOT["dataset_fingerprint_sha256"] = annotation_fingerprint(AnnotationDataset.model_validate(DATASET))


def test_ready_human_pilot_materialises_paired_frozen_synthetic_runs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matrix.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    payload = {
        "dataset": DATASET, "pilot": PILOT, "synthetic_data_confirmation": True, "success_criteria": CRITERIA,
        "conditions": [
            {"label": "Weak", "memory_strategy": "weak_first_hit", "provider": "rule_based", "model": "rule-based-target-ai"},
            {"label": "Scope", "memory_strategy": "scope_aware", "provider": "rule_based", "model": "rule-based-target-ai"},
        ],
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/research/exploratory/synthetic-matrix", json=payload)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["scenario_count"] == 5
            assert body["acceptance_protocol"]["criteria"] == CRITERIA
            assert body["acceptance_protocol"]["frozen_at"]
            assert body["total_audit_runs"] == 10
            assert body["total_target_calls"] == 40
            duplicate = client.post("/api/v1/research/exploratory/synthetic-matrix", json=payload)
            assert duplicate.status_code == 409
    finally:
        app.dependency_overrides.clear()

    db = factory()
    try:
        assert {item.source_origin for item in db.query(ConversationModel).all()} == {"synthetic"}
        assert db.query(ExperimentModel).count() == 5
        assert db.query(AuditRunModel).count() == 10
        from app.services.formal_freeze import formal_runtime_signature
        runtime = formal_runtime_signature()
        for audit in db.query(AuditRunModel).all():
            assert audit.target_system_adapter_version == runtime['adapter']
            assert audit.reproducibility_metadata['formal_runtime_signature'] == runtime
            assert audit.reproducibility_metadata['formal_acceptance_protocol'] == body['acceptance_protocol']
            from datetime import datetime, timezone
            frozen=datetime.fromisoformat(body['acceptance_protocol']['frozen_at'].replace('Z','+00:00'))
            assert frozen <= audit.created_at.replace(tzinfo=timezone.utc)
        tests = db.query(TestCaseModel).all()
        assert len(tests) == 40
        assert {test.quality_status for test in tests} == {"accepted"}
        assert {test.grounding_status for test in tests} == {"grounded"}
        canonical = [test for test in tests if test.suite_test_id is None]
        peers = [test for test in tests if test.suite_test_id is not None]
        assert len(canonical) == len(peers) == 20
        assert all(test.suite_test_id in {source.id for source in canonical} for test in peers)
    finally:
        db.close()


def test_matrix_rejects_non_synthetic_dataset_before_persistence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matrix-reject.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def test_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    non_synthetic = {**DATASET, "conversations": list(DATASET["conversations"])}
    non_synthetic["data_origin"] = "Authorised research conversations"
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/research/exploratory/synthetic-matrix", json={
                "dataset": non_synthetic, "pilot": PILOT, "synthetic_data_confirmation": True, "success_criteria": CRITERIA,
                "conditions": [
                    {"label": "Weak", "memory_strategy": "weak_first_hit", "provider": "rule_based", "model": "rule-based-target-ai"},
                    {"label": "Scope", "memory_strategy": "scope_aware", "provider": "rule_based", "model": "rule-based-target-ai"},
                ],
            })
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
    db = factory()
    try:
        assert db.query(ExperimentModel).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize('action', ['review', 'regenerate'])
def test_formal_gold_suite_cannot_be_changed_before_execution(tmp_path, action):
    engine = create_engine(f"sqlite:///{tmp_path / 'gold-freeze.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            created = client.post('/api/v1/research/exploratory/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
                'conditions': [
                    {'label': 'Scope', 'memory_strategy': 'scope_aware', 'provider': 'rule_based'},
                    {'label': 'Temporal', 'memory_strategy': 'temporal_importance', 'provider': 'rule_based'},
                ],
            })
            assert created.status_code == 201
            run_id = created.json()['scenarios'][0]['run_ids'][0]
            with factory() as db:
                test = db.query(TestCaseModel).filter_by(run_id=run_id).first()
                test_id, prompt, note = test.id, test.prompt, test.validation_notes
            url = f'/api/v1/audits/{run_id}/tests/{test_id}/{action}'
            result = client.patch(url, json={'quality_status': 'rejected', 'note': 'Change frozen reference'}) if action == 'review' else client.post(url)
            assert result.status_code == 409, result.text
            with factory() as db:
                saved = db.get(TestCaseModel, test_id)
                assert (saved.prompt, saved.validation_notes, saved.quality_status) == (prompt, note, 'accepted')
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('stage', ['execute', 'evaluate', 'retry'])
@pytest.mark.parametrize('component', ['message', 'memory', 'relationship', 'question', 'reference', 'configuration', 'criteria', 'legacy'])
def test_formal_matrix_rejects_saved_input_drift(tmp_path, stage, component):
    from app.models import MessageModel, MemoryModel, MemoryRelationshipModel, EvaluationResultModel, TargetResponseModel
    engine = create_engine(f"sqlite:///{tmp_path / 'inputs.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            created = client.post('/api/v1/research/exploratory/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
                'conditions': [
                    {'label': 'Scope', 'memory_strategy': 'scope_aware', 'provider': 'rule_based'},
                    {'label': 'Temporal', 'memory_strategy': 'temporal_importance', 'provider': 'rule_based'},
                ],
            })
            assert created.status_code == 201
            run_id = created.json()['scenarios'][0]['run_ids'][0]
            if stage == 'evaluate':
                assert client.post(f'/api/v1/audits/{run_id}/execute').status_code == 200
            with factory() as db:
                audit = db.get(AuditRunModel, run_id)
                if stage == 'retry':
                    audit.status = 'FAILED'
                memory = db.query(MemoryModel).filter_by(conversation_id=audit.conversation_id).first()
                test = db.query(TestCaseModel).filter_by(run_id=run_id).first()
                if component == 'message':
                    db.query(MessageModel).filter_by(conversation_id=audit.conversation_id).first().content = 'Changed source'
                elif component == 'memory':
                    memory.canonical_value = 'Changed gold'
                elif component == 'relationship':
                    db.add(MemoryRelationshipModel(id='changed-edge', memory_id=memory.id,
                                                  target_memory_id=memory.id, relationship_type='UPDATE'))
                elif component == 'question':
                    test.prompt = 'Changed question'
                elif component == 'reference':
                    test.expected_behavior = 'Changed reference'
                elif component == 'configuration':
                    audit.temperature = 0.7
                elif component == 'criteria':
                    from copy import deepcopy
                    metadata=deepcopy(audit.reproducibility_metadata)
                    metadata['formal_acceptance_protocol']['criteria']['test_validity_min_percent']=0
                    audit.reproducibility_metadata=metadata
                else:
                    audit.reproducibility_metadata = {k:v for k,v in audit.reproducibility_metadata.items()
                                                      if k != 'formal_input_sha256'}
                db.commit()
            result = client.post(f'/api/v1/audits/{run_id}/{stage}')
            assert result.status_code == 409, result.text
            assert 'frozen' in result.json()['detail']
            with factory() as db:
                assert db.query(EvaluationResultModel).count() == 0
                assert db.query(TargetResponseModel).count() == (4 if stage == 'evaluate' else 0)
                expected_status = {'execute':'TESTS_GENERATED', 'evaluate':'TESTS_EXECUTED', 'retry':'FAILED'}[stage]
                assert db.get(AuditRunModel, run_id).status == expected_status
    finally:
        app.dependency_overrides.clear()


def test_formal_inputs_remain_valid_through_execution_and_scoring(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unchanged.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            created = client.post('/api/v1/research/exploratory/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
                'conditions': [
                    {'label': 'Scope', 'memory_strategy': 'scope_aware', 'provider': 'rule_based'},
                    {'label': 'Temporal', 'memory_strategy': 'temporal_importance', 'provider': 'rule_based'},
                ],
            })
            assert created.status_code == 201
            for run_id in created.json()['scenarios'][0]['run_ids']:
                assert client.post(f'/api/v1/audits/{run_id}/execute').status_code == 200
                if run_id == created.json()['scenarios'][0]['run_ids'][-1]:
                    with factory() as db:
                        db.get(AuditRunModel, run_id).status = 'FAILED'
                        db.commit()
                    result = client.post(f'/api/v1/audits/{run_id}/retry')
                else:
                    result = client.post(f'/api/v1/audits/{run_id}/evaluate')
                assert result.status_code == 200, result.text
                with factory() as db:
                    assert db.get(AuditRunModel, run_id).status == 'COMPLETED'
    finally:
        app.dependency_overrides.clear()


def test_formal_matrix_supports_distinct_models_under_one_policy(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/research/exploratory/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
                'conditions': [
                    {'label':'Small model', 'memory_strategy':'scope_aware', 'provider':'ollama', 'model':'qwen3:1.7b'},
                    {'label':'Larger model', 'memory_strategy':'scope_aware', 'provider':'ollama', 'model':'qwen3:8b'},
                ],
            })
            assert response.status_code == 201, response.text
            ids = response.json()['scenarios'][0]['run_ids']
            assert len(set(ids)) == 2
            with factory() as db:
                runs = [db.get(AuditRunModel, value) for value in ids]
                assert {run.model for run in runs} == {'qwen3:1.7b', 'qwen3:8b'}
                assert {run.memory_strategy for run in runs} == {'scope_aware'}
                source = db.query(TestCaseModel).filter_by(run_id=ids[0]).all()
                peers = db.query(TestCaseModel).filter_by(run_id=ids[1]).all()
                assert {test.suite_test_id for test in peers} == {test.id for test in source}
                assert {test.prompt for test in peers} == {test.prompt for test in source}
                assert db.query(AuditRunModel).count() == 10
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('variation', ['renamed', 'whitespace'])
def test_formal_matrix_rejects_duplicate_conditions_despite_labels(variation):
    from pydantic import ValidationError
    from app.schemas.formal_experiment import ExploratoryMatrixCreateRequest
    first = {'label':'First', 'memory_strategy':'scope_aware', 'provider':'ollama', 'model':'qwen3:1.7b'}
    second = {**first, 'label':'Second', 'model':' qwen3:1.7b ' if variation == 'whitespace' else first['model']}
    with pytest.raises(ValidationError, match='combination may appear only once'):
        ExploratoryMatrixCreateRequest.model_validate({'dataset':DATASET, 'pilot':PILOT,
            'synthetic_data_confirmation':True, 'success_criteria': CRITERIA, 'conditions':[first, second]})


@pytest.mark.parametrize("drift", ["missing_binding", "wrong_binding", "source", "reference"])
def test_formal_request_rejects_unbound_or_changed_reviewed_release(drift):
    from copy import deepcopy
    from pydantic import ValidationError
    from app.schemas.formal_experiment import FormalMatrixCreateRequest
    dataset, pilot = deepcopy(DATASET), deepcopy(PILOT)
    if drift == 'missing_binding':
        pilot.pop('dataset_fingerprint_sha256')
    elif drift == 'wrong_binding':
        pilot['dataset_fingerprint_sha256'] = '0' * 64
    elif drift == 'source':
        dataset['conversations'][0]['messages'][0]['content'] += ' Additional context.'
    else:
        dataset['conversations'][0]['gold_tests'][0]['expected_behavior'] += ' Additional expected detail.'
    development=deepcopy(DATASET)
    for scenario in development['conversations']:
        for message in scenario['messages']:
            message['content'] += ' Distinct development-only context.'
    with pytest.raises(ValidationError, match='exact reviewed dataset content'):
        FormalMatrixCreateRequest.model_validate({'dataset':dataset,'pilot':pilot,
            'development_dataset':development,
            'study_design':{'sampling_rule':'Use the complete frozen inventory before viewing results; exclude none.','primary_outcome':'freshness'},
            'conditions':[{'label':'Weak','provider':'rule_based','model':'rule-based-target-ai','memory_strategy':'weak_first_hit'},
                          {'label':'Strong','provider':'rule_based','model':'rule-based-target-ai','memory_strategy':'strong_rule_based'}],
            'synthetic_data_confirmation':True, 'success_criteria': CRITERIA})


@pytest.mark.parametrize('drift', ['missing_binding', 'source'])
def test_formal_api_rejects_reviewed_release_drift_before_persistence(tmp_path, monkeypatch, drift):
    from copy import deepcopy
    from test_input_and_relationship_guards import client_for
    from app.services.formal_matrix import FormalSyntheticMatrixService
    dataset, pilot = deepcopy(DATASET), deepcopy(PILOT)
    if drift == 'missing_binding':
        pilot.pop('dataset_fingerprint_sha256')
    else:
        dataset['conversations'][0]['messages'][0]['content'] += ' Different reviewed source.'
    def forbidden_create(*args, **kwargs):
        raise AssertionError('Invalid reviewed release reached persistence.')
    monkeypatch.setattr(FormalSyntheticMatrixService, 'create', forbidden_create)
    with client_for(tmp_path) as client:
        response = client.post('/api/v1/research/exploratory/synthetic-matrix', json={
            'dataset': dataset, 'pilot': pilot, 'synthetic_data_confirmation': True, 'success_criteria': CRITERIA,
            'conditions': [
                {'label': 'None', 'provider': 'rule_based', 'model': 'rule-based-target-ai', 'memory_strategy': 'no_memory'},
                {'label': 'All', 'provider': 'rule_based', 'model': 'rule-based-target-ai', 'memory_strategy': 'full_context'},
            ],
        })
        assert response.status_code == 422, response.text
        assert 'exact reviewed dataset content' in response.text
        assert client.get('/api/v1/audits').json() == []


def test_formal_creation_requires_explicit_success_criteria():
    from pydantic import ValidationError
    from app.schemas.formal_experiment import FormalMatrixCreateRequest
    with pytest.raises(ValidationError,match="success_criteria"):
        FormalMatrixCreateRequest.model_validate({"dataset":DATASET,"pilot":PILOT,"synthetic_data_confirmation":True,
            "conditions":[{"label":"Weak","memory_strategy":"weak_first_hit"},{"label":"Scope","memory_strategy":"scope_aware"}]})


@pytest.mark.parametrize('value', [-1, 101, None, ''])
def test_success_criteria_reject_invalid_percentages(value):
    from pydantic import ValidationError
    from app.schemas.formal_experiment import FormalSuccessCriteria
    with pytest.raises(ValidationError):
        FormalSuccessCriteria.model_validate({**CRITERIA,'test_validity_min_percent':value})


def test_threshold_check_reads_saved_criteria_and_rejects_wrong_release_or_tampering(tmp_path):
    import copy
    engine=create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,autoflush=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=test_db
    try:
        with TestClient(app) as client:
            created=client.post('/api/v1/research/exploratory/synthetic-matrix',json={'dataset':DATASET,'pilot':PILOT,'synthetic_data_confirmation':True,'success_criteria':CRITERIA,'conditions':[{'label':'Scope','memory_strategy':'scope_aware','provider':'rule_based'},{'label':'Temporal','memory_strategy':'temporal_importance','provider':'rule_based'}]})
            assert created.status_code==201,created.text
            run_id=created.json()['scenarios'][0]['run_ids'][0]
            payload={'frozen_run_id':run_id,'dataset':DATASET,'predictions':{'dataset_id':DATASET['dataset_id'],'dataset_version':DATASET['dataset_version']}}
            report=client.post('/api/v1/research/formal/acceptance-check',json=payload)
            assert report.status_code==200,report.text
            assert report.json()['protocol']['criteria']==CRITERIA
            assert not report.json()['all_thresholds_met']
            wrong=copy.deepcopy(payload);wrong['dataset']['data_origin']+=' changed'
            assert client.post('/api/v1/research/formal/acceptance-check',json=wrong).status_code==422
            absent={**payload,'frozen_run_id':'missing'}
            assert client.post('/api/v1/research/formal/acceptance-check',json=absent).status_code==404
            with factory() as db:
                audit=db.get(AuditRunModel,run_id)
                metadata=copy.deepcopy(audit.reproducibility_metadata)
                metadata['formal_acceptance_protocol']['criteria']['test_validity_min_percent']=0
                audit.reproducibility_metadata=metadata;db.commit()
            assert client.post('/api/v1/research/formal/acceptance-check',json=payload).status_code==409
    finally:
        app.dependency_overrides.clear()


def test_saved_answer_binding_separates_conditions_and_detects_changed_evidence(tmp_path):
    from app.models import TargetResponseModel, EvaluationResultModel
    from app.services.formal_matrix import _stable_id
    engine=create_engine(f"sqlite:///{tmp_path / 'answer-binding.db'}")
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,autoflush=False)
    def test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=test_db
    try:
        with TestClient(app) as client:
            created=client.post('/api/v1/research/exploratory/synthetic-matrix',json={'dataset':DATASET,'pilot':PILOT,'synthetic_data_confirmation':True,'success_criteria':CRITERIA,'conditions':[{'label':'Scope','memory_strategy':'scope_aware','provider':'rule_based'},{'label':'Temporal','memory_strategy':'temporal_importance','provider':'rule_based'}]})
            assert created.status_code==201,created.text
            run_id,peer_id=created.json()['scenarios'][0]['run_ids']
            source=DATASET['conversations'][0]
            machine={'dataset_id':DATASET['dataset_id'],'dataset_version':DATASET['dataset_version'],'evaluator_predictions':[{'conversation_id':source['conversation_id'],'response_id':r['response_id'],'test_id':r['test_id'],'passed':True} for r in source['gold_evaluations']]}
            with factory() as db:
                for index,reference in enumerate(source['gold_evaluations']):
                    test_id=_stable_id('T',run_id,reference['test_id'])
                    db.add(TargetResponseModel(id=f'BOUND-R{index}',run_id=run_id,test_id=test_id,response_text=reference['response_text'],model='fixture',temperature=0))
                    db.flush()
                    db.add(EvaluationResultModel(id=f'BOUND-E{index}',test_id=test_id,response_id=f'BOUND-R{index}',passed=True,reason='Isolated engineering fixture',evaluator='rule_based'))
                db.commit()
            payload={'frozen_run_id':run_id,'dataset':DATASET,'predictions':machine}
            report=client.post('/api/v1/research/formal/acceptance-check',json=payload)
            assert report.status_code==200,report.text
            binding=report.json()['saved_evidence_binding']
            assert binding['status']=='verified' and binding['matched']==4
            assert report.json()['metrics']['conversations']==1
            assert report.json()['metrics']['evaluator_coverage']['expected']==4
            assert len(binding['receipt_sha256'])==64
            peer=client.post('/api/v1/research/formal/acceptance-check',json={**payload,'frozen_run_id':peer_id})
            assert peer.json()['saved_evidence_binding']['missing']==4
            assert not peer.json()['saved_result_thresholds_met']
            mixed={**machine,'evaluator_predictions':machine['evaluator_predictions']+[{'conversation_id':DATASET['conversations'][1]['conversation_id'],'response_id':DATASET['conversations'][1]['gold_evaluations'][0]['response_id'],'test_id':DATASET['conversations'][1]['gold_evaluations'][0]['test_id'],'passed':True}]}
            assert client.post('/api/v1/research/formal/acceptance-check',json={**payload,'predictions':mixed}).status_code==422
            with factory() as db:
                db.get(TargetResponseModel,'BOUND-R0').response_text='Changed saved answer'
                db.get(EvaluationResultModel,'BOUND-E1').passed=False
                db.commit()
            changed=client.post('/api/v1/research/formal/acceptance-check',json=payload).json()['saved_evidence_binding']
            assert changed['mismatched']==2 and changed['status']=='incomplete'
            assert changed['receipt_sha256']!=binding['receipt_sha256']
            with factory() as db:
                original=db.get(TargetResponseModel,'BOUND-R2')
                db.add(TargetResponseModel(id='AMBIGUOUS-R',run_id=run_id,test_id=original.test_id,response_text=original.response_text,model='fixture',temperature=0))
                db.commit()
            assert client.post('/api/v1/research/formal/acceptance-check',json=payload).json()['saved_evidence_binding']['ambiguous']==1
            with factory() as db:
                original=db.get(TargetResponseModel,'BOUND-R3')
                db.add(EvaluationResultModel(id='AMBIGUOUS-E',test_id=original.test_id,response_id=original.id,passed=True,reason='Second verdict fixture',evaluator='rule_based'))
                db.commit()
            duplicate=client.post('/api/v1/research/formal/acceptance-check',json=payload).json()['saved_evidence_binding']
            assert duplicate['ambiguous']==2
            with factory() as db:
                db.get(TargetResponseModel,'AMBIGUOUS-R').response_text='Changed ambiguous candidate'
                db.commit()
            assert client.post('/api/v1/research/formal/acceptance-check',json=payload).json()['saved_evidence_binding']['receipt_sha256']!=duplicate['receipt_sha256']
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('value',[0,6,1.5,True,'3'])
def test_formal_repetitions_require_bounded_integer(value):
    from pydantic import ValidationError
    from app.schemas.formal_experiment import ExploratoryMatrixCreateRequest
    with pytest.raises(ValidationError):
        ExploratoryMatrixCreateRequest.model_validate({'dataset':DATASET,'pilot':PILOT,'synthetic_data_confirmation':True,'success_criteria':CRITERIA,'repetitions':value,'conditions':[{'label':'Weak','provider':'rule_based','memory_strategy':'weak_first_hit'},{'label':'Scope','provider':'rule_based','memory_strategy':'scope_aware'}]})


def test_frozen_repetitions_execute_and_aggregate_as_two_conditions(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'repetitions.db'}")
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,autoflush=False)
    def database():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=database
    try:
        with TestClient(app) as client:
            created=client.post('/api/v1/research/exploratory/synthetic-matrix',json={'dataset':DATASET,'pilot':PILOT,'synthetic_data_confirmation':True,'success_criteria':CRITERIA,'repetitions':3,'conditions':[{'label':'Weak','provider':'rule_based','model':'rule-based-target-ai','memory_strategy':'weak_first_hit'},{'label':'Scope','provider':'rule_based','model':'rule-based-target-ai','memory_strategy':'scope_aware'}]})
            assert created.status_code==201,created.text
            plan=created.json()
            assert plan['repetition_count']==3
            assert plan['condition_count']==2
            assert plan['total_audit_runs']==30
            assert plan['total_target_calls']==120
            scenario=plan['scenarios'][0]
            assert len(scenario['run_ids'])==6
            with factory() as db:
                rows=[db.get(AuditRunModel,key) for key in scenario['run_ids']]
                assert [row.reproducibility_metadata['formal_repetition_index'] for row in rows]==[1,1,2,2,3,3]
                assert {row.random_seed for row in rows}=={42}
                assert len({row.reproducibility_metadata['configuration_fingerprint'] for row in rows})==2
                assert all(row.reproducibility_metadata['seed_control']['target']=='deterministic_local' for row in rows)
            for key in scenario['run_ids']:
                executed=client.post(f'/api/v1/audits/{key}/execute')
                assert executed.status_code==200,executed.text
                scored=client.post(f'/api/v1/audits/{key}/evaluate')
                assert scored.status_code==200,scored.text
            analytics=client.get(f"/api/v1/experiments/{scenario['experiment_id']}/results")
            assert analytics.status_code==200,analytics.text
            # Every planned repeat is a fresh execution, grouped by full frozen settings.
            conditions=analytics.json()['conditions']
            assert len(conditions)==2
            assert all(row['planned_runs']==3 and row['completed_runs']==3 for row in conditions)
            restored=client.get(f"/api/v1/research/formal/{scenario['run_ids'][0]}/plan")
            assert restored.status_code==200,restored.text
            assert restored.json()==plan
    finally:
        app.dependency_overrides.clear();engine.dispose()
