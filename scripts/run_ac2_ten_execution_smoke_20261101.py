"""Execute registered, human-approved AC2 questions without regenerating a suite.

Run only after --prepare and backend --register emitted registrations.json.
One durable execution seal and per-history journals forbid silent redispatch.
All answer outcomes remain AUTOMATIC assessments, separate from AC2 validity.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ac2_ten_execution_common import (
    EXPECTED_IDS,
    FORMAT,
    OUTPUT_RELATIVE,
    GuardError,
    check_protocol,
    now,
    question_signature,
    read,
    save,
    sha,
)


def target_receipt_ok(answer):
    evidence = answer.get('execution_metadata') or {}
    return (answer.get('model') == 'gpt-6-astra' and evidence.get('response_source') == 'openai'
            and evidence.get('reported_model') == 'gpt-6-astra'
            and evidence.get('requested_reasoning_effort') == 'max')


def judge_receipt_ok(evaluation):
    evidence = evaluation.get('judge_execution') or {}
    return (evidence.get('provider') == 'openai' and evidence.get('model') == 'gpt-6-astra'
            and evidence.get('reported_model') == 'gpt-6-astra'
            and evidence.get('requested_reasoning_effort') == 'max'
            and not evaluation.get('evaluator', '').startswith('fallback-'))


def writer_receipt_ok(executions):
    return any(row.get('role') == 'target_memory_writing' and row.get('status') == 'completed'
               and row.get('provider') == 'openai' and row.get('reported_model') == 'gpt-6-astra'
               and (row.get('error_diagnostics') or {}).get('requested_reasoning_effort') == 'max'
               for row in executions)


def validate_registrations(protocol, protocol_path, registrations):
    if (registrations.get('format') != FORMAT + '-registrations'
            or registrations.get('protocol_sha256') != sha(protocol_path)
            or registrations.get('role') != protocol['role']):
        raise GuardError('Registrations do not match the frozen protocol.')
    rows = registrations.get('registrations', [])
    if len(rows) != 10 or tuple(row.get('history_id') for row in rows) != EXPECTED_IDS:
        raise GuardError('Exactly one registered condition per original history is required.')
    if len({row.get('run_id') for row in rows}) != 10:
        raise GuardError('Registered run identities must be distinct.')
    for row, source in zip(rows, protocol['histories'], strict=True):
        if (row.get('source_run_id') != source['source_run_id']
                or len(row.get('copied_test_ids', [])) != 4
                or len(set(row['copied_test_ids'])) != 4):
            raise GuardError('A registration does not preserve its four approved source questions.')
    return rows


def run(root, output_folder, api_url):
    root, output_folder = Path(root), Path(output_folder)
    parsed = urlparse(api_url)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1'} or parsed.username or parsed.password:
        raise GuardError('Use only the local Auditor API; credentials never belong in this URL.')
    protocol_path = output_folder / 'protocol.json'
    registrations_path = output_folder / 'registrations.json'
    protocol, registrations = read(protocol_path), read(registrations_path)
    check_protocol(root, protocol)
    rows = validate_registrations(protocol, protocol_path, registrations)
    seal = {'format': FORMAT + '-execution-seal', 'created_utc': now(),
            'protocol_sha256': sha(protocol_path), 'registrations_sha256': sha(registrations_path),
            'no_redispatch': 'An existing seal or journal requires manual reconciliation, never rerunning this script.'}
    save(output_folder / 'execution-seal.json', seal, exclusive=True)
    sources = {item['history_id']: item for item in protocol['histories']}
    print_lock = threading.Lock()

    def check():
        if sha(protocol_path) != seal['protocol_sha256'] or sha(registrations_path) != seal['registrations_sha256']:
            raise GuardError('Frozen protocol/registrations changed during execution.')
        check_protocol(root, protocol)

    def one(registration):
        hid, rid, group = registration['history_id'], registration['run_id'], registration['experiment_id']
        path = output_folder / f'{hid}-execution.json'
        state = {'history_id': hid, 'run_id': rid, 'experiment_id': group,
                 'source_run_id': registration['source_run_id'], 'status': 'started',
                 'assessment_basis': 'automatic; not human answer accuracy or question validity',
                 'operations': [], 'started_utc': now()}
        save(path, state, exclusive=True)

        def call(method, route, body=None, *, binary_name=None):
            check()
            operation = {'method': method, 'path': route, 'state': 'dispatched', 'dispatched_utc': now()}
            state['operations'].append(operation)
            save(path, state)  # Durable BEFORE every read or paid write dispatch.
            try:
                request = Request(api_url.rstrip('/') + route, method=method,
                                  data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type': 'application/json'})
                with urlopen(request, timeout=1800) as response:
                    blob = response.read()
                    if binary_name:
                        destination = output_folder / f'{hid}-{binary_name}'
                        with destination.open('xb') as artifact:
                            artifact.write(blob)
                        result = {'artifact': destination.name, 'sha256': sha(destination), 'bytes': len(blob)}
                    else:
                        result = json.loads(blob)
                    operation.update(state='returned', http_status=response.status, response=result)
            except HTTPError as exc:
                operation.update(state='http_error', http_status=exc.code,
                                 error=exc.read().decode(errors='replace')[:1500])
                save(path, state)
                raise
            except Exception as exc:
                operation.update(state='ambiguous', error_type=type(exc).__name__)
                save(path, state)
                raise
            finally:
                operation['finished_utc'] = now()
                save(path, state)
            return result

        try:
            audit = call('GET', f'/audits/{rid}')
            expected = protocol['condition']
            for key in ('provider', 'model', 'target_memory_writer', 'memory_strategy',
                        'evaluator_provider', 'evaluator_model', 'pipeline_provider', 'pipeline_model',
                        'target_configuration', 'retrieval_mode'):
                if audit.get(key) != expected[key]:
                    raise GuardError('Registered target configuration no longer matches the protocol.')
            if audit.get('run_id') != rid:
                raise GuardError('The returned audit has a different run identity.')
            for key in ('temperature', 'random_seed', 'test_budget', 'prompt_template_version',
                        'target_memory_capacity', 'memory_maintenance_policy', 'target_system_adapter',
                        'retrieval_provider', 'retrieval_model'):
                if audit.get(key) != sources[hid]['source_configuration'].get(key):
                    raise GuardError('An untargeted source configuration field changed.')
            profile = audit.get('target_memory_profile') or audit.get('reproducibility', {}).get('target_memory_profile')
            if profile != sources[hid]['source_configuration']['target_memory_profile']:
                raise GuardError('The fixed source profile changed.')
            if audit.get('status') != 'TESTS_GENERATED':
                raise GuardError('The registered run has already started; no execution replay permitted.')
            tests = call('GET', f'/audits/{rid}/tests')
            if ({q['test_id'] for q in tests} != set(registration['copied_test_ids']) or len(tests) != 4
                    or sorted(question_signature(q) for q in tests)
                    != sorted(question_signature(q) for q in sources[hid]['questions'])):
                raise GuardError('Frozen source question content or copied identities changed.')
            answers = call('POST', f'/audits/{rid}/execute', {})
            state['answers_returned'] = len(answers)
            state['target_max_receipts_verified'] = sum(target_receipt_ok(answer) for answer in answers)
            if (len(answers) != 4 or {a['test_id'] for a in answers} != set(registration['copied_test_ids'])
                    or not all(target_receipt_ok(answer) for answer in answers)):
                raise GuardError('Target answers or direct OpenAI Astra max receipts are incomplete.')
            evaluations = call('POST', f'/audits/{rid}/evaluate', {})
            state['evaluations_returned'] = len(evaluations)
            state['judge_max_receipts_verified'] = sum(judge_receipt_ok(evaluation) for evaluation in evaluations)
            if len(evaluations) != 4 or {e['test_id'] for e in evaluations} != set(registration['copied_test_ids']):
                raise GuardError('Automatic evaluations do not cover the frozen four questions.')
            state['automatic_passed'] = sum(e.get('passed') is True for e in evaluations)
            state['automatic_failed'] = sum(e.get('passed') is False for e in evaluations)
            state['automatic_uncertain'] = sum(e.get('passed') is None for e in evaluations)
            executions = call('GET', f'/audits/{rid}/agent-executions')
            state['writer_max_receipt_verified'] = writer_receipt_ok(executions)
            state['status'] = ('completed_automatic' if state['writer_max_receipt_verified']
                               and state['judge_max_receipts_verified'] == 4 else 'completed_automatic_receipts_incomplete')
        except Exception as exc:  # noqa: BLE001 - persist every unexpected source failure before stopping.
            state.update(status='stopped_no_replay', error_type=type(exc).__name__, error=str(exc)[:350])
        finally:
            # Read-only collection attempts retain partial answers/failures even
            # after execution or judging failed. They never dispatch execute again.
            for route, artifact in [
                (f'/audits/{rid}', None), (f'/audits/{rid}/target-memory-trace', None),
                (f'/audits/{rid}/agent-executions', None), (f'/audits/{rid}/results', None),
                (f'/experiments/{group}/results', None),
                (f'/experiments/{group}/reproducibility-bundle.json', None),
                (f'/experiments/{group}/export.csv', 'experiment.csv'),
                (f'/experiments/{group}/artifact.zip', 'artifact.zip'),
            ]:
                try:
                    call('GET', route, binary_name=artifact)
                except Exception as exc:  # noqa: BLE001 - collection failures must not mask the original failure.
                    state.setdefault('inspection_failures', []).append({'path': route, 'error_type': type(exc).__name__})
            state['finished_utc'] = now()
            save(path, state)
        with print_lock:
            print(hid, state['status'], flush=True)
        return {key: state.get(key) for key in ('history_id', 'run_id', 'experiment_id', 'status',
                'answers_returned', 'evaluations_returned', 'automatic_passed', 'automatic_failed',
                'automatic_uncertain', 'target_max_receipts_verified', 'judge_max_receipts_verified',
                'writer_max_receipt_verified')}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(one, rows))
    snapshot_status = 'unavailable'
    known_saved = 0
    unknown_histories = list(EXPECTED_IDS)
    try:
        check()
        # The HTTP report/export path exposes completed runs only. This guarded
        # READ-ONLY command also preserves responses after partial failures.
        command = ['docker', 'compose', 'exec', '-T', 'backend', 'python',
                   '/scripts/register_ac2_ten_execution_smoke_20261101.py', '--inspect',
                   '--protocol', '/output/' + str(protocol_path.relative_to(root / 'output'))]
        receipt = {'state': 'dispatched', 'created_utc': now(), 'kind': 'read_only_db_inspection'}
        save(output_folder / 'db-snapshot-operation.json', receipt, exclusive=True)
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60, check=False)
        if completed.returncode != 0:
            raise GuardError('Read-only snapshot command did not complete successfully.')
        snapshot = json.loads(completed.stdout)
        if snapshot.get('protocol_sha256') != sha(protocol_path):
            raise GuardError('Read-only snapshot belongs to a different protocol.')
        save(output_folder / 'read-only-db-snapshot.json', snapshot, exclusive=True)
        unknown_histories = []
        for item in snapshot['histories']:
            if item['registration_count'] != 1 or len(item['groups'][0]['runs']) != 1:
                unknown_histories.append(item['history_id'])
                continue
            saved = item['groups'][0]['runs'][0]['responses']
            known_saved += len({answer['test_id'] for answer in saved})
        snapshot_status = 'returned'
        receipt.update(state='returned', completed_utc=now())
        save(output_folder / 'db-snapshot-operation.json', receipt)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, subprocess.SubprocessError) as exc:
        operation = output_folder / 'db-snapshot-operation.json'
        if operation.exists():
            receipt = read(operation)
            receipt.update(state='unavailable', error_type=type(exc).__name__)
            save(operation, receipt)
    summary = {'format': FORMAT + '-summary', 'created_utc': now(), 'histories': outcomes,
               'planned_answers': 40, 'returned_answers': sum(row.get('answers_returned') or 0 for row in outcomes),
               'not_returned_answer_slots': 40 - sum(row.get('answers_returned') or 0 for row in outcomes),
               'read_only_db_snapshot_status': snapshot_status, 'known_saved_answers': known_saved,
               'histories_with_unknown_saved_count': unknown_histories,
               'missing_saved_answers': 40 - known_saved if not unknown_histories else None,
               'assessment_basis': 'automatic only; not AC2 validity or independent AC3 validation',
               'reconciliation_notice': 'Ambiguous execute/evaluate requests may still be running. Inspect status/receipts without replay; snapshot counts are observations, not proof a remote request stopped.',
               'protocol_sha256': sha(protocol_path), 'registrations_sha256': sha(registrations_path)}
    save(output_folder / 'collection-summary.json', summary, exclusive=True)
    return summary


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-folder', type=Path, default=root / OUTPUT_RELATIVE)
    parser.add_argument('--api-url', default='http://127.0.0.1:8000/api/v1')
    args = parser.parse_args()
    print(json.dumps(run(root, args.output_folder, args.api_url), ensure_ascii=False))


if __name__ == '__main__':
    main()
