"""Mocked adapter integration: separate draft/check ledger, private-source isolation.

No semantic repair or real-provider success is established by these tests.
"""
from datetime import datetime, timezone
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.session import Base
from app.models import AgentExecutionModel, AuditRunModel, ConversationModel, TargetAgentMemoryModel
from app.schemas import AuditRun, Conversation, ConversationMessage, TargetResponse, TestCase as Case
from app.schemas.domain import TargetMemoryRetrievalResult, TargetMemoryRetrievalEvidence
from app.schemas.target_profile import TargetMemoryProfile
from app.target_ai.providers import HttpTargetAIConnector
from app.target_ai.rule_based import memory_input_evidence, selected_memory_context
from app.target_systems.controlled import ControlledTargetSystemAdapter
from app.memory_agent.answer_validation import TargetAnswerValidator, ABSTENTION_TEXT


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


@pytest.fixture
def target(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2027, 1, 2, tzinfo=timezone.utc)
    conversation = Conversation(conversation_id='C-CHECK', created_at=now, authorised=True, messages=[
        ConversationMessage(message_id='S1', role='user', timestamp=now,
                            content='My colleague planned a visit.'),
        ConversationMessage(message_id='S2', role='assistant', timestamp=now,
                            content='You could consider a later visit.'),
    ])
    db.add(ConversationModel(id=conversation.conversation_id, authorised=True))
    db.add(AuditRunModel(id='R-CHECK', conversation_id=conversation.conversation_id, status='CREATED',
                        target_configuration='strong', provider='openrouter', model='openai/gpt-6-luna',
                        temperature=0, random_seed=42, test_budget=1, prompt_template_version='test',
                        memory_strategy='strong_rule_based'))
    db.flush()
    audit = AuditRun(run_id='R-CHECK', conversation_id=conversation.conversation_id, status='CREATED',
                     target_configuration='strong', provider='openrouter', model='openai/gpt-6-luna',
                     temperature=0, random_seed=42, test_budget=1, prompt_template_version='test',
                     created_at=now, memory_strategy='strong_rule_based',
                     target_memory_profile=TargetMemoryProfile(answer_validation='source_grounding'))
    values = ['My colleague planned a visit.',
              '{"content":"You could consider a later visit.","role":"user"}']
    for i, value in enumerate(values, 1):
        db.add(TargetAgentMemoryModel(id=f'TM-CHECK-{i}', run_id=audit.run_id,
               source_conversation_id=conversation.conversation_id, canonical_value=value,
               source_message_ids=[f'S{i}'], observed_at=now, write_order=i,
               scope='episodic', lifecycle_state='ACTIVE'))
    db.flush()
    adapter = ControlledTargetSystemAdapter(db, audit)
    monkeypatch.setattr(adapter.store, 'ingest', lambda *_: None)
    adapter.ingest(conversation)
    monkeypatch.setattr(adapter.store, 'retrieve', lambda *_args, **_kwargs: TargetMemoryRetrievalResult(
        context=values, evidence=TargetMemoryRetrievalEvidence(retrieval_id='RET-CHECK',
        run_id=audit.run_id, test_id='T-CHECK', strategy='strong_rule_based',
        selected_memory_ids=['TM-CHECK-1', 'TM-CHECK-2'], created_at=now)))
    case = Case(test_id='T-CHECK', run_id=audit.run_id, dimension='accuracy',
                prompt='What was planned?', expected_behavior='PRIVATE_EXPECTED_SENTINEL',
                supporting_memory_ids=['PRIVATE_GOLD_SENTINEL'], generator_version='test')
    seen = []
    def execute(_self, private, actual_audit):
        assert private.expected_behavior == '' and private.supporting_memory_ids == []
        seen.append(list(selected_memory_context(private, actual_audit.target_configuration)))
        response = TargetResponse(response_id='RESP-CHECK', test_id=case.test_id, run_id=audit.run_id,
                                  response_text='The colleague completed a visit.', model=audit.model,
                                  temperature=0, created_at=now)
        response.execution_metadata.memory_input = memory_input_evidence(private, actual_audit.target_configuration, 'actual instruction')
        response.execution_metadata.request_attempts = 1
        response.execution_metadata.response_source = 'actual_provider'
        response.execution_metadata.reported_model = audit.model
        return response
    monkeypatch.setattr(HttpTargetAIConnector, 'execute', execute)
    yield db, audit, case, adapter, seen
    db.close()
    engine.dispose()


