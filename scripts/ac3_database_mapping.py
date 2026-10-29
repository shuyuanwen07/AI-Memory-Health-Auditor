"""Read-only binding of a frozen AC3 suite to actual application memories.

This module does not create audits, import tests, call models, or reserve money.
The caller must separately supply an already authenticated database session and
explicit history-to-conversation mapping. A future mutating importer must repeat
all checks under a database lock and enforce real per-request budget accounting.
"""
import json
from pathlib import Path

from sqlalchemy import select

from app.models import AuditRunModel, ConversationModel, MemoryModel, MemoryRelationshipModel, MessageModel, TestCaseModel, TargetResponseModel
from app.schemas.domain import Dimension, RelationshipType
from scripts.ac3_fixed_suite_adapter import compile_mock, sha


def compile_database_stage(db, frozen_path: Path, frozen_sha256: str, reservation: str, history_conversations: dict):
    """Verify actual saved source and confirmed memories, then prepare a dry-run plan."""
    if db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean read-only session; pending database changes are not permitted.')
    # compile_mock validates review hashes, prospective attestations, suite,
    # configuration and the simulated budget before any database access.
    initial = compile_mock(frozen_path, frozen_sha256, reservation)
    raw = frozen_path.read_bytes()
    if sha(raw) != frozen_sha256:
        raise ValueError('Frozen suite changed during preparation.')
    suite = json.loads(raw)['suite']
    cases = suite['cases']
    # The current source design deliberately packs two simultaneous facts in
    # M4 and a general preference plus scoped exception in M5. The older
    # one-verbatim-memory-per-message mapping cannot encode those relationships.
    # Do not stage it until the separately reviewed multi-fact importer is wired.
    fact_plan = initial.get('reviewed_fact_plan')
    if fact_plan is None and any(any(message['message_id'].endswith(('-M4', '-M5')) for message in case['source_messages']) for case in cases):
        raise ValueError('Compound sources require the reviewed multi-fact relationship importer; the legacy one-memory mapping is unsafe.')
    history_ids = {case['history_id'] for case in cases}
    if not isinstance(history_conversations, dict) or set(history_conversations) != history_ids:
        raise ValueError('An explicit conversation mapping is required for each frozen history.')
    ids = list(history_conversations.values())
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Conversation IDs must be distinct, non-empty strings.')
    snapshot = {'histories': []}
    fact_snapshot = {'histories': {}}
    relation_count = 0
    with db.no_autoflush:
        for case in cases:
            conversation_id = history_conversations[case['history_id']]
            conversation = db.get(ConversationModel, conversation_id, populate_existing=True)
            if conversation is None or conversation.authorised is not True or conversation.source_origin != 'synthetic':
                raise ValueError('Every mapped conversation must be authorised and explicitly synthetic.')
            messages = list(db.scalars(select(MessageModel).where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.sequence).execution_options(populate_existing=True)))
            expected_messages = case['source_messages']
            if len(messages) != len(expected_messages):
                raise ValueError('Saved conversation must match the complete frozen history.')
            for index, (actual, expected) in enumerate(zip(messages, expected_messages)):
                if (actual.source_message_id != expected['message_id'] or actual.role != expected['role']
                        or actual.content != expected['text'] or expected['order'] != index + 1
                        or actual.sequence != index):
                    raise ValueError('Saved source message identity, role, order, or text differs from the frozen history.')
            memories = list(db.scalars(select(MemoryModel).where(MemoryModel.conversation_id == conversation_id)
                .order_by(MemoryModel.id).execution_options(populate_existing=True)))
            local_memory_ids = {m.id for m in memories}
            source_ids = {message['message_id'] for message in expected_messages}
            relationships = list(db.scalars(select(MemoryRelationshipModel)
                .where(MemoryRelationshipModel.memory_id.in_(local_memory_ids))
                .order_by(MemoryRelationshipModel.id).execution_options(populate_existing=True)))
            for relation in relationships:
                evidence = relation.evidence_message_ids
                if (relation.target_memory_id not in local_memory_ids or relation.target_memory_id == relation.memory_id
                        or relation.relationship_type not in {item.value for item in RelationshipType}
                        or not isinstance(evidence, list) or not evidence
                        or any(not isinstance(item, str) for item in evidence)
                        or len(set(evidence)) != len(evidence) or not set(evidence).issubset(source_ids)):
                    raise ValueError('Memory relationships must use local distinct memories, supported types and local source evidence.')
            relation_count += len(relationships)
            snapshot['histories'].append({'history_id': case['history_id'], 'conversation_id': conversation_id,
                'memories': [{'memory_id': m.id, 'conversation_id': m.conversation_id, 'status': m.status,
                              'source_message_ids': m.source_message_ids, 'canonical_value': m.canonical_value}
                             for m in memories]})
            fact_snapshot['histories'][case['history_id']] = {
                'memories': [{'memory_id': m.id, 'status': m.status, 'source_message_ids': m.source_message_ids,
                              'canonical_value': m.canonical_value} for m in memories],
                'relationships': [{'memory_id': r.memory_id, 'target_memory_id': r.target_memory_id,
                    'relationship_type': r.relationship_type, 'evidence_message_ids': r.evidence_message_ids}
                    for r in relationships]}
        if fact_plan is None:
            result = compile_mock(frozen_path, frozen_sha256, reservation, snapshot)
        else:
            from scripts.ac3_reviewed_fact_map import validate_fact_plan
            validate_fact_plan(suite, fact_plan, initial['fact_plan_reviews'], fact_snapshot)
            result = compile_mock(frozen_path, frozen_sha256, reservation)
            for item in result['items']:
                facts = fact_plan['histories'][item['history_id']]['facts']
                item['supporting_memory_ids'] = [fact['memory_id'] for fact in facts
                    if fact['source_message_id'] in item['supporting_source_message_ids']]
    if initial['frozen_sha256'] != result['frozen_sha256'] or sha(frozen_path.read_bytes()) != frozen_sha256:
        raise ValueError('Frozen suite changed while binding database records.')
    result.update({'format': 'ac3-confirmed-memory-database-check-v1', 'memory_records_verified_in_app': True,
                   'structurally_checked_relationships': relation_count, 'relationship_completeness_verified': False,
                   'import_supported': False, 'execution_supported': False,
                   'limitation': 'Read-only database verification only. Relationship semantics/completeness, concurrent changes, '
                                 'actual import, locked revalidation, live budget enforcement and execution are not validated.'})
    return result


