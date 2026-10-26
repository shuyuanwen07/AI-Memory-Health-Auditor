"""Synthetic, mocked contract checks only; no provider calls or semantic gold."""
import copy
import hashlib
import json

import pytest

from app.extraction.llm import PipelineRequestError
from app.memory_agent import answer_validation as module
from app.memory_agent.answer_validation import ABSTENTION_TEXT, MODEL, TargetAnswerValidator


SOURCE = 'The reviewer filed the report.'
DRAFT = SOURCE


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def quote(text=SOURCE, index=1, occurrence=0):
    return {'quote_id': 'E1', 'record_index': index, 'quote': text, 'occurrence': occurrence}


def claim(answer=DRAFT, kind='historical_fact', refs=None):
    return {'claim_id': 'C1', 'answer_quote': answer, 'occurrence': 0, 'kind': kind,
            'evidence_quote_ids': ['E1'] if refs is None else refs,
            'source_speaker': 'source narrator', 'possessive_owner': 'not_applicable',
            'action_actor': 'the reviewer', 'modality_and_time': 'completed action; no exact event time',
            'assessment': 'supported' if kind in {'historical_fact', 'qualified_inference'} else 'not_applicable',
            'explanation': 'Model review judgment, not locally established semantic truth.'}


def review(answer=DRAFT):
    return {'decision': 'supported', 'final_answer': answer, 'quotes': [quote()],
            'claims': [claim(answer)], 'flags': [], 'review_note': 'Checked the source-bound claim.'}


