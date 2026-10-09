"""The formal matrix persists only approved synthetic scenarios and frozen suites."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from app.database.session import Base, get_db
from app.main import app
from app.models import AuditRunModel, ExperimentModel, TestCaseModel


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
            created = client.post('/api/v1/research/formal/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True,
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
        "dataset": DATASET, "pilot": PILOT, "synthetic_data_confirmation": True,
        "conditions": [
            {"label": "Weak", "memory_strategy": "weak_first_hit", "provider": "rule_based", "model": "rule-based-target-ai"},
            {"label": "Scope", "memory_strategy": "scope_aware", "provider": "rule_based", "model": "rule-based-target-ai"},
        ],
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/research/formal/synthetic-matrix", json=payload)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["scenario_count"] == 5
            assert body["total_audit_runs"] == 10
            assert body["total_target_calls"] == 40
            duplicate = client.post("/api/v1/research/formal/synthetic-matrix", json=payload)
            assert duplicate.status_code == 409
    finally:
        app.dependency_overrides.clear()

    db = factory()
    try:
        assert db.query(ExperimentModel).count() == 5
        assert db.query(AuditRunModel).count() == 10
        from app.services.formal_freeze import formal_runtime_signature
        runtime = formal_runtime_signature()
        for audit in db.query(AuditRunModel).all():
            assert audit.target_system_adapter_version == runtime['adapter']
            assert audit.reproducibility_metadata['formal_runtime_signature'] == runtime
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
            response = client.post("/api/v1/research/formal/synthetic-matrix", json={
                "dataset": non_synthetic, "pilot": PILOT, "synthetic_data_confirmation": True,
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
            created = client.post('/api/v1/research/formal/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True,
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
@pytest.mark.parametrize('component', ['message', 'memory', 'relationship', 'question', 'reference', 'configuration', 'legacy'])
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
            created = client.post('/api/v1/research/formal/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True,
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
            created = client.post('/api/v1/research/formal/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True,
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
            response = client.post('/api/v1/research/formal/synthetic-matrix', json={
                'dataset': DATASET, 'pilot': PILOT, 'synthetic_data_confirmation': True,
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
    from app.schemas.formal_experiment import FormalMatrixCreateRequest
    first = {'label':'First', 'memory_strategy':'scope_aware', 'provider':'ollama', 'model':'qwen3:1.7b'}
    second = {**first, 'label':'Second', 'model':' qwen3:1.7b ' if variation == 'whitespace' else first['model']}
    with pytest.raises(ValidationError, match='combination may appear only once'):
        FormalMatrixCreateRequest.model_validate({'dataset':DATASET, 'pilot':PILOT,
            'synthetic_data_confirmation':True, 'conditions':[first, second]})