def exercise_import_in_memory(db, frozen_path: Path, frozen_sha256: str, reservation: str,
                              history_conversations: dict, history_runs: dict):
    """Exercise a prospective import solely inside a rolled-back in-memory SQLite savepoint.

    There is deliberately no production-capable import or run-state transition here.
    This verifies the prospective mappings against the application's real test schema
    without permitting a target call or retaining any test rows.
    """
    bind = db.get_bind()
    if bind.url.get_backend_name() != 'sqlite' or bind.url.database not in (None, ':memory:'):
        raise ValueError('Import rehearsal is restricted to an in-memory SQLite test database.')
    if db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean test session.')
    plan = compile_database_stage(db, frozen_path, frozen_sha256, reservation, history_conversations)
    histories = set(history_conversations)
    if not isinstance(history_runs, dict) or set(history_runs) != histories:
        raise ValueError('A separate test audit is required for every frozen history.')
    run_ids = list(history_runs.values())
    if any(not isinstance(value, str) or not value.strip() for value in run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError('Test audit IDs must be distinct and non-empty.')
    eligible = [row for row in plan['items'] if row['grounding_review'] == 'valid']
    if len(eligible) != plan['eligible_question_count'] or any(row['history_id'] not in histories for row in eligible):
        raise ValueError('Reviewed question identities do not match the frozen suite.')
    config = plan['model_configuration']
    dimensions = {item.value for item in Dimension}
    with db.no_autoflush:
        for history, run_id in history_runs.items():
            run = db.get(AuditRunModel, run_id, populate_existing=True)
            if not run or run.status != 'CREATED' or run.conversation_id != history_conversations[history]:
                raise ValueError('Each audit must be CREATED for its mapped conversation.')
            if any(getattr(run, key) != config[value] for key, value in (
                ('provider', 'target_provider'), ('model', 'target_model'),
                ('evaluator_provider', 'evaluator_provider'), ('evaluator_model', 'evaluator_model'),
                ('pipeline_provider', 'pipeline_provider'), ('pipeline_model', 'pipeline_model'),
                ('memory_strategy', 'target_strategy'))):
                raise ValueError('Audit provider, model or strategy differs from the frozen configuration.')
            tests = [row for row in eligible if row['history_id'] == history]
            if not tests or run.test_budget != len(tests):
                raise ValueError('Audit test budget must match its reviewed eligible questions.')
            if db.scalar(select(TestCaseModel.id).where(TestCaseModel.run_id == run_id).limit(1)) or db.scalar(select(TargetResponseModel.id).where(TargetResponseModel.run_id == run_id).limit(1)):
                raise ValueError('Audit must have no existing tests or target responses.')
            if any(row['dimension'] not in dimensions or not row['supporting_memory_ids'] for row in tests):
                raise ValueError('A test dimension or confirmed source-memory mapping is invalid.')
    # Roll back the savepoint even after success: no live tests or status are retained.
    with db.begin_nested() as savepoint:
        for row in eligible:
            test_id = 'AC3' + sha((f"{frozen_sha256}|{history_runs[row['history_id']]}|{row['test_id']}").encode())[:32].upper()
            db.add(TestCaseModel(id=test_id, run_id=history_runs[row['history_id']], dimension=row['dimension'],
                prompt=row['question'], expected_behavior=row['expected_behavior'],
                supporting_memory_ids=row['supporting_memory_ids'], generator_version='ac3-import-rehearsal-v1',
                test_type='contextual', quality_status='pending', grounding_status='pending',
                validation_notes='Test-only rehearsal; no independent adjudication or execution is asserted.',
                target_memory_context=[]))
        db.flush()
        if any(db.get(AuditRunModel, run_id).status != 'CREATED' for run_id in run_ids):
            raise ValueError('Import rehearsal must not transition audit state.')
        savepoint.rollback()
    return {'format': 'ac3-fixed-suite-import-rehearsal-v1', 'frozen_sha256': frozen_sha256,
            'test_rows_exercised': len(eligible), 'audit_count': len(run_ids), 'database_written': False,
            'test_rows_retained': False, 'model_called': False, 'execution_supported': False,
            'relationship_validation': 'structural_only_semantics_unverified', 'budget_enforcement': 'simulated_only',
            'notice': 'In-memory test only. Production import, relationship review, locked revalidation, real billing and execution remain unsupported.'}