def install_review(monkeypatch, *, decision='corrected', fail=False, no_observation=False):
    calls = []
    def validate(self, **kwargs):
        calls.append(copy.deepcopy(kwargs))
        assert 'PRIVATE_EXPECTED_SENTINEL' not in json.dumps(kwargs)
        assert 'PRIVATE_GOLD_SENTINEL' not in json.dumps(kwargs)
        assert set(kwargs) == {'question', 'context', 'draft_answer', 'max_output_tokens',
                               'context_character_budget', 'reasoning_effort', 'source_roles'}
        final = (kwargs['draft_answer'] if decision == 'supported' else ABSTENTION_TEXT
                 if decision == 'uncertain' else 'The colleague planned a visit.')
        metadata = dict(version=self.VERSION, decision=decision,
                        validation_scope='local_byte_bindings_and_recorded_model_review_not_semantic_proof',
                        question_sha256=hashlib.sha256(kwargs['question'].encode()).hexdigest(),
                        source_context_sha256=digest(kwargs['context']), source_roles_sha256=digest(kwargs['source_roles']),
                        draft_answer_sha256=hashlib.sha256(kwargs['draft_answer'].encode()).hexdigest(),
                        final_answer_sha256=hashlib.sha256(final.encode()).hexdigest())
        self.last_execution = {'provider': self.provider, 'model': self.model, 'reported_model': self.model,
                               'request_attempts': 1, 'status': 'parsed', 'elapsed_ms': 2,
                               'requested_output_token_limit': kwargs['max_output_tokens']}
        self.last_observation = None if no_observation else {
            'instructions': 'synthetic check contract', 'prompt': json.dumps(kwargs), 'schema': {},
            'input_payload': kwargs, 'raw_input_payload': kwargs,
            'raw_model_review': {'decision': decision, 'source_quote': 'planned a visit'},
            'output_data': {**metadata, 'final_answer': final},
            'status': 'failed' if fail else 'completed', 'execution': self.last_execution,
            'error_code': 'synthetic_failure' if fail else None,
            'error_summary': 'Synthetic failed validation.' if fail else None}
        if fail:
            raise HTTPException(502, 'Synthetic failed validation.')
        return SimpleNamespace(final_answer=final, decision=decision, public_metadata=lambda: metadata)
    monkeypatch.setattr(TargetAnswerValidator, 'validate', validate)
    return calls


@pytest.mark.parametrize('decision', ['supported', 'corrected', 'uncertain'])
def test_separate_durable_draft_review_and_final_without_full_private_input(target, monkeypatch, decision):
    db, audit, case, adapter, primary = target
    calls = install_review(monkeypatch, decision=decision)
    response = adapter.answer(case, audit)
    rows = db.scalars(select(AgentExecutionModel)).all()
    assert [row.role for row in rows] == ['target_answer_draft', 'target_answer_validation']
    draft, review = rows
    assert draft.output_data['response']['response_text'] == 'The colleague completed a visit.'
    assert draft.output_data['execution_origin'] == 'copy_of_primary_target_answer'
    assert draft.input_refs['execution_origin'] == 'copy_of_primary_target_answer'
    assert calls[0]['context'] == primary[0]
    assert calls[0]['source_roles'] == ['user', 'assistant']  # stored JSON cannot spoof source role
    assert response.response_text == review.output_data['result']['final_answer']
    assert review.input_refs['draft_execution_id'] == draft.id
    assert response.execution_metadata.answer_validation['execution_id'] == review.id
    assert response.execution_metadata.response_source == 'actual_provider'
    assert response.execution_metadata.request_attempts == 1
    assert response.execution_metadata.answer_validation['execution']['request_attempts'] == 1
    assert 'input_payload' not in review.output_data and 'raw_input_payload' not in review.output_data
    assert 'context' not in review.output_data and 'private_observation' not in review.output_data
    assert primary[0][1] not in json.dumps(review.output_data)
    assert 'source_quote' in review.output_data['raw_model_review']
    assert 'raw_input_payload' in adapter.last_answer_validation_observation
    assert 'last_answer_validation_observation' not in adapter.trace()
    assert 'raw_model_review' not in response.execution_metadata.answer_validation
    assert 'claims' not in response.execution_metadata.answer_validation


@pytest.mark.parametrize('weak', [False, True])
def test_both_conditions_review_only_actual_selected_context(target, monkeypatch, weak):
    from app.schemas import TargetConfiguration
    _db, audit, case, adapter, primary = target
    audit.target_configuration = TargetConfiguration.WEAK if weak else TargetConfiguration.STRONG
    calls = install_review(monkeypatch)
    adapter.answer(case, audit)
    assert calls[0]['context'] == primary[0]
    assert len(calls[0]['context']) == (1 if weak else 2)
    assert len(calls[0]['source_roles']) == len(primary[0])


def test_default_off_preserves_original_behavior_and_makes_no_review_stage(target, monkeypatch):
    db, audit, case, adapter, _ = target
    audit.target_memory_profile.answer_validation = 'off'
    monkeypatch.setattr(TargetAnswerValidator, 'validate', lambda *_a, **_k: pytest.fail('disabled review called'))
    response = adapter.answer(case, audit)
    assert response.response_text == 'The colleague completed a visit.'
    assert response.execution_metadata.answer_validation is None
    assert db.scalars(select(AgentExecutionModel)).all() == []


