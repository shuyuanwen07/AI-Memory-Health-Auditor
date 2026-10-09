"""Verify receipts against the actual Qwen request, including final filtering."""
import hashlib
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from app.schemas import AuditRun, AuditStatus, Dimension, TargetConfiguration, TargetProvider, TestCase as Case
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.target_ai.providers import HttpTargetAIConnector
from app.api.routes import target_retrieval_trace_schema


def test_trace_question_comes_from_linked_test_not_retrieval_position():
    from app.models import TestCaseModel, TargetResponseModel
    def get(model, identity):
        if model is TestCaseModel:
            assert identity == 'T-REAL'
            return SimpleNamespace(prompt='Which database applies now?')
        assert model is TargetResponseModel and identity == 'R1'
        return SimpleNamespace(execution_metadata={})
    retrieval = SimpleNamespace(id='RET3', test_id='T-REAL', strategy='full_context',
        selected_memory_ids=[], ranking_evidence=[], final_response_id='R1',
        created_at=datetime.now(timezone.utc))
    result = target_retrieval_trace_schema(SimpleNamespace(get=get), retrieval)
    assert result.question == 'Which database applies now?'


@pytest.mark.parametrize('configuration, expected_ids, empty', [
    (TargetConfiguration.WEAK, ['TM1'], False),
    (TargetConfiguration.STRONG, ['TM1', 'TM3'], False),
    (TargetConfiguration.STRONG, [], True),
])
def test_qwen_receipt_tracks_final_context_not_retrieved_candidates(monkeypatch, configuration, expected_ids, empty):
    audit = AuditRun(run_id='RUN1', conversation_id='C1', status=AuditStatus.CREATED,
                     target_configuration=configuration, provider=TargetProvider.OLLAMA,
                     model='qwen-test', temperature=0, random_seed=42, test_budget=1,
                     prompt_template_version='v1', created_at=datetime.now(timezone.utc))
    test = Case(test_id='T1', run_id='RUN1', dimension=Dimension.FRESHNESS,
                prompt='Which database applies?', expected_behavior='EVALUATOR_ONLY_SECRET',
                supporting_memory_ids=['GOLD'], generator_version='v1',
                target_memory_context=['GOLD_CONTEXT_MUST_BE_REPLACED'])
    retrieval = SimpleNamespace(context=['  MySQL  ', 'MySQL', 'PostgreSQL'],
        evidence=SimpleNamespace(retrieval_id='RET1', selected_memory_ids=['TM1', 'TM2', 'TM3']))
    if empty:
        retrieval.context = []
        retrieval.evidence.selected_memory_ids = []
    adapter = ControlledTargetSystemAdapter.__new__(ControlledTargetSystemAdapter)
    adapter.audit = audit
    adapter._conversation = object()
    adapter.store = SimpleNamespace(retrieve=lambda *args: retrieval)
    captured = {}

    def post(url, headers, payload):
        captured.update(payload)
        return {'message': {'content': 'PostgreSQL'}}

    monkeypatch.setattr(HttpTargetAIConnector, '_post', staticmethod(post))
    response = adapter.answer(test, audit)
    receipt = response.execution_metadata.memory_input
    assert receipt.sent_memory_ids == expected_ids
    assert receipt.record_count == len(expected_ids)
    messages = captured['messages']
    assert receipt.instruction_sha256 == hashlib.sha256(messages[0]['content'].encode()).hexdigest()
    assert receipt.prompt_sha256 == hashlib.sha256(messages[1]['content'].encode()).hexdigest()
    assert 'EVALUATOR_ONLY_SECRET' not in str(messages)
    assert 'GOLD_CONTEXT' not in str(messages)
    assert ('PostgreSQL' in messages[0]['content']) == (configuration == TargetConfiguration.STRONG and not empty)
    # Matching the expected answer does not establish memory use: Weak did not receive it.
    assert response.response_text == 'PostgreSQL'


def test_legacy_or_unsuccessful_retrieval_does_not_invent_input_receipt():
    retrieval = SimpleNamespace(id='RET1', test_id='T1', strategy='full_context',
        selected_memory_ids=['TM1'], ranking_evidence=[], final_response_id='R1',
        created_at=datetime.now(timezone.utc))
    db = SimpleNamespace(get=lambda *args: SimpleNamespace(execution_metadata={}))
    assert target_retrieval_trace_schema(db, retrieval).memory_input is None
    retrieval.final_response_id = None
    assert target_retrieval_trace_schema(db, retrieval).memory_input is None
