"""Pure source/approval guards for the optional post-review execution smoke.

Importing this module never accesses a database or calls a provider.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_IDS = tuple(f'prospective-{i:02d}' for i in range(1, 30, 3))
SOURCE_RELATIVE = 'output/proposal-delivery/ac2-original-ten-effective-cohort-20261101-v1'
OUTPUT_RELATIVE = 'output/proposal-delivery/ac2-original-ten-execution-smoke-20261101-v2'
ROLE = 'ac2_ten_execution_smoke_v2'
FORMAT = 'ac2-ten-execution-smoke-v2'
SCRIPT_NAMES = ('ac2_ten_execution_common.py', 'register_ac2_ten_execution_smoke_20261101.py',
                'run_ac2_ten_execution_smoke_20261101.py')
DIMENSIONS = {'accuracy', 'freshness', 'conflict_resolution', 'appropriate_use'}


class GuardError(ValueError):
    """Stop before mutation/dispatch when the approval or frozen input differs."""


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value, *, exclusive=False):
    path = Path(path)
    body = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(body)
    else:
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(body, encoding='utf-8')
        temporary.replace(path)


def relative(root, path):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError as exc:
        raise GuardError('Approval and source files must be inside the project.') from exc


def question_signature(question):
    return (question['dimension'], question['test_type'], question['prompt'],
            question['expected_behavior'], tuple(sorted(question['supporting_memory_ids'])),
            question['generator_version'])


def application_hashes(root):
    root = Path(root)
    result = {str(path.relative_to(root)): sha(path) for path in sorted((root / 'backend/app').rglob('*.py'))}
    if not result:
        raise GuardError('Cannot locate the application source to freeze.')
    return result


def validate_approval(root, source_folder, review_summary, human_confirmation):
    """Bind explicit human approval to the exact forty saved questions.

    The summary is an approval adapter, not newly invented review judgments.
    It must declare question_total/valid_questions=40, invalid/uncertain=0,
    approved_question_ids and the source summary's SHA. The separate user
    confirmation must bind this very adapter by review_summary_sha256.
    """
    root, source_folder = Path(root), Path(source_folder)
    review_summary, human_confirmation = Path(review_summary), Path(human_confirmation)
    relative(root, source_folder)
    relative(root, review_summary)
    relative(root, human_confirmation)
    review, confirmation = read(review_summary), read(human_confirmation)
    if (confirmation.get('two_distinct_humans') is not True
            or confirmation.get('independent') is not True
            or not isinstance(confirmation.get('user_statement'), str)
            or not confirmation['user_statement'].strip()
            or confirmation.get('review_summary_sha256') != sha(review_summary)):
        raise GuardError('Explicit source-bound confirmation by two independent humans is required.')
    required = {'question_total': 40, 'valid_questions': 40, 'invalid_questions': 0, 'uncertain_questions': 0}
    if any(type(review.get(key)) is not int or review[key] != value for key, value in required.items()):
        raise GuardError('All forty source questions must be explicitly reviewed valid before execution.')
    source_summary = source_folder / 'summary.json'
    summary = read(source_summary)
    if (review.get('source_summary_sha256') != sha(source_summary)
            or summary.get('histories') != 10 or summary.get('generated_questions') != 40):
        raise GuardError('The reviewed source summary is not the complete forty-question ten-history result.')
    rows = summary.get('runs', [])
    if len(rows) != 10 or tuple(row.get('history_id') for row in rows) != EXPECTED_IDS:
        raise GuardError('The exact original ten histories must be preserved in source order.')
    histories, all_ids = [], []
    for item in rows:
        hid = item['history_id']
        record_path = source_folder / f'{hid}.json'
        if item.get('record_sha256') != sha(record_path):
            raise GuardError('A source run record changed after the reviewed summary.')
        record = read(record_path)
        generated = [row for row in record.get('requests', [])
                     if row.get('path', '').endswith('/generate-tests') and row.get('status') == 'returned']
        if len(generated) != 1 or record.get('status') != 'completed':
            raise GuardError('Each source needs exactly one successful, saved generation response.')
        run_id = record.get('run_id')
        snapshots = [row for row in record['requests']
                     if row.get('method') == 'GET' and row.get('path') == f'/audits/{run_id}/tests'
                     and row.get('status') == 'returned']
        # A real product regeneration can replace wording/reference/identity.
        # The last saved GET snapshot is authoritative for the active cohort;
        # preserve the original POST generation response as historical evidence.
        question_response = snapshots[-1] if snapshots else generated[0]
        questions = question_response['response']
        if (not isinstance(questions, list) or len(questions) != 4
                or {q.get('dimension') for q in questions} != DIMENSIONS):
            raise GuardError('Each history must retain its four source-backed dimensions.')
        run_ids = {q.get('run_id') for q in questions}
        if len(run_ids) != 1 or None in run_ids or next(iter(run_ids)) != record.get('run_id'):
            raise GuardError('Question identities do not belong to their recorded source run.')
        run_id = record['run_id']
        audits = [r['response'] for r in record['requests']
                  if r.get('method') == 'GET' and r.get('path') == f'/audits/{run_id}'
                  and r.get('status') == 'returned']
        if len(audits) != 1:
            raise GuardError('A saved source audit configuration is required.')
        audit = audits[0]
        if (audit.get('target_configuration') != 'weak' or audit.get('retrieval_mode') != 'fixed'
                or audit.get('test_budget') != 4 or audit.get('pipeline_provider') != 'openai'
                or audit.get('pipeline_model') != 'gpt-6-astra'):
            raise GuardError('Source audit settings differ from the frozen AC2 generation condition.')
        for question in questions:
            question_signature(question)  # All signature fields must be present.
        ids = [q['test_id'] for q in questions]
        if len(set(ids)) != 4:
            raise GuardError('Question identities must be distinct.')
        all_ids.extend(ids)
        histories.append({'history_id': hid, 'source_run_id': run_id,
                          'conversation_id': audit['conversation_id'], 'source_test_ids': ids,
                          'questions': questions, 'source_configuration': audit,
                          'question_snapshot_method': question_response['method'],
                          'question_snapshot_path': question_response['path'],
                          'source_record': relative(root, record_path), 'source_record_sha256': sha(record_path)})
    approved = review.get('approved_question_ids')
    if (not isinstance(approved, list) or len(approved) != 40 or len(set(approved)) != 40
            or len(set(all_ids)) != 40 or set(approved) != set(all_ids)):
        raise GuardError('Human review must identify every one of the exact forty saved question IDs.')
    return {'histories': histories, 'source_summary': relative(root, source_summary),
            'source_summary_sha256': sha(source_summary),
            'review_summary': relative(root, review_summary), 'review_summary_sha256': sha(review_summary),
            'human_confirmation': relative(root, human_confirmation),
            'human_confirmation_sha256': sha(human_confirmation)}


def check_protocol(root, protocol):
    root = Path(root)
    if protocol.get('format') != FORMAT or protocol.get('role') != ROLE:
        raise GuardError('Unexpected execution smoke protocol.')
    for key in ('source_summary', 'review_summary', 'human_confirmation'):
        if sha(root / protocol[key]) != protocol[key + '_sha256']:
            raise GuardError('The frozen source/review/confirmation changed.')
    if application_hashes(root) != protocol['application_sha256']:
        raise GuardError('Application source changed after the execution smoke freeze.')
    for relative_path, expected in protocol['scripts_sha256'].items():
        if sha(root / relative_path) != expected:
            raise GuardError('An execution smoke script changed after protocol freeze.')
    approval = validate_approval(root, root / protocol['source_folder'],
                                 root / protocol['review_summary'], root / protocol['human_confirmation'])
    if approval['histories'] != protocol['histories']:
        raise GuardError('The saved source questions/configurations changed.')
    return approval
