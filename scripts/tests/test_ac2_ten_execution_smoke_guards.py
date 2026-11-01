"""Execution preparation cannot turn AI-only or changed data into paid dispatch."""
import builtins
import hashlib
import json
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import urlparse

import pytest

from scripts.ac2_ten_execution_common import (
    EXPECTED_IDS,
    SCRIPT_NAMES,
    GuardError,
    check_protocol,
    read,
    save,
    sha,
    validate_approval,
)
from scripts.register_ac2_ten_execution_smoke_20261101 import (
    prepare,
    register,
    restore_approved_profile,
)
from scripts.run_ac2_ten_execution_smoke_20261101 import (
    judge_receipt_ok,
    run,
    target_receipt_ok,
    writer_receipt_ok,
)


def fixture(tmp_path):
    root = tmp_path
    source = root / 'source'
    source.mkdir()
    rows, ids = [], []
    dimensions = ['accuracy', 'freshness', 'conflict_resolution', 'appropriate_use']
    profile = {'label': 'Original configuration', 'version': 1, 'identity_analysis': 'off', 'output_token_limit': None}
    for index, hid in enumerate(EXPECTED_IDS):
        rid = f'R{index}'
        questions = [{'test_id': f'T{index}-{dim}', 'run_id': rid, 'dimension': dim,
                      'test_type': 'direct', 'prompt': f'Question for {dim}?',
                      'expected_behavior': f'Stated behavior for {dim}.',
                      'supporting_memory_ids': [f'M{index}'], 'generator_version': 'fixture'} for dim in dimensions]
        audit = {'run_id': rid, 'conversation_id': f'C{index}', 'target_configuration': 'weak',
                 'retrieval_mode': 'fixed', 'test_budget': 4, 'pipeline_provider': 'openai',
                 'pipeline_model': 'gpt-6-astra', 'target_memory_profile': profile}
        record = {'run_id': rid, 'status': 'completed', 'requests': [
            {'method': 'POST', 'path': f'/audits/{rid}/generate-tests', 'status': 'returned', 'response': questions},
            {'method': 'GET', 'path': f'/audits/{rid}', 'status': 'returned', 'response': audit}]}
        path = source / f'{hid}.json'
        save(path, record, exclusive=True)
        rows.append({'history_id': hid, 'record_sha256': sha(path)})
        ids.extend(q['test_id'] for q in questions)
    save(source / 'summary.json', {'histories': 10, 'generated_questions': 40, 'runs': rows}, exclusive=True)
    review = root / 'review.json'
    save(review, {'question_total': 40, 'valid_questions': 40, 'invalid_questions': 0,
                  'uncertain_questions': 0, 'approved_question_ids': ids,
                  'source_summary_sha256': sha(source / 'summary.json')}, exclusive=True)
    confirmation = root / 'confirmation.json'
    save(confirmation, {'user_statement': 'Two people independently checked every source question.',
                        'two_distinct_humans': True, 'independent': True,
                        'review_summary_sha256': sha(review)}, exclusive=True)
    (root / 'backend/app').mkdir(parents=True)
    (root / 'backend/app/example.py').write_text('value = 1\n')
    (root / 'scripts').mkdir()
    for name in SCRIPT_NAMES:
        (root / 'scripts' / name).write_text('# Frozen test fixture, never executed.\n')
    return root, source, review, confirmation


def reseal(review, confirmation):
    value = read(confirmation)
    value['review_summary_sha256'] = sha(review)
    save(confirmation, value)


