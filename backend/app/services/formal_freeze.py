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
from app.schemas.domain import TargetConfiguration


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
    from app.extraction.llm import pipeline_output_token_cap
    return {
        'source_sha256': digest.hexdigest(),
        'evaluator': RuleBasedBehaviourEvaluator.VERSION,
        'writer': RuleBasedMemoryExtractor.VERSION,
        'adapter': ControlledTargetSystemAdapter.version,
        'pipeline_output_token_cap': str(pipeline_output_token_cap()),
    }


def assert_formal_runtime_frozen(audit) -> None:
    metadata = audit.reproducibility_metadata or {}
    if not metadata.get('formal_matrix_version'):
        return
    if metadata.get('coverage_policy', 'strict_full_v1') != 'strict_full_v1':
        raise HTTPException(409, 'Formal studies require strict coverage.')
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
                for row in db.scalars(select(model).where(predicate).order_by(model.id).execution_options(populate_existing=True))]

    def serial(value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        raise TypeError(f'Unsupported frozen input type: {type(value).__name__}')

    memories = rows(MemoryModel, MemoryModel.conversation_id == audit.conversation_id)
    memory_ids = [item['id'] for item in memories]
    experiment = db.get(ExperimentModel, audit.experiment_id) if audit.experiment_id else None
    fields = ('conversation_id', 'experiment_id', 'target_configuration', 'provider', 'model',
              'temperature', 'random_seed', 'test_budget', 'prompt_template_version',
              'pipeline_provider', 'pipeline_model', 'semantic_review_provider', 'semantic_review_model',
              'evaluator_provider', 'evaluator_model',
              'memory_strategy', 'memory_maintenance_policy', 'target_memory_capacity',
              'target_memory_writer', 'target_memory_writer_version',
              'target_system_adapter', 'target_system_adapter_version')
    metadata = audit.reproducibility_metadata or {}
    messages = rows(MessageModel, MessageModel.conversation_id == audit.conversation_id)
    for message in messages:
        # An additive, empty provenance column must not invalidate pre-0025
        # input receipts. Non-empty provenance is an input and stays frozen.
        if message.get('original_timestamp') is None:
            message.pop('original_timestamp', None)
    payload = {
        'version': 'formal-inputs-v2',
        'configuration': {field: getattr(audit, field) for field in fields},
        'execution_controls': {key: metadata.get(key) for key in
                               ('target_memory_profile', 'target_retry_policy', 'execution_budget')},
        'acceptance_protocol': metadata.get('formal_acceptance_protocol'),
        'messages': messages,
        'memories': memories,
        'relationships': rows(MemoryRelationshipModel, MemoryRelationshipModel.memory_id.in_(memory_ids)),
        'tests': rows(TestCaseModel, TestCaseModel.run_id == audit.id, ('target_memory_context',)),
        'suite_configuration': experiment.test_suite_configuration if experiment else None,
        'canonical_run': experiment.test_suite_source_run_id if experiment else None,
    }
    if 'formal_repetition_index' in metadata:
        payload['repetition'] = {key: metadata.get(key) for key in ('formal_repetition_index', 'formal_repetition_count')}
    if 'formal_matrix_manifest' in metadata:
        payload['matrix_manifest'] = metadata['formal_matrix_manifest']
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, default=serial).encode()).hexdigest()


def assert_formal_inputs_frozen(db: Session, audit) -> None:
    from app.services.benchmark_plan import assert_benchmark_plan_inputs_frozen
    assert_benchmark_plan_inputs_frozen(db, audit)
    metadata = audit.reproducibility_metadata or {}
    if not metadata.get('formal_matrix_version'):
        return
    if metadata.get('coverage_policy', 'strict_full_v1') != 'strict_full_v1':
        raise HTTPException(409, 'Formal studies require strict coverage.')
    protocol = metadata.get('formal_acceptance_protocol') or {}
    if protocol.get('study_mode') == 'formal_experiment_b' and (
        protocol.get('reader_control') != 'fixed_strong_reader'
        or audit.target_configuration != TargetConfiguration.STRONG.value
    ):
        raise HTTPException(409,
            'Formal Experiment B requires one frozen Strong reader for every memory strategy. '
            'This plan does not satisfy that control. Create a newly reviewed study; '
            'historical answers and results are preserved.')
    saved = metadata.get('formal_input_sha256')
    if not saved or saved != formal_input_signature(db, audit):
        raise HTTPException(409,
            'The source data, reference questions or settings of this frozen experiment have changed. '
            'Create a newly reviewed dataset version before continuing. Existing results are preserved.')
