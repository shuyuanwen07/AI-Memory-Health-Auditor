"""Read-only inspection of staged AC3 application data; never authorizes execution.

The result is an observation, not an authorization: the transaction has no
execution lock, so future work must revalidate under the same lock/transaction
used for dispatch. It calls no provider and modifies no records.
"""
from sqlalchemy import select
from app.models import AuditRunModel, TargetResponseModel, TestCaseModel
from app.schemas.domain import AuditStatus
from app.services.formal_freeze import formal_input_signature
from scripts.ac3_database_mapping import compile_database_stage
from scripts.ac3_fixed_suite_adapter import sha


def inspect_staged_ac3(db, frozen_path, frozen_sha256, reservation, history_conversations, history_runs, *, settled_receipts=None):
    if db.new or db.dirty or db.deleted:
        raise ValueError('A clean session is required')
    if not isinstance(history_runs, dict) or set(history_runs) != set(history_conversations):
        raise ValueError('Exactly one audit per frozen history is required')
    run_ids = list(history_runs.values())
    if any(not isinstance(x, str) or not x.strip() for x in run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError('Audit identifiers must be distinct')
    with db.no_autoflush:
        plan = compile_database_stage(db, frozen_path, frozen_sha256, reservation, history_conversations)
        eligible = [row for row in plan['items'] if row['grounding_review'] == 'valid']
        if len(eligible) != plan['eligible_question_count']:
            raise ValueError('Eligible count changed')
        if settled_receipts is not None and (not isinstance(settled_receipts, dict) or
                not set(settled_receipts).issubset({row['test_id'] for row in eligible})):
            raise ValueError('Ledger contains unknown frozen questions')
        config = plan['model_configuration']
        for history, run_id in history_runs.items():
            run = db.get(AuditRunModel, run_id, populate_existing=True)
            if run is None or run.status != AuditStatus.RESEARCH_STAGED.value or run.conversation_id != history_conversations[history] or run.experiment_id is not None:
                raise ValueError('Audit is not the expected quarantined staged history')
            if any(getattr(run, key) != config[value] for key, value in (
                ('provider', 'target_provider'), ('model', 'target_model'),
                ('evaluator_provider', 'evaluator_provider'), ('evaluator_model', 'evaluator_model'),
                ('pipeline_provider', 'pipeline_provider'), ('pipeline_model', 'pipeline_model'),
                ('memory_strategy', 'target_strategy'))):
                raise ValueError('Staged audit configuration changed')
            rows = [x for x in eligible if x['history_id'] == history]
            metadata = (run.reproducibility_metadata or {}).get('ac3_staged_suite') or {}
            if not rows or run.test_budget != len(rows) or metadata.get('frozen_sha256') != frozen_sha256 or metadata.get('history_id') != history or metadata.get('test_count') != len(rows) or metadata.get('execution_supported') is not False:
                raise ValueError('Staged receipt differs from frozen suite')
            if metadata.get('input_sha256') != formal_input_signature(db, run):
                raise ValueError('Staged input fingerprint changed')
            expected = {'AC3' + sha(f"{frozen_sha256}|{run_id}|{row['test_id']}".encode())[:32].upper(): row for row in rows}
            responses = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)))
            if settled_receipts is None:
                if responses:
                    raise ValueError('Staged audit has unexpected target responses')
            else:
                expected_responses = {local_id: settled_receipts[item['test_id']]
                                      for local_id, item in expected.items() if item['test_id'] in settled_receipts}
                if (len(responses) != len(expected_responses) or
                    {response.test_id for response in responses} != set(expected_responses)):
                    raise ValueError('Saved responses differ from the settled ledger')
                for response in responses:
                    receipt = expected_responses[response.test_id]
                    if (response.response_text != receipt['response_text'] or response.model != config['target_model']):
                        raise ValueError('Saved response content or model differs from the settled ledger')
            saved = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id).execution_options(populate_existing=True)))
            if set(expected) != {row.id for row in saved}:
                raise ValueError('Staged question identities changed')
            for row in saved:
                item = expected[row.id]
                if (row.dimension != item['dimension'] or row.prompt != item['question'] or
                    row.expected_behavior != item['expected_behavior'] or row.supporting_memory_ids != item['supporting_memory_ids'] or
                    row.generator_version != 'ac3-quarantined-stage-v1' or row.quality_status != 'pending' or row.grounding_status != 'pending'):
                    raise ValueError('Staged question content or status changed')
    return {'format': 'ac3-staged-readiness-observation-v1', 'audit_count': len(run_ids),
            'eligible_question_count': len(eligible), 'execution_authorized': False,
            'model_called': False, 'database_written': False,
            'blocking_conditions': ['no_live_budget_guard', 'relationship_semantics_and_completeness_unverified',
                'no_atomic_dispatch_revalidation', 'no_provider_execution_adapter'],
            'notice': 'Read-only observation only. Never use this result to dispatch or change audit state.'}