def test_complete_source_bound_human_approval_identifies_the_exact_forty_questions(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    checked = validate_approval(root, source, review, confirmation)
    assert len(checked['histories']) == 10
    assert sum(len(item['questions']) for item in checked['histories']) == 40


@pytest.mark.parametrize('field', ['two_distinct_humans', 'independent'])
def test_missing_independent_humans_stops_before_protocol_creation(tmp_path, field):
    root, source, review, confirmation = fixture(tmp_path)
    value = read(confirmation)
    value[field] = False
    save(confirmation, value)
    output = root / 'output/smoke'
    with pytest.raises(GuardError, match='two independent humans'):
        prepare(root, source, output, review, confirmation)
    assert not output.exists()


def test_later_review_edit_does_not_inherit_prior_human_confirmation(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    value = read(review)
    value['review_note'] = 'Later change'
    save(review, value)
    with pytest.raises(GuardError, match='confirmation'):
        validate_approval(root, source, review, confirmation)


def test_changed_question_record_cannot_reuse_original_review_hash(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    path = source / f'{EXPECTED_IDS[0]}.json'
    value = read(path)
    value['requests'][0]['response'][0]['prompt'] = 'A newly altered question?'
    save(path, value)
    with pytest.raises(GuardError, match='source run record changed'):
        validate_approval(root, source, review, confirmation)


def test_one_invalid_question_blocks_execution_even_with_human_acknowledgment(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    value = read(review)
    value.update(valid_questions=39, invalid_questions=1)
    save(review, value)
    reseal(review, confirmation)
    with pytest.raises(GuardError, match='forty source questions'):
        validate_approval(root, source, review, confirmation)


def test_duplicate_or_missing_approved_question_identity_is_not_counted_as_forty(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    value = read(review)
    value['approved_question_ids'][-1] = value['approved_question_ids'][0]
    save(review, value)
    reseal(review, confirmation)
    with pytest.raises(GuardError, match='every one'):
        validate_approval(root, source, review, confirmation)


def test_registration_guard_runs_before_database_imports(tmp_path, monkeypatch):
    root = tmp_path
    protocol = root / 'invalid.json'
    save(protocol, {'format': 'not-approved'}, exclusive=True)
    original = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith('app.'):
            raise AssertionError('Database/application imported before source approval')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    with pytest.raises(GuardError, match='Unexpected'):
        register(root, protocol)


def test_prepared_protocol_rejects_application_changes_and_cannot_overwrite(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    output = root / 'output/smoke'
    protocol_path = prepare(root, source, output, review, confirmation)
    protocol = read(protocol_path)
    check_protocol(root, protocol)
    with pytest.raises(FileExistsError):
        prepare(root, source, output, review, confirmation)
    (root / 'backend/app/example.py').write_text('value = 2\n')
    with pytest.raises(GuardError, match='Application source changed'):
        check_protocol(root, protocol)


def test_receipts_require_actual_direct_openai_max_not_just_the_requested_model():
    answer = {'model': 'gpt-6-astra', 'execution_metadata': {'response_source': 'openai',
              'reported_model': 'gpt-6-astra', 'requested_reasoning_effort': 'max'}}
    assert target_receipt_ok(answer)
    answer['execution_metadata']['response_source'] = 'openrouter'
    assert not target_receipt_ok(answer)
    evaluation = {'evaluator': 'fallback-rule', 'judge_execution': {'provider': 'openai', 'model': 'gpt-6-astra',
                  'reported_model': 'gpt-6-astra', 'requested_reasoning_effort': 'max'}}
    assert not judge_receipt_ok(evaluation)
    evaluation['evaluator'] = 'llm-judge-openai'
    assert judge_receipt_ok(evaluation)
    execution = {'role': 'target_memory_writing', 'status': 'completed', 'provider': 'openai',
                 'reported_model': 'gpt-6-astra', 'error_diagnostics': {'requested_reasoning_effort': 'max'}}
    assert writer_receipt_ok([execution])
    execution['status'] = 'failed'
    assert not writer_receipt_ok([execution])


def test_ambiguous_execute_is_journaled_first_and_never_replayed(tmp_path, monkeypatch):
    root, source, review, confirmation = fixture(tmp_path)
    output = root / 'output/smoke'
    protocol_path = prepare(root, source, output, review, confirmation)
    protocol = read(protocol_path)
    registrations = {'format': protocol['format'] + '-registrations', 'role': protocol['role'],
                     'protocol_sha256': sha(protocol_path), 'registrations': []}
    tests_by_run, history_by_run = {}, {}
    for index, item in enumerate(protocol['histories']):
        rid = f'EXEC{index}'
        copied = [{**q, 'run_id': rid, 'test_id': f'COPY-{q["test_id"]}'} for q in item['questions']]
        tests_by_run[rid] = copied
        history_by_run[rid] = item['history_id']
        registrations['registrations'].append({'history_id': item['history_id'],
            'source_run_id': item['source_run_id'], 'experiment_id': f'GROUP{index}',
            'run_id': rid, 'copied_test_ids': [q['test_id'] for q in copied]})
    save(output / 'registrations.json', registrations, exclusive=True)
    executed = []

    class Reply:
        status = 200

        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.value).encode()

    def transport(request, **kwargs):
        route = urlparse(request.full_url).path.removeprefix('/api/v1')
        parts = route.strip('/').split('/')
        if request.get_method() == 'POST':
            assert route.endswith('/execute')
            rid = parts[1]
            journal = read(output / f'{history_by_run[rid]}-execution.json')
            assert journal['operations'][-1]['state'] == 'dispatched'
            executed.append(rid)
            raise URLError('simulated ambiguous timeout')
        if parts[0] == 'audits' and len(parts) == 2:
            rid = parts[1]
            index = int(rid.removeprefix('EXEC'))
            return Reply({**protocol['histories'][index]['source_configuration'],
                          **protocol['condition'], 'run_id': rid, 'status': 'TESTS_GENERATED',
                          'target_memory_profile': protocol['histories'][index]['source_configuration']['target_memory_profile']})
        if route.endswith('/tests'):
            return Reply(tests_by_run[parts[1]])
        return Reply({})

    snapshot = {'protocol_sha256': sha(protocol_path), 'histories': [
        {'history_id': hid, 'registration_count': 1, 'groups': [{'runs': [{'responses': []}]}]} for hid in EXPECTED_IDS]}
    monkeypatch.setattr('scripts.run_ac2_ten_execution_smoke_20261101.urlopen', transport)
    monkeypatch.setattr('scripts.run_ac2_ten_execution_smoke_20261101.subprocess.run',
                        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(snapshot)))
    summary = run(root, output, 'http://127.0.0.1:8000/api/v1')
    assert len(executed) == len(set(executed)) == 10
    assert all(row['status'] == 'stopped_no_replay' for row in summary['histories'])
    assert summary['known_saved_answers'] == 0 and summary['missing_saved_answers'] == 40
    assert summary['assessment_basis'].startswith('automatic only')
    with pytest.raises(FileExistsError):
        run(root, output, 'http://127.0.0.1:8000/api/v1')
    assert len(executed) == 10


def revise_active_snapshot(root, source, review, confirmation, *, new_identity):
    """Keep original POST untouched, append actual-style GET snapshots, reseal fixtures."""
    path = source / f'{EXPECTED_IDS[0]}.json'
    record = read(path)
    original = json.loads(json.dumps(record['requests'][0]['response']))
    current = json.loads(json.dumps(original))
    selected = next(q for q in current if q['dimension'] == 'freshness')
    old_id = selected['test_id']
    selected['prompt'] = 'Describe the recorded update history and what remains unresolved?'
    selected['expected_behavior'] = 'Explain the historical change and request clarification for the incompatible current records.'
    if new_identity:
        selected['test_id'] = old_id + '-revised'
    record['requests'].extend([
        {'method': 'GET', 'path': '/audits/R0/tests', 'status': 'returned', 'response': original},
        {'method': 'GET', 'path': '/audits/R0/tests', 'status': 'returned', 'response': current},
    ])
    save(path, record)
    summary = read(source / 'summary.json')
    summary['runs'][0]['record_sha256'] = sha(path)
    save(source / 'summary.json', summary)
    approval = read(review)
    approval['source_summary_sha256'] = sha(source / 'summary.json')
    if new_identity:
        approval['approved_question_ids'] = [selected['test_id'] if qid == old_id else qid
                                             for qid in approval['approved_question_ids']]
    save(review, approval)
    reseal(review, confirmation)
    return original, current, old_id, selected['test_id']


@pytest.mark.parametrize('new_identity', [False, True])
def test_latest_real_get_snapshot_binds_active_questions_instead_of_stale_post(tmp_path, new_identity):
    root, source, review, confirmation = fixture(tmp_path)
    original, current, _, _ = revise_active_snapshot(root, source, review, confirmation, new_identity=new_identity)
    checked = validate_approval(root, source, review, confirmation)
    first = checked['histories'][0]
    assert first['questions'] == current
    assert first['questions'] != original
    assert first['question_snapshot_method'] == 'GET'
    assert first['question_snapshot_path'] == '/audits/R0/tests'
    # The original API response is retained byte-for-content, not fabricated as revised.
    record = read(source / f'{EXPECTED_IDS[0]}.json')
    assert record['requests'][0]['response'] == original
    output = root / 'output/smoke'
    prepared = read(prepare(root, source, output, review, confirmation))
    assert prepared['histories'][0]['questions'] == current


def test_approval_of_stale_post_ids_cannot_authorize_new_get_question_identities(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    _, _, old_id, new_id = revise_active_snapshot(root, source, review, confirmation, new_identity=True)
    approval = read(review)
    approval['approved_question_ids'] = [old_id if qid == new_id else qid for qid in approval['approved_question_ids']]
    save(review, approval)
    reseal(review, confirmation)
    with pytest.raises(GuardError, match='exact forty saved question IDs'):
        validate_approval(root, source, review, confirmation)


def normalized_fork_fixture(approved):
    values = {'provider': 'openai', 'model': 'gpt-6-astra', 'temperature': 0, 'random_seed': 42,
        'test_budget': 4, 'pipeline_provider': 'openai', 'pipeline_model': 'gpt-6-astra',
        'semantic_review_provider': 'openai', 'semantic_review_model': 'gpt-6-astra',
        'evaluator_provider': 'openai', 'evaluator_model': 'gpt-6-astra', 'retrieval_mode': 'fixed',
        'retrieval_provider': None, 'retrieval_model': None, 'memory_strategy': 'relationship_packet',
        'memory_maintenance_policy': 'update_aware_consolidation', 'target_memory_capacity': 50,
        'target_memory_writer': 'llm_structured', 'target_memory_writer_version': 'fixture-writer-v1',
        'target_system_adapter': 'controlled-memory', 'target_system_adapter_version': 'controlled-memory-v1'}
    profile = dict(approved)
    if profile['output_token_limit'] is None:
        profile['output_token_limit'] = 2048  # Actual build_audit behavior being repaired.
    metadata = {'target_memory_profile': profile, 'configuration_fingerprint': 'normalized-old',
                'retrieval_agent_version': None, 'coverage_policy': 'strict_full_v1',
                'study_role': 'ac2_ten_execution_smoke_v2', 'diagnostic_source_run_id': 'original'}
    return SimpleNamespace(**values, reproducibility_metadata=metadata), values


@pytest.mark.parametrize('limit', [None, 777])
def test_new_fork_preserves_exact_source_nullable_profile_and_recomputes_actual_fingerprint(limit):
    approved = {'label': 'Source', 'identity_analysis': 'off', 'output_token_limit': limit}
    original_approved = dict(approved)
    target, fields = normalized_fork_fixture(approved)
    old_metadata = json.loads(json.dumps(target.reproducibility_metadata))
    hashed = []

    def fingerprint(configuration):
        hashed.append(configuration)
        return hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    restore_approved_profile(target, approved, fingerprint)
    final = target.reproducibility_metadata
    assert final['target_memory_profile'] == original_approved
    assert final['target_memory_profile']['output_token_limit'] is limit
    expected_configuration = {**fields, 'retrieval_agent_version': None, 'target_memory_profile': approved}
    assert hashed == [expected_configuration]
    assert final['configuration_fingerprint'] == fingerprint(expected_configuration)
    assert final['configuration_fingerprint'] != old_metadata['configuration_fingerprint']
    assert final['study_role'] == 'ac2_ten_execution_smoke_v2'
    preservation = final['execution_smoke_profile_preservation']
    assert preservation['created_profile_before_restore'] == old_metadata['target_memory_profile']
    assert preservation['output_token_limit_restored'] is (limit is None)
    assert approved == original_approved  # Never mutate the source profile or its snapshot.
    final['target_memory_profile']['label'] = 'Changed only on new fork'
    assert approved == original_approved


def test_profile_restoration_refuses_other_unplanned_changes_before_touching_metadata():
    approved = {'label': 'Source', 'identity_analysis': 'off', 'output_token_limit': None}
    target, _ = normalized_fork_fixture(approved)
    target.reproducibility_metadata['target_memory_profile']['identity_analysis'] = 'agent'
    before = json.loads(json.dumps(target.reproducibility_metadata))
    with pytest.raises(GuardError, match='beyond the known'):
        restore_approved_profile(target, approved, lambda _: pytest.fail('Fingerprint must not run'))
    assert target.reproducibility_metadata == before


def test_v2_protocol_cannot_authorize_v1_seal_or_registration(tmp_path):
    root, source, review, confirmation = fixture(tmp_path)
    protocol_path = prepare(root, source, root / 'output/smoke-v2', review, confirmation)
    protocol = read(protocol_path)
    assert protocol['format'] == 'ac2-ten-execution-smoke-v2'
    assert protocol['role'] == 'ac2_ten_execution_smoke_v2'
    stale = {**protocol, 'format': 'ac2-ten-execution-smoke-v1', 'role': 'ac2_ten_execution_smoke_v1'}
    with pytest.raises(GuardError, match='Unexpected execution smoke protocol'):
        check_protocol(root, stale)