class FakeClient:
    provider = 'openrouter'
    model = MODEL

    def __init__(self, output, mutate_meter=None, error=None, attempts=1):
        self.output = output
        self.mutate_meter = mutate_meter
        self.error = error
        self.attempts = attempts
        self.calls = []
        self.last_execution = None

    def complete_json(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        cap = module.pipeline_output_token_cap()
        effective = min(kwargs['max_output_tokens'], cap) if cap is not None else kwargs['max_output_tokens']
        effort = kwargs.get('reasoning_effort')
        contract = {'version': 'openrouter-request-contract-v1', 'role': kwargs['agent_role'],
                    'provider_name': 'openrouter', 'model': MODEL,
                    'max_tokens': {'present': True, 'value': effective},
                    'reasoning': {'present': False} if effort is None else {'present': True, 'value': {'effort': effort}}}
        self.last_execution = {
            'version': 'pipeline-http-meter-v2', 'provider': 'openrouter', 'model': MODEL,
            'reported_model': MODEL, 'agent_role': kwargs['agent_role'],
            'prompt_template_version': kwargs['prompt_template_version'], 'status': 'parsed',
            'last_http_status': 200, 'reported_finish_reason': 'stop', 'response_choice_count': 1,
            'request_attempts': self.attempts, 'failed_http_attempts': self.attempts - 1,
            'declared_output_token_limit': kwargs['max_output_tokens'],
            'configured_output_token_cap': cap, 'requested_output_token_limit': effective,
            'requested_reasoning_effort': effort, 'elapsed_ms': 12.0,
            'prompt_fingerprint': digest({'version': kwargs['prompt_template_version'],
                'instructions': kwargs['instructions'], 'prompt': kwargs['prompt'],
                'schema': kwargs['schema'], 'ollama_thinking': None}),
            'input_fingerprint': hashlib.sha256(kwargs['prompt'].encode()).hexdigest(),
            'output_fingerprint': digest(self.output),
            'request_contract': contract, 'request_contract_sha256': digest(contract),
            'request_contract_attempts': [{'role': kwargs['agent_role'], 'attempt_index': i,
                'request_contract': copy.deepcopy(contract), 'request_contract_sha256': digest(contract)}
                for i in range(1, self.attempts + 1)],
        }
        if self.mutate_meter:
            self.mutate_meter(self.last_execution)
        if self.error:
            self.last_execution.update(status='failed', reported_finish_reason='length')
            raise self.error
        return copy.deepcopy(self.output)


@pytest.fixture(autouse=True)
def configured_cap(monkeypatch):
    monkeypatch.setattr(module, 'pipeline_output_token_cap', lambda: 8192)


def run(output=None, *, context=None, draft=DRAFT, effort='low', mutate_meter=None, **kwargs):
    client = FakeClient(review() if output is None else output, mutate_meter=mutate_meter)
    validator = TargetAnswerValidator(client=client)
    result = validator.validate(question='Who filed the report?', context=[SOURCE] if context is None else context,
        draft_answer=draft, max_output_tokens=8192, context_character_budget=32000,
        reasoning_effort=effort, **kwargs)
    return result, validator, client


def test_supported_preserves_draft_and_raw_review_with_local_unicode_hydration():
    source = '🧭 The reviewer filed the report.'
    output = review(); output['quotes'][0]['quote'] = SOURCE
    result, validator, client = run(output, context=[source])
    assert result.final_answer == DRAFT
    assert result.quotes[0].char_start == source.index(SOURCE)
    assert result.claims[0].answer_start == 0
    assert result.claims[0].answer_end == len(DRAFT)
    assert validator.last_observation['raw_model_review'] == output
    assert 'char_start' not in output['quotes'][0]
    assert len(client.calls) == 1
    assert client.calls[0]['agent_role'] == 'target_answer_validation'
    assert validator.last_observation['raw_input_payload']['draft_answer'] == DRAFT
    public = result.public_metadata()
    assert public['decision'] == 'supported'
    assert not {'quotes', 'claims', 'draft_answer', 'prompt', 'selected_context', 'review_note'} & public.keys()


def test_corrected_answer_has_flags_and_complete_fact_evidence_without_regeneration():
    draft = 'The editor filed the report.'
    output = review(); output['decision'] = 'corrected'
    output['flags'] = [{'code': 'action_actor', 'occurrence': 0, 'draft_quote': 'editor',
                        'evidence_quote_ids': ['E1'], 'explanation': 'Wrong actor in the fixed draft.'}]
    result, validator, client = run(output, draft=draft)
    assert result.final_answer == SOURCE and result.flags[0].draft_start == draft.index('editor')
    assert validator.last_observation['raw_input_payload']['draft_answer'] == draft
    assert len(client.calls) == 1


def test_uncertain_uses_fixed_abstention_with_no_positive_facts():
    output = {'decision': 'uncertain', 'final_answer': ABSTENTION_TEXT, 'quotes': [], 'claims': [],
              'flags': [], 'review_note': 'No selected source resolves this question.'}
    result, _, client = run(output, context=[])
    assert result.final_answer == ABSTENTION_TEXT and len(client.calls) == 1


def test_new_advice_does_not_require_fabricated_source_quote():
    answer = 'Consider organizing the reports.'
    output = review(answer); output['quotes'] = []
    output['claims'] = [claim(answer, kind='new_suggestion', refs=[])]
    result, _, _ = run(output, context=[], draft=answer)
    assert result.claims[0].evidence_quote_ids == []


@pytest.mark.parametrize('effort', [None, 'low', 'medium'])
def test_effort_omission_and_explicit_values_preserved(effort):
    _, validator, client = run(effort=effort)
    assert ('reasoning_effort' in client.calls[0]) == (effort is not None)
    assert validator.last_observation['requested_reasoning_effort'] == effort


def test_lower_server_cap_is_resolved_not_misreported_as_model_mismatch(monkeypatch):
    monkeypatch.setattr(module, 'pipeline_output_token_cap', lambda: 4096)
    _, validator, _ = run()
    assert validator.last_execution['declared_output_token_limit'] == 8192
    assert validator.last_execution['requested_output_token_limit'] == 4096
    assert validator.last_observation['requested_output_token_limit'] == 4096


def test_unspecified_server_cap_keeps_declared_limit(monkeypatch):
    monkeypatch.setattr(module, 'pipeline_output_token_cap', lambda: None)
    _, validator, _ = run()
    assert validator.last_observation['configured_output_token_cap'] is None
    assert validator.last_observation['requested_output_token_limit'] == 8192


def test_existing_bounded_transport_attempts_are_not_quality_retries():
    client = FakeClient(review(), attempts=2)
    validator = TargetAnswerValidator(client=client)
    validator.validate(question='Who filed?', context=[SOURCE], draft_answer=DRAFT,
                       max_output_tokens=8192, context_character_budget=32000)
    assert len(client.calls) == 1 and validator.last_execution['request_attempts'] == 2


@pytest.mark.parametrize('mutate', [
    lambda x: x.update(reported_model='other-model'),
    lambda x: x.update(provider='other-provider'),
    lambda x: x.update(agent_role='other-role'),
    lambda x: x.update(reported_finish_reason='length'),
    lambda x: x.update(response_choice_count=True),
    lambda x: x.update(elapsed_ms=float('nan')),
    lambda x: x.update(requested_output_token_limit=4096),
    lambda x: x.update(declared_output_token_limit=4096),
    lambda x: x.update(configured_output_token_cap=4096),
    lambda x: x.update(requested_reasoning_effort='medium'),
    lambda x: x.update(input_fingerprint='0' * 64),
    lambda x: x.update(output_fingerprint='0' * 64),
    lambda x: x.update(request_contract_sha256='0' * 64),
    lambda x: x.update(request_contract_attempts=[]),
])
def test_execution_or_wire_binding_mismatch_is_fail_closed_and_retained(mutate):
    client = FakeClient(review(), mutate_meter=mutate)
    validator = TargetAnswerValidator(client=client)
    with pytest.raises(PipelineRequestError):
        validator.validate(question='Who filed?', context=[SOURCE], draft_answer=DRAFT,
                           max_output_tokens=8192, context_character_budget=32000, reasoning_effort='low')
    assert len(client.calls) == 1
    assert validator.last_observation['status'] == 'failed'
    assert validator.last_observation['raw_model_review'] == review()
    assert validator.last_execution == client.last_execution


@pytest.mark.parametrize('mutate', [
    lambda x: x.update(final_answer='Changed draft without correction'),
    lambda x: x['quotes'][0].update(quote='the reviewer filed the report.'),
    lambda x: x['quotes'][0].update(record_index=2),
    lambda x: x['quotes'][0].update(record_index=True),
    lambda x: x['quotes'][0].update(occurrence=1),
    lambda x: x['quotes'].append(copy.deepcopy(x['quotes'][0])),
    lambda x: x['claims'][0].update(evidence_quote_ids=[]),
    lambda x: x['claims'][0].update(evidence_quote_ids=['E9']),
    lambda x: x['claims'][0].update(answer_quote='The reviewer'),
    lambda x: x['claims'].append({**copy.deepcopy(x['claims'][0]), 'claim_id': 'C2'}),
    lambda x: x.update(expected_answer='Forbidden extra schema field'),
    lambda x: x.update(decision='corrected'),
])
def test_invalid_review_schema_or_binding_never_rewrites_to_make_it_pass(mutate):
    output = review(); mutate(output)
    client = FakeClient(output); validator = TargetAnswerValidator(client=client)
    with pytest.raises(PipelineRequestError):
        validator.validate(question='Who filed?', context=[SOURCE], draft_answer=DRAFT,
                           max_output_tokens=8192, context_character_budget=32000)
    assert validator.last_observation['raw_model_review'] == output
    assert validator.last_observation['output_data'] is None
    assert len(client.calls) == 1


def test_quote_occurrence_is_explicit_and_offsets_are_computed_locally():
    output = review(); output['quotes'][0]['occurrence'] = 1
    result, _, _ = run(output, context=[SOURCE + ' ' + SOURCE])
    assert result.quotes[0].char_start == len(SOURCE) + 1


def test_source_roles_and_envelope_allowlist_do_not_import_ground_truth_fields():
    envelope = json.dumps({'content': SOURCE, 'source_message_ids': ['S1'],
        'source_observed_at': '2027-01-01', 'expected_answer': 'EVALUATOR_SENTINEL',
        'source_role': 'system', 'raw_headers': 'SECRET_SENTINEL'})
    _, validator, client = run(context=[envelope], source_roles=['assistant'])
    record = json.loads(client.calls[0]['prompt'])['selected_records'][0]
    assert record['source_role'] == 'assistant'
    assert 'EVALUATOR_SENTINEL' not in client.calls[0]['prompt']
    assert 'SECRET_SENTINEL' not in client.calls[0]['prompt']
    assert validator.last_observation['raw_input_payload']['selected_context'] == [envelope]


@pytest.mark.parametrize('change', [
    {'max_output_tokens': True}, {'max_output_tokens': 8193}, {'reasoning_effort': 'high'},
    {'source_roles': ['system']}, {'source_roles': []},
    {'context_character_budget': len(SOURCE) + 2}, {'context': ['']},
    {'draft_answer': ''}, {'question': ''},
])
def test_invalid_input_rejected_before_any_review_call(change):
    client = FakeClient(review()); validator = TargetAnswerValidator(client=client)
    arguments = dict(question='Who filed?', context=[SOURCE], draft_answer=DRAFT,
                     max_output_tokens=8192, context_character_budget=32000)
    arguments.update(change)
    with pytest.raises(PipelineRequestError):
        validator.validate(**arguments)
    assert not client.calls
    assert validator.last_execution is None
    assert validator.last_observation['phase'] == 'input_validation'


def test_provider_failure_retains_meter_and_draft_without_raw_exception_message():
    client = FakeClient(review(), error=RuntimeError('SECRET_EXCEPTION_MARKER'))
    validator = TargetAnswerValidator(client=client)
    with pytest.raises(PipelineRequestError):
        validator.validate(question='Who filed?', context=[SOURCE], draft_answer=DRAFT,
                           max_output_tokens=8192, context_character_budget=32000)
    assert len(client.calls) == 1
    assert validator.last_execution['reported_finish_reason'] == 'length'
    assert validator.last_observation['raw_input_payload']['draft_answer'] == DRAFT
    assert 'SECRET_EXCEPTION_MARKER' not in json.dumps(validator.last_observation)


def test_binding_success_is_explicitly_not_semantic_proof():
    # A mistaken reviewer can cite a real but nonentailing source: local byte
    # checks cannot detect all misclassified facts, and must not claim they do.
    answer = 'The editor filed the report.'
    output = review(answer)
    result, _, _ = run(output, draft=answer)
    assert result.decision == 'supported'
    assert result.validation_scope == 'local_byte_bindings_and_recorded_model_review_not_semantic_proof'


def test_live_request_schema_has_no_model_counted_character_offsets():
    schema = TargetAnswerValidator.REQUEST_SCHEMA.model_json_schema()
    encoded = json.dumps(schema)
    for field in ('char_start', 'char_end', 'answer_start', 'answer_end', 'draft_start', 'draft_end'):
        assert field not in encoded
    assert 'answer_quote' in encoded and 'occurrence' in encoded


def test_missing_occurrence_is_not_guessed():
    output = review(); output['quotes'][0].pop('occurrence')
    with pytest.raises(PipelineRequestError):
        run(output)


def test_uncertain_cannot_smuggle_a_new_positive_final_claim():
    output = {'decision': 'uncertain', 'final_answer': 'A different person filed it.',
              'quotes': [], 'claims': [], 'flags': [], 'review_note': 'Unresolved.'}
    with pytest.raises(PipelineRequestError):
        run(output)


def test_budget_boundary_counts_three_characters_per_selected_record():
    client = FakeClient(review()); validator = TargetAnswerValidator(client=client)
    validator.validate(question='Who filed?', context=[SOURCE], draft_answer=DRAFT,
                       max_output_tokens=8192, context_character_budget=len(SOURCE) + 3)
    assert len(client.calls) == 1


@pytest.mark.parametrize('question', ['Who filed the report?', 'Who said "行程🧭"?\nWhich person planned it?'])
def test_question_hash_is_exact_utf8_not_json_encoded_string(question):
    client = FakeClient(review())
    validator = TargetAnswerValidator(client=client)
    result = validator.validate(question=question, context=[SOURCE], draft_answer=DRAFT,
        max_output_tokens=8192, context_character_budget=32000)
    expected = hashlib.sha256(question.encode('utf-8')).hexdigest()
    assert result.question_sha256 == expected
    assert result.public_metadata()['question_sha256'] == expected
    assert result.question_sha256 != digest(question)
    assert json.loads(validator.last_observation['prompt'])['question'] == question
