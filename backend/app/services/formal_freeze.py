"""Reject software drift before doing work on a frozen formal matrix."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MessageModel, MemoryModel, MemoryRelationshipModel, TestCaseModel, ExperimentModel
from pathlib import Path

from fastapi import HTTPException

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.target_systems.controlled import ControlledTargetSystemAdapter


def formal_runtime_signature() -> dict[str, str]:
    # Hash package source, including dependencies of extraction, retrieval,
    # prompts, evaluation and score aggregation. Version labels alone cannot
    # detect a change made without a corresponding version bump.
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(package.rglob('*.py')):
        relative = path.relative_to(package).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, 'big'))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return {
        'source_sha256': digest.hexdigest(),
        'evaluator': RuleBasedBehaviourEvaluator.VERSION,
        'writer': RuleBasedMemoryExtractor.VERSION,
        'adapter': ControlledTargetSystemAdapter.version,
    }


def assert_formal_runtime_frozen(audit) -> None:
    metadata = audit.reproducibility_metadata or {}
    if not metadata.get('formal_matrix_version'):
        return
    saved = metadata.get('formal_runtime_signature')
    if not saved or saved != formal_runtime_signature():
        raise HTTPException(409,
            'This frozen experiment no longer matches the installed audit software. '
            'Restore its original software or create a newly reviewed experiment before continuing. '
            'Existing answers and results have been preserved.')



def formal_input_signature(db: Session, audit) -> str:
    """Fingerprint saved research inputs, excluding outputs and lifecycle state.

    Datetimes use UTC independently of database timezone round-tripping.
    Retrieved target context is an output and must not invalidate the input.
    """
    def rows(model, predicate, excluded=()):
        return [{column.name: getattr(row, column.name) for column in model.__table__.columns
                 if column.name not in excluded}
                for row in db.scalars(select(model).where(predicate).order_by(model.id))]

    def serial(value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        raise TypeError(f'Unsupported frozen input type: {type(value).__name__}')

    memories = rows(MemoryModel, MemoryModel.conversation_id == audit.conversation_id)
    memory_ids = [item['id'] for item in memories]
    experiment = db.get(ExperimentModel, audit.experiment_id)
    fields = ('conversation_id', 'experiment_id', 'target_configuration', 'provider', 'model',
              'temperature', 'random_seed', 'test_budget', 'prompt_template_version',
              'pipeline_provider', 'pipeline_model', 'evaluator_provider', 'evaluator_model',
              'memory_strategy', 'memory_maintenance_policy', 'target_memory_capacity',
              'target_memory_writer', 'target_memory_writer_version',
              'target_system_adapter', 'target_system_adapter_version')
    metadata = audit.reproducibility_metadata or {}
    payload = {
        'version': 'formal-inputs-v1',
        'configuration': {field: getattr(audit, field) for field in fields},
        'execution_controls': {key: metadata.get(key) for key in
                               ('target_memory_profile', 'target_retry_policy', 'execution_budget')},
        'messages': rows(MessageModel, MessageModel.conversation_id == audit.conversation_id),
        'memories': memories,
        'relationships': rows(MemoryRelationshipModel, MemoryRelationshipModel.memory_id.in_(memory_ids)),
        'tests': rows(TestCaseModel, TestCaseModel.run_id == audit.id, ('target_memory_context',)),
        'suite_configuration': experiment.test_suite_configuration if experiment else None,
        'canonical_run': experiment.test_suite_source_run_id if experiment else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, default=serial).encode()).hexdigest()


def assert_formal_inputs_frozen(db: Session, audit) -> None:
    metadata = audit.reproducibility_metadata or {}
    if not metadata.get('formal_matrix_version'):
        return
    saved = metadata.get('formal_input_sha256')
    if not saved or saved != formal_input_signature(db, audit):
        raise HTTPException(409,
            'The source data, reference questions or settings of this frozen experiment have changed. '
            'Create a newly reviewed dataset version before continuing. Existing results are preserved.')
