"""Controlled evaluator ablation over the same immutable target answers."""
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditRunModel, ExperimentModel, TargetResponseModel, TestCaseModel


def reuse_target_answers(db: Session, run_id: str, source_run_id: str):
    if run_id == source_run_id:
        raise HTTPException(422, 'Choose a different source run.')
    target, source = db.get(AuditRunModel, run_id), db.get(AuditRunModel, source_run_id)
    if not target or not source:
        raise HTTPException(404, 'Audit not found.')
    experiment = db.get(ExperimentModel, target.experiment_id) if target.experiment_id else None
    config = experiment.test_suite_configuration if experiment else {}
    if not experiment or target.experiment_id != source.experiment_id or not config.get('compare_evaluators'):
        raise HTTPException(409, 'Answer reuse requires one explicit evaluator-ablation experiment.')
    if experiment.status == 'CANCELLED':
        raise HTTPException(409, 'This experiment was cancelled.')
    validate_shared_target(source, target)
    tm = target.reproducibility_metadata or {}
    if source.status not in {'TESTS_EXECUTED', 'COMPLETED'}:
        raise HTTPException(409, 'Execute the source answers before reusing them.')
    existing = db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == run_id)).all()
    prior = tm.get('shared_answer_source_run_id')
    if prior and prior != source_run_id:
        raise HTTPException(409, 'The frozen shared-answer source cannot be changed.')
    if (source.reproducibility_metadata or {}).get('shared_answer_source_run_id'):
        raise HTTPException(409, 'Use the original independently executed source run.')
    if existing:
        if prior == source_run_id and target.status in {'TESTS_EXECUTED', 'COMPLETED'}:
            return existing
        raise HTTPException(409, 'Existing target answers cannot be overwritten or relabelled as shared.')
    if target.status != 'TESTS_GENERATED':
        raise HTTPException(409, 'Prepare and review the destination questions first.')
    source_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source_run_id)).all()
    target_tests = db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == run_id)).all()
    def canonical(test):
        return test.suite_test_id or test.id
    originals = {canonical(test): test for test in source_tests}
    if not target_tests or len(originals) != len(source_tests) or len(originals) != len(target_tests) or set(originals) != {canonical(test) for test in target_tests}:
        raise HTTPException(409, 'Both runs must use the exact canonical question suite.')
    source_answers = {row.test_id: row for row in db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == source_run_id)).all()}
    if len(source_answers) != len(source_tests):
        raise HTTPException(409, 'Source answers are incomplete.')
    checks = ('prompt', 'expected_behavior', 'dimension', 'supporting_memory_ids', 'quality_status', 'generator_version')
    for test in target_tests:
        original = originals[canonical(test)]
        if any(getattr(test, key) != getattr(original, key) for key in checks) or test.quality_status != 'accepted':
            raise HTTPException(409, 'Frozen reviewed question content differs.')
    copies = []
    for test in target_tests:
        original = source_answers[originals[canonical(test)].id]
        receipt = original.execution_metadata or {}
        copies.append(TargetResponseModel(id='R'+uuid4().hex.upper(), test_id=test.id, run_id=run_id,
            response_text=original.response_text, model=original.model, temperature=original.temperature,
            execution_metadata={'request_attempts': 0, 'latency_ms': 0, 'input_tokens': 0, 'output_tokens': 0,
                'total_tokens': 0, 'response_source': 'shared_target_answer',
                'shared_source_run_id': source_run_id, 'shared_source_response_id': original.id,
                'completion_status': receipt.get('completion_status'), 'finish_reason': receipt.get('finish_reason'),
                'requested_output_token_limit': receipt.get('requested_output_token_limit'),
                'memory_input': receipt.get('memory_input')}, created_at=datetime.now(timezone.utc)))
    db.add_all(copies)
    target.reproducibility_metadata = {**tm, 'shared_answer_source_run_id': source_run_id}
    target.status = 'TESTS_EXECUTED'
    experiment.status = 'RUNNING'
    db.commit()
    return copies


def validate_shared_target(source, target):
    fields = ('conversation_id', 'provider', 'model', 'temperature', 'random_seed', 'target_configuration',
              'memory_strategy', 'memory_maintenance_policy', 'target_memory_capacity', 'target_memory_writer',
              'target_memory_writer_version', 'target_system_adapter', 'target_system_adapter_version',
              'retrieval_mode', 'retrieval_provider', 'retrieval_model',
              'test_budget', 'prompt_template_version')
    if any(getattr(source, key) != getattr(target, key) for key in fields):
        raise HTTPException(409, 'Target settings must match exactly to reuse answers.')
    sm, tm = source.reproducibility_metadata or {}, target.reproducibility_metadata or {}
    for key in ('target_memory_profile', 'target_retry_policy', 'memory_policy_version',
                'retrieval_agent_version'):
        if sm.get(key) != tm.get(key):
            raise HTTPException(409, 'Frozen target policy settings differ.')