@pytest.mark.parametrize('no_observation', [False, True])
def test_failure_keeps_draft_and_failed_review_and_never_returns_unchecked_answer(target, monkeypatch, no_observation):
    db, audit, case, adapter, _ = target
    install_review(monkeypatch, fail=True, no_observation=no_observation)
    with pytest.raises(HTTPException) as raised:
        adapter.answer(case, audit)
    assert raised.value.status_code == 502
    assert raised.value.target_execution['primary_status'] == 'completed'
    assert raised.value.target_execution['request_attempts'] == 1
    assert raised.value.target_execution['failure_stage'] == 'target_answer_validation'
    assert raised.value.target_execution['answer_validation']['status'] == 'failed'
    rows = db.scalars(select(AgentExecutionModel)).all()
    assert [row.status for row in rows] == ['completed', 'failed']
    assert rows[0].output_data['response']['response_text'] == 'The colleague completed a visit.'
    assert rows[1].output_data['result'] is None or rows[1].status == 'failed'
    db.commit()  # same transaction behavior as existing API failure handler
    assert len(db.scalars(select(AgentExecutionModel)).all()) == 2


@pytest.mark.parametrize('source_ids', [['S1', 'S2'], ['MISSING'], []])
def test_mixed_or_unknown_source_roles_are_unknown(target, source_ids):
    db, _audit, _case, adapter, _ = target
    db.get(TargetAgentMemoryModel, 'TM-CHECK-1').source_message_ids = source_ids
    assert adapter._answer_source_roles(['TM-CHECK-1']) == ['unknown']


def test_missing_primary_input_binding_stops_before_review_and_retains_draft(target, monkeypatch):
    db, audit, case, adapter, _ = target
    calls = install_review(monkeypatch)
    original = HttpTargetAIConnector.execute
    def broken(self, *args):
        response = original(self, *args)
        response.execution_metadata.memory_input = None
        return response
    monkeypatch.setattr(HttpTargetAIConnector, 'execute', broken)
    with pytest.raises(HTTPException):
        adapter.answer(case, audit)
    assert calls == []
    assert [r.status for r in db.scalars(select(AgentExecutionModel)).all()] == ['completed', 'failed']


def test_missing_success_observation_cannot_claim_validated(target, monkeypatch):
    _db, audit, case, adapter, _ = target
    install_review(monkeypatch, no_observation=True)
    with pytest.raises(HTTPException, match='observation'):
        adapter.answer(case, audit)


def test_public_meter_uses_allowlist_not_private_client_dictionary(target, monkeypatch):
    _db, audit, case, adapter, _ = target
    install_review(monkeypatch)
    original = TargetAnswerValidator.validate
    def with_private_meter(self, **kwargs):
        result = original(self, **kwargs)
        self.last_execution['raw_input_payload'] = {'context': kwargs['context']}
        return result
    monkeypatch.setattr(TargetAnswerValidator, 'validate', with_private_meter)
    response = adapter.answer(case, audit)
    assert 'raw_input_payload' not in response.execution_metadata.answer_validation['execution']


def test_external_adapter_cannot_silently_ignore_enabled_validation(target):
    from app.schemas import TargetSystemAdapterKind
    from app.target_systems.registry import get_target_system_adapter
    db, audit, _case, _adapter, _ = target
    audit.target_system_adapter = TargetSystemAdapterKind.EXTERNAL_HTTP
    with pytest.raises(HTTPException) as raised:
        get_target_system_adapter(db, audit)
    assert raised.value.status_code == 422


def test_real_validator_result_question_hash_matches_primary_and_both_ledger_refs(target, monkeypatch):
    # Real validator binding, synthetic full-meter client: no provider request.
    from test_target_answer_validation import FakeClient, review
    db, audit, case, adapter, _ = target
    case.prompt = 'Who said "行程🧭"?\nWhich person planned it?'
    output = review('The colleague completed a visit.')
    output['quotes'][0]['quote'] = 'My colleague planned a visit.'
    client = FakeClient(output)
    original_init = TargetAnswerValidator.__init__
    monkeypatch.setattr(TargetAnswerValidator, '__init__',
        lambda self, provider, model: original_init(self, provider, model, client=client))
    from app.memory_agent import answer_validation as module
    monkeypatch.setattr(module, 'pipeline_output_token_cap', lambda: 8192)
    response = adapter.answer(case, audit)
    rows = db.scalars(select(AgentExecutionModel)).all()
    expected = hashlib.sha256(client.calls[0]['prompt'].encode()).hexdigest()
    assert rows[1].input_fingerprint == expected  # entire JSON request remains a different fingerprint
    question = json.loads(client.calls[0]['prompt'])['question']
    expected_question = hashlib.sha256(question.encode('utf-8')).hexdigest()
    assert response.execution_metadata.memory_input.prompt_sha256 == expected_question
    assert response.execution_metadata.answer_validation['question_sha256'] == expected_question
    assert rows[0].input_refs['question_sha256'] == expected_question
    assert rows[1].input_refs['question_sha256'] == expected_question
    assert rows[1].output_data['result']['question_sha256'] == expected_question
