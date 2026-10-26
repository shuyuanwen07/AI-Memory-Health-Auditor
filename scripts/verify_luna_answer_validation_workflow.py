"""Supplement the original isolated Luna verifier with exact draft/review bindings.

Offline only: this verifier never invokes validate(), complete_json(), a provider,
or a model. Passing proves local provenance, not semantic truth or human review.
Run the original verifier with --require-reported-models first.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

MODEL = 'openai/gpt-6-luna'
ROLE = 'target_answer_validation'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(report, observations, wires, source):
    from app.schemas import TestCase
    from app.memory_agent.answer_validation import TargetAnswerValidator, AnswerValidationReview, AnswerValidationResult
    from app.target_systems.controlled import ControlledTargetSystemAdapter
    from app.target_ai.rule_based import private_context_instruction, target_question_input
    from app.target_ai.openrouter import build_openrouter_json_payload, build_openrouter_target_payload
    from app.target_ai.request_contracts import build_openrouter_request_contract
    require(report.get('status') == 'completed' and report.get('core_api_status') == 'completed', 'Incomplete workflow')
    require(report.get('planned_repetitions_per_strategy') == 3 and len(report.get('runs', [])) == 6,
            'Expected exactly six predeclared runs')
    require(not report.get('private_observation_write_failures'), 'Private capture failed')
    require(observations.get('version') == 'private-answer-validation-observation-receipts-v1'
            and observations.get('provenance') == 'actual_runtime_observation'
            and observations.get('reconstructed') is False, 'Invalid observation envelope')
    require(wires.get('version') == 'private-workflow-wire-observation-v1'
            and wires.get('provenance') == 'actual_runtime_observation'
            and wires.get('reconstructed') is False, 'Invalid wire envelope')
    observed = observations.get('observations')
    require(isinstance(observed, list) and len(observed) == 24, 'Expected 24 actual review observations')
    require([row.get('attempt') for row in observed] == list(range(1, 25)), 'Observation ordinals missing/duplicated')
    events = wires.get('events')
    require(isinstance(events, list) and events, 'Missing actual HTTP-boundary capture')
    require(report.get('configured_pipeline_output_token_cap') == 8192, 'Pipeline budget was not predeclared')
    allowed_roles = {'memory_extraction', 'relationship_analysis', 'independent_memory_review',
                     'coverage_planning', 'test_generation', 'test_review', 'target_answer', ROLE,
                     'blind_evaluation', 'post_run_diagnostic'}
    for event in events:
        contract = event.get('request_contract') or {}
        require(event.get('role') in allowed_roles and contract.get('role') == event['role']
                and contract.get('provider_name') == 'openrouter' and contract.get('model') == MODEL
                and event.get('request_contract_sha256') == digest(contract), 'Unbound workflow role/contract')
        limit = contract.get('max_tokens') or {}
        require(limit.get('present') is True and type(limit.get('value')) is int
                and 1 <= limit['value'] <= 8192, 'Uncapped or excessive workflow request')
        require(contract.get('reasoning') == ({'present': True, 'value': {'effort': 'medium'}}
                if event['role'] in {'target_answer', ROLE} else {'present': False}),
                'Unexpected reasoning presence/value')
    # Pair every before/after event, including shared-suite and failed-attempt roles.
    require(len(events) % 2 == 0, 'Incomplete HTTP-boundary event capture')
    for index in range(0, len(events), 2):
        before, after = events[index:index + 2]
        require(before.get('phase') == 'before_send' and after.get('phase') == 'after_send'
                and before.get('status') == 'prepared' and before.get('http_status') is None
                and before.get('error_type') is None
                and {k: v for k, v in before.items() if k not in {'phase', 'status', 'http_status', 'error_type'}}
                    == {k: v for k, v in after.items() if k not in {'phase', 'status', 'http_status', 'error_type'}},
                'Unpaired actual transport event')
    roles_by_source = {}
    for message in source['messages']:
        roles_by_source.setdefault(message['message_id'], []).append(message['role'].strip().lower())
    consumed, execution_ids, rows = set(), set(), []
    expected_wire = {}
    # Supply a deliberately unusable client; only pure local methods below run.
    validator = TargetAnswerValidator(provider='openrouter', model=MODEL, client=object())

    def bind_wire(meter, *, role, instructions, prompt, schema=None):
        contract = meter.get('request_contract')
        require(isinstance(contract, dict) and contract.get('provider', {}).get('present') is True,
                'Missing actual strict routing')
        options = contract['provider']['value']
        args = dict(model=MODEL, instructions=instructions, prompt=prompt,
                    max_output_tokens=8192, reasoning_effort='medium', provider_options=options)
        payload = (build_openrouter_json_payload(**args, schema_name='target_answer_source_validation', schema=schema)
                   if schema is not None else build_openrouter_target_payload(**args, temperature=0))
        rebuilt = build_openrouter_request_contract(url='https://openrouter.ai/api/v1/chat/completions',
                                                    payload=payload, role=role)
        require(contract == rebuilt and meter.get('request_contract_sha256') == digest(rebuilt),
                'Actual wire differs from pure reconstruction')
        attempts = meter.get('request_contract_attempts')
        count = meter.get('request_attempts')
        require(type(count) is int and count > 0 and isinstance(attempts, list) and len(attempts) == count,
                'HTTP attempt coverage missing')
        for index, attempt in enumerate(attempts, 1):
            require(attempt.get('attempt_index') == index and type(attempt.get('attempt_index')) is int
                    and attempt.get('role') == role and attempt.get('request_contract') == rebuilt
                    and attempt.get('request_contract_sha256') == digest(rebuilt)
                    and 'observer_error_type' not in attempt, 'Invalid HTTP attempt receipt')
        require(attempts[-1].get('status') == 'response' and attempts[-1].get('http_status') == 200,
                'Last transport attempt did not complete')
        return attempts

    for run in report['runs']:
        rid = run['run_id']
        profile = run['configuration']['target_memory_profile']
        for key, expected in {'output_token_limit': 8192, 'reasoning_effort': 'medium',
                              'answer_validation': 'source_grounding',
                              'answer_validation_output_token_limit': 8192,
                              'answer_validation_reasoning_effort': 'medium'}.items():
            require(profile.get(key) == expected, f'Unexpected frozen profile: {key}')
        require(profile.get('identity_analysis', 'off') == 'off', 'Unexpected additional identity analysis')
        require(not profile.get('retrieve_message_context', False)
                and not profile.get('additional_instructions', '').strip(), 'Unsupported context/style variant')
        for evaluation in run['evaluations']:
            judge = evaluation['judge_execution']
            require(judge.get('version') == 'judge-http-meter-v5' and judge.get('provider') == 'openrouter'
                    and judge.get('model') == judge.get('reported_model') == MODEL
                    and judge.get('configured_output_token_cap') == 8192
                    and judge.get('requested_output_token_limit') == 8192
                    and judge.get('output_budget_status') == 'configured'
                    and judge.get('completion_status') == 'complete' and judge.get('finish_reason') == 'stop',
                    'Judge actual model/completion/configured budget mismatch')
        agents = run['agents']
        stages = {row['execution_id']: row for row in agents}
        require(len(stages) == len(agents), 'Duplicate ledger execution IDs')
        require(Counter(a['role'] for a in agents if a['role'] in {'target_answer_draft', ROLE})
                == Counter({'target_answer_draft': 4, ROLE: 4}), 'Missing/extra draft or validation stages')
        tests = {test['test_id']: test for test in run['tests']}
        memories = {memory['memory_id']: memory for memory in run['memory_trace']['records']}
        response_by_test = {response['test_id']: response for response in run['responses']}
        require(len(response_by_test) == 4, 'Missing/duplicate final test responses')
        run_observed = [row for row in observed if row.get('run_id') == rid]
        require(len(run_observed) == 4, 'Review/run binding missing')
        for wrapper in run_observed:
            require(wrapper.get('analyzer_call_status') == 'completed' and wrapper.get('exception_type') is None,
                    'Failed review cannot pass')
            observation = wrapper.get('last_observation')
            require(isinstance(observation, dict) and observation.get('status') == 'completed'
                    and wrapper.get('last_observation_sha256') == digest(observation)
                    and wrapper.get('last_execution') == observation.get('execution'), 'Observation capture mismatch')
            raw, result, meter = observation['raw_input_payload'], observation['output_data'], observation['execution']
            matches = []
            for final in response_by_test.values():
                metadata = final['execution_metadata'].get('answer_validation') or {}
                if (metadata.get('draft_answer_sha256') == text_digest(raw['draft_answer'])
                        and target_question_input(tests[final['test_id']]['prompt']) == raw['question']):
                    matches.append(final)
            require(len(matches) == 1, 'Review does not identify exactly one test/draft')
            final = matches[0]
            tid = final['test_id']
            require((rid, tid) not in consumed, 'Review reused for another answer')
            consumed.add((rid, tid))
            meta = final['execution_metadata']['answer_validation']
            draft_id, check_id = meta.get('draft_execution_id'), meta.get('execution_id')
            require(draft_id and check_id and draft_id != check_id and draft_id not in execution_ids
                    and check_id not in execution_ids, 'Missing/reused stage identity')
            execution_ids.update((draft_id, check_id))
            draft_stage, check_stage = stages[draft_id], stages[check_id]
            for stage, role in ((draft_stage, 'target_answer_draft'), (check_stage, ROLE)):
                require(stage['run_id'] == rid and stage['conversation_id'] == report['conversation_id']
                        and stage['role'] == role and stage['status'] == 'completed'
                        and stage['provider'] == 'openrouter' and stage['model'] == stage['reported_model'] == MODEL,
                        'Stage identity/status/provider mismatch')
            require(draft_stage['output_data'].get('execution_origin') == 'copy_of_primary_target_answer'
                    and draft_stage['input_refs'].get('execution_accounting') == 'mirror_of_primary_target_call',
                    'Primary draft mirror accounting missing')
            draft = draft_stage['output_data']['response']
            require(draft['test_id'] == final['test_id'] and draft['response_id'] == final['response_id']
                    and draft['run_id'] == rid and draft['response_text'] == raw['draft_answer'], 'Draft carrier mismatch')
            primary = draft['execution_metadata']
            receipt = primary['memory_input']
            selected_ids = receipt['sent_memory_ids']
            require(isinstance(selected_ids, list) and len(selected_ids) == len(set(selected_ids)), 'Invalid sent memory IDs')
            context = [memories[mid]['canonical_value'].strip() for mid in selected_ids]
            require(context == raw['selected_context'] and receipt['record_count'] == len(context),
                    'Review did not receive the exact delivered records')
            source_roles = []
            for mid in selected_ids:
                source_ids = memories[mid]['source_message_ids']
                values = [roles_by_source.get(sid, []) for sid in source_ids]
                role_set = {value[0] for value in values if len(value) == 1}
                source_roles.append(next(iter(role_set)) if source_ids and all(len(v) == 1 and v[0] in {'user', 'assistant'}
                                     for v in values) and len(role_set) == 1 else 'unknown')
            require(raw['source_roles'] == source_roles, 'Source speaker roles not bound to original conversation')
            question = target_question_input(tests[tid]['prompt'])
            expected_refs = {'test_id': tid, 'selected_memory_ids': selected_ids, 'source_roles': source_roles,
                             'question_sha256': text_digest(question), 'source_context_sha256': digest(context),
                             'source_roles_sha256': digest(source_roles), 'draft_answer_sha256': text_digest(draft['response_text'])}
            for stage in (draft_stage, check_stage):
                require(all(stage['input_refs'].get(k) == v for k, v in expected_refs.items()), 'Stage input references differ')
            require(check_stage['input_refs'].get('draft_execution_id') == draft_id, 'Review is not linked to its draft')
            require(receipt['prompt_sha256'] == text_digest(question) and receipt['context_sha256'] == digest(context),
                    'Primary input receipt mismatch')
            private_test = TestCase.model_validate(tests[tid]).model_copy(update={'target_memory_context': context})
            instructions = private_context_instruction(private_test, 'strong')
            require(receipt['instruction_sha256'] == text_digest(instructions), 'Primary instruction hash mismatch')
            require(primary.get('reported_model') == MODEL and primary.get('requested_output_token_limit') == 8192
                    and primary.get('requested_reasoning_effort') == 'medium'
                    and primary.get('completion_status') == 'complete' and primary.get('finish_reason') == 'stop',
                    'Primary completion/control mismatch')
            payload = validator.build_request_payload(question=question, context=context,
                draft_answer=draft['response_text'], source_roles=source_roles)
            schema = validator.REQUEST_SCHEMA.model_json_schema()
            prompt = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            require(observation['input_payload'] == payload and observation['prompt'] == prompt
                    and observation['schema'] == schema and observation['instructions'] == validator.INSTRUCTIONS
                    and observation['version'] == validator.VERSION and observation['role'] == ROLE,
                    'Review prompt/schema reconstruction mismatch')
            require(observation['declared_output_token_limit'] == 8192
                    and observation['configured_output_token_cap'] == 8192
                    and observation['requested_output_token_limit'] == 8192
                    and observation['requested_reasoning_effort'] == 'medium'
                    and observation['context_character_budget'] == profile['context_character_budget'], 'Review budget mismatch')
            validator._verify_execution(meter, prompt=prompt, schema=schema, output=observation['raw_model_review'],
                                        cap=8192, configured_cap=8192, effort='medium')
            bound = validator._bind(AnswerValidationReview.model_validate(observation['raw_model_review']),
                                    records=payload['selected_records'], draft=draft['response_text'])
            expected_result = AnswerValidationResult(**bound, version=validator.VERSION,
                validation_scope='local_byte_bindings_and_recorded_model_review_not_semantic_proof',
                question_sha256=digest(question), source_context_sha256=digest(context), source_roles_sha256=digest(source_roles),
                draft_answer_sha256=text_digest(draft['response_text']), final_answer_sha256=text_digest(bound['final_answer']))
            require(result == expected_result.model_dump(mode='json') and check_stage['output_data'] == {
                'result': result, 'raw_model_review': observation['raw_model_review']}, 'Local quote/result binding differs')
            require(all(meta.get(k) == v for k, v in expected_result.public_metadata().items())
                    and meta.get('execution') == ControlledTargetSystemAdapter._answer_validation_meter(meter)
                    and final['response_text'] == result['final_answer'], 'Final delivery/result/meter differs')
            require(meta.get('final_text_source') == {'supported': 'original_draft', 'corrected': 'validator_corrected',
                    'uncertain': 'fixed_abstention'}[result['decision']], 'Final text origin missing')
            for stage, execution in ((draft_stage, primary), (check_stage, meter)):
                diagnostics = stage.get('error_diagnostics') or {}
                require(all(diagnostics.get(key) == execution.get(key) for key in
                    ('request_contract', 'request_contract_sha256', 'request_contract_attempts')),
                    'Ledger/actual wire provenance differs')
            expected_wire.setdefault((rid, 'target_answer'), []).extend(bind_wire(primary, role='target_answer',
                instructions=instructions, prompt=question))
            expected_wire.setdefault((rid, ROLE), []).extend(bind_wire(meter, role=ROLE,
                instructions=validator.INSTRUCTIONS, prompt=prompt, schema=schema))
            rows.append({'run_id': rid, 'test_id': tid, 'response_id': final['response_id'],
                         'draft_execution_id': draft_id, 'validation_execution_id': check_id,
                         'decision': result['decision'], 'draft_sha256': text_digest(draft['response_text']),
                         'final_sha256': text_digest(final['response_text']), 'source_context_sha256': digest(context)})
    require(len(consumed) == 24, 'Not all answers covered')
    for role in ('target_answer', ROLE):
        require(all(event.get('run_id') in {r['run_id'] for r in report['runs']}
                    for event in events if event.get('role') == role), 'Unbound answer/review HTTP event')
    for (rid, role), attempts in expected_wire.items():
        actual = [event for event in events if event.get('run_id') == rid and event.get('role') == role]
        expected = []
        for attempt in attempts:
            before = {**attempt, 'status': 'prepared', 'http_status': None, 'error_type': None}
            expected.extend([{'run_id': rid, **before, 'phase': 'before_send'},
                             {'run_id': rid, **attempt, 'phase': 'after_send'}])
        require(actual == expected, 'Actual per-HTTP attempt events differ from execution meters')
    return {'passed': True, 'verified_answers': 24, 'unique_draft_stages': 24, 'unique_validation_stages': 24,
            'primary_draft_network_calls': 24, 'additional_validation_logical_calls': 24,
            'draft_ledger_entries_are_mirrors_not_extra_calls': True,
            'http_attempts': {role: sum(len(v) for (rid, r), v in expected_wire.items() if r == role)
                              for role in ('target_answer', ROLE)},
            'decisions': dict(Counter(row['decision'] for row in rows)), 'rows': rows,
            'captured_http_attempt_counts_by_role': dict(Counter(e['role'] for e in events if e['phase'] == 'after_send')),
            'judge_budget_meter_verified': True,
            'judge_wire_observer_available': any(e.get('role') == 'blind_evaluation' for e in events),
            'judge_wire_limitation': 'Current full-workflow judge directly dispatches httpx; meter-v5 and source-built cap verified, no missing actual judge wire contract inferred.',
            'total_cost_or_all_attempt_usage_proven': False,
            'scope': 'Exact local provenance, byte/span bindings and actual wire controls; not semantic truth, human gold or universal safety.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--original-verification', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--wire', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'backend'))
    report = json.loads(args.report.read_text())
    original = json.loads(args.original_verification.read_text())
    require(original.get('passed') is True and original.get('report_sha256') == hashlib.sha256(args.report.read_bytes()).hexdigest(),
            'Original strict verifier must pass against this exact report first')
    for path, key in ((args.observations, 'answer_validation_observations_sha256'),
                      (args.wire, 'actual_wire_observations_sha256')):
        require(report.get(key) == hashlib.sha256(path.read_bytes()).hexdigest(), 'Private sidecar file hash mismatch')
    source_path = root / 'datasets/smoke/qwen-four-dimension-source-v1.json'
    require(report['source_sha256'] == hashlib.sha256(source_path.read_bytes()).hexdigest(), 'Approved source hash mismatch')
    from verify_luna_isolated_api import verify as original_verify
    approval_path = root / 'datasets/smoke/qwen-four-dimension-approval-v1.json'
    require(report['approval_sha256'] == hashlib.sha256(approval_path.read_bytes()).hexdigest(), 'Approval hash mismatch')
    # Independently rerun all original local checks with the strict option;
    # an earlier lax or differently bound verifier result cannot substitute.
    original_rebuilt = original_verify(report, json.loads(args.report.with_suffix('.bundle.json').read_text()),
        list(csv.DictReader(args.report.with_suffix('.csv').open())), json.loads(source_path.read_text()),
        json.loads(approval_path.read_text()), require_reported_models=True)
    require(original == {**original_rebuilt, 'report_sha256': hashlib.sha256(args.report.read_bytes()).hexdigest()},
            'Original strict verification receipt differs from current exact reconstruction')
    result = verify(report, json.loads(args.observations.read_text()), json.loads(args.wire.read_text()),
                    json.loads(source_path.read_text()))
    result.update(report_sha256=hashlib.sha256(args.report.read_bytes()).hexdigest(),
                  original_verification_sha256=hashlib.sha256(args.original_verification.read_bytes()).hexdigest(),
                  observation_file_sha256=hashlib.sha256(args.observations.read_bytes()).hexdigest(),
                  wire_file_sha256=hashlib.sha256(args.wire.read_bytes()).hexdigest())
    with args.output.open('x') as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
