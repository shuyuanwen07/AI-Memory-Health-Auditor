"""Prepare, then register a separate execution smoke only after explicit human approval.

1. On the host, --prepare --review-summary FILE --human-confirmation FILE.
2. Inside backend Docker, --register --protocol /output/.../protocol.json.
   Redirect its single JSON result on the HOST to registrations.json.

No generation is rerun. The --register mode is the only database mutation;
imports, --help and --prepare do not import database/application modules.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ac2_ten_execution_common import (
    FORMAT,
    OUTPUT_RELATIVE,
    ROLE,
    SCRIPT_NAMES,
    SOURCE_RELATIVE,
    GuardError,
    application_hashes,
    check_protocol,
    now,
    question_signature,
    read,
    relative,
    save,
    sha,
    validate_approval,
)


def prepare(root, source_folder, output_folder, review_summary, human_confirmation):
    root, output_folder = Path(root), Path(output_folder)
    try:
        output_folder.resolve().relative_to((root / 'output').resolve())
    except ValueError as exc:
        raise GuardError('Execution protocol must stay in the Docker-visible project output folder.') from exc
    approval = validate_approval(root, source_folder, review_summary, human_confirmation)
    protocol = {'format': FORMAT, 'role': ROLE, 'created_utc': now(),
                'source_folder': relative(root, source_folder), **approval,
                'application_sha256': application_hashes(root),
                'scripts_sha256': {str(Path('scripts') / name): sha(root / 'scripts' / name) for name in SCRIPT_NAMES},
                'condition': {'provider': 'openai', 'model': 'gpt-6-astra', 'reasoning_effort': 'max',
                              'target_memory_writer': 'llm_structured', 'memory_strategy': 'relationship_packet',
                              'evaluator_provider': 'openai', 'evaluator_model': 'gpt-6-astra',
                              'pipeline_provider': 'openai', 'pipeline_model': 'gpt-6-astra',
                              'target_configuration': 'weak', 'retrieval_mode': 'fixed'},
                'histories_planned': 10, 'questions_planned': 40, 'max_parallel_histories': 3,
                'profile_preservation': 'Restore the exact approved source profile on each NEW fork before commit, including null output_token_limit. Reject every other profile drift. Recompute its configuration fingerprint from the actual final configuration.',
                'previous_attempt': 'output/proposal-delivery/ac2-original-ten-execution-smoke-20261101-v1; retained guard-stop attempt, never resumed or replayed by v2.',
                'design': 'One new condition per approved source, same frozen questions. No question regeneration. Structured target writer and reader use direct OpenAI Astra max. Source profile and weak/fixed controls are retained.',
                'interpretation': 'Execution/evaluation smoke only; automatic answer assessments are separate from human question-validity labels. Not a four-strategy comparison or independent AC3 accuracy validation.',
                'limitations': ['Previously observed synthetic sources; not independent or representative.',
                                'The active approved cohort may contain revised questions. Replaced versions remain historical evidence, not additional independent samples.',
                                'Human confirmation is user-reported and AI-assisted; identities are not authenticated.',
                                'No host-level replay of an ambiguous model operation. Backend transport attempts remain in provider receipts.',
                                'Provider failures or missing receipts are retained, not counted as passing answers.']}
    # Every guard and input read precedes creating any real protocol directory.
    output_folder.mkdir(parents=True, exist_ok=False)
    save(output_folder / 'protocol.json', protocol, exclusive=True)
    return output_folder / 'protocol.json'


def restore_approved_profile(target, approved_profile, fingerprint_fn):
    """Undo only build_audit's null -> 2048 profile default on a NEW fork.

    AuditRunModel has no target_memory_profile column: the authoritative
    stored profile is in reproducibility_metadata. This runs before the
    fork transaction commits. Original source rows remain untouched.
    """
    before = copy.deepcopy(target.reproducibility_metadata)
    observed = before.get('target_memory_profile')
    expected_normalized = copy.deepcopy(approved_profile)
    if expected_normalized.get('output_token_limit') is None:
        expected_normalized['output_token_limit'] = 2048
    if observed != approved_profile and observed != expected_normalized:
        raise GuardError('Fork changed source profile beyond the known null output-token default.')
    if observed == expected_normalized and observed != approved_profile and 'output_token_limit' not in approved_profile:
        raise GuardError('Approved profile must explicitly contain its nullable output-token field.')
    metadata = copy.deepcopy(before)
    metadata['target_memory_profile'] = copy.deepcopy(approved_profile)
    fields = ('provider', 'model', 'temperature', 'random_seed', 'test_budget',
              'pipeline_provider', 'pipeline_model', 'semantic_review_provider', 'semantic_review_model',
              'evaluator_provider', 'evaluator_model', 'retrieval_mode', 'retrieval_provider', 'retrieval_model',
              'memory_strategy', 'memory_maintenance_policy', 'target_memory_capacity',
              'target_memory_writer', 'target_memory_writer_version',
              'target_system_adapter', 'target_system_adapter_version')
    configuration = {key: getattr(target, key) for key in fields}
    configuration['retrieval_agent_version'] = metadata.get('retrieval_agent_version')
    configuration['target_memory_profile'] = copy.deepcopy(approved_profile)
    if metadata.get('coverage_policy', 'strict_full_v1') != 'strict_full_v1':
        configuration['coverage_policy'] = metadata['coverage_policy']
    metadata['configuration_fingerprint'] = fingerprint_fn(configuration)
    metadata['execution_smoke_profile_preservation'] = {
        'policy': 'exact_approved_source_profile_v2',
        'created_profile_before_restore': observed,
        'created_configuration_fingerprint_before_restore': before.get('configuration_fingerprint'),
        'output_token_limit_restored': observed != approved_profile,
        'configuration_fingerprint_recomputed': True,
    }
    target.reproducibility_metadata = metadata


def register(root, protocol_path):
    root = Path(root)
    protocol = read(protocol_path)
    check_protocol(root, protocol)  # No DB imports, reads or mutations before this guard.
    import json

    from app.api.quality_routes import fork_conditions
    from app.api.routes import (
        assert_test_evidence_available,
        audit_run_lock,
        audit_schema,
        fingerprint,
    )
    from app.database.session import SessionLocal
    from app.models import AuditRunModel, ExperimentModel, TestCaseModel
    from sqlalchemy import select

    registrations = []
    with SessionLocal() as db, audit_run_lock(ROLE, db=db):
        sources = []
        previous = list(db.scalars(select(ExperimentModel)).all())
        for item in protocol['histories']:
            source = db.get(AuditRunModel, item['source_run_id'])
            if not source or source.status != 'TESTS_GENERATED' or source.conversation_id != item['conversation_id']:
                raise GuardError('A source audit is missing, changed or has already started.')
            if any((g.test_suite_metadata or {}).get('study_role') == ROLE
                   and (g.test_suite_metadata or {}).get('diagnostic_source_run_id') == source.id for g in previous):
                raise GuardError('A registration already exists; reconcile it instead of creating a duplicate.')
            schema = audit_schema(source)
            if (schema.target_configuration.value != 'weak' or schema.retrieval_mode.value != 'fixed'
                    or schema.pipeline_provider != 'openai' or schema.pipeline_model != 'gpt-6-astra'):
                raise GuardError('Source audit configuration differs from its approved settings.')
            live = schema.model_dump(mode='json')
            for field in ('provider', 'model', 'pipeline_provider', 'pipeline_model', 'semantic_review_provider',
                          'semantic_review_model', 'test_budget', 'temperature', 'random_seed',
                          'prompt_template_version', 'memory_strategy', 'memory_maintenance_policy',
                          'target_memory_capacity', 'target_memory_writer', 'target_system_adapter',
                          'target_configuration', 'retrieval_mode', 'target_memory_profile'):
                if live.get(field) != item['source_configuration'].get(field):
                    raise GuardError('A source configuration field changed after approval.')
            profile = schema.target_memory_profile
            if (profile.identity_analysis != 'off' or profile.answer_validation != 'off'
                    or profile.retain_assistant_history or profile.retrieve_message_context
                    or profile.isolate_project_scope or profile.prefer_current_state or profile.additional_instructions):
                raise GuardError('The source must retain its weak/fixed profile with auxiliary features off.')
            originals = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == source.id)).all())
            if ({q.id for q in originals} != set(item['source_test_ids']) or len(originals) != 4
                    or sorted(question_signature({'dimension':q.dimension, 'test_type':q.test_type,
                         'prompt':q.prompt, 'expected_behavior':q.expected_behavior,
                         'supporting_memory_ids':q.supporting_memory_ids, 'generator_version':q.generator_version}) for q in originals)
                    != sorted(question_signature(q) for q in item['questions'])):
                raise GuardError('The database questions differ from the reviewed frozen source.')
            assert_test_evidence_available(db, source.conversation_id, originals, 422)
            sources.append((item, source, schema, profile))
        # All ten sources were checked before any mutation; commit the forks atomically.
        for item, source, schema, profile in sources:
            package = fork_conditions(source, db, [profile], role=ROLE,
                note='Separate execution smoke. User reports two independent human checks of the forty source questions; automatic target-answer review is separate.',
                same_suite=True, targeted_memory_writer='llm_structured', shared_memory_strategy='relationship_packet',
                target_provider='openai', target_model='gpt-6-astra',
                target_evaluator_provider='openai', target_evaluator_model='gpt-6-astra',
                preserve_target_configuration=True, commit=False)
            rid = package['runs'][0]['run_id']
            target = db.get(AuditRunModel, rid)
            restore_approved_profile(target, item['source_configuration']['target_memory_profile'], fingerprint)
            db.flush()
            if audit_schema(target).target_memory_profile.model_dump(mode='json') != item['source_configuration']['target_memory_profile']:
                raise GuardError('The new fork did not round-trip the exact approved source profile.')
            copied = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == rid)).all())
            if len(copied) != 4 or any(q.grounding_status != 'grounded' for q in copied):
                raise GuardError('Copied questions lack complete grounded evidence; no registration committed.')
            # Record the explicit human-approved quality decision on NEW copies;
            # preserve the original source rows, questions and automatic history.
            for question in copied:
                question.quality_status = 'accepted'
                question.validation_notes = ('Operator-recorded human acceptance after two independent checks, '
                    f"review summary SHA256 {protocol['review_summary_sha256']}. Source question content unchanged.")
            metadata = dict(target.reproducibility_metadata)
            metadata['question_validity_confirmation_sha256'] = protocol['human_confirmation_sha256']
            metadata['execution_smoke_protocol_sha256'] = sha(protocol_path)
            metadata['assessment_basis'] = 'automatic; not independent human answer accuracy'
            target.reproducibility_metadata = metadata
            registrations.append({'history_id': item['history_id'], 'source_run_id': source.id,
                                  'experiment_id': package['experiment_id'], 'run_id': rid,
                                  'copied_test_ids': sorted(q.id for q in copied)})
        db.commit()
    result = {'format': FORMAT + '-registrations', 'protocol_sha256': sha(protocol_path),
              'role': ROLE, 'registered_utc': now(), 'registrations': registrations}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def inspect(root, protocol_path):
    """Read-only recovery snapshot, including responses from failed/incomplete runs."""
    protocol = read(protocol_path)
    check_protocol(root, protocol)
    from app.api.routes import (
        audit_schema,
        eval_schema,
        public_test_schema,
        response_schema,
        target_memory_trace_payload,
    )
    from app.database.session import SessionLocal
    from app.models import (
        AuditRunModel,
        EvaluationResultModel,
        ExperimentModel,
        TargetResponseModel,
        TestCaseModel,
    )
    from sqlalchemy import select

    result = {'format': FORMAT + '-read-only-snapshot', 'observed_utc': now(),
              'protocol_sha256': sha(protocol_path), 'histories': []}
    with SessionLocal() as db:
        groups = list(db.scalars(select(ExperimentModel)).all())
        for source in protocol['histories']:
            matches = [group for group in groups if (group.test_suite_metadata or {}).get('study_role') == ROLE
                       and (group.test_suite_metadata or {}).get('diagnostic_source_run_id') == source['source_run_id']]
            item = {'history_id': source['history_id'], 'registration_count': len(matches), 'groups': []}
            for group in matches:
                package = {'experiment_id': group.id, 'status': group.status, 'runs': []}
                for audit in db.scalars(select(AuditRunModel).where(AuditRunModel.experiment_id == group.id)).all():
                    questions = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id == audit.id)).all())
                    answers = list(db.scalars(select(TargetResponseModel).where(TargetResponseModel.run_id == audit.id)).all())
                    evaluations = list(db.scalars(select(EvaluationResultModel).join(TestCaseModel)
                                                  .where(TestCaseModel.run_id == audit.id)).all())
                    package['runs'].append({'audit': audit_schema(audit).model_dump(mode='json'),
                        'questions': [public_test_schema(q).model_dump(mode='json') for q in questions],
                        'responses': [response_schema(answer).model_dump(mode='json') for answer in answers],
                        'evaluations': [eval_schema(evaluation).model_dump(mode='json') for evaluation in evaluations],
                        'trace': target_memory_trace_payload(audit, db)})
                item['groups'].append(package)
            result['histories'].append(item)
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--register', action='store_true')
    mode.add_argument('--inspect', action='store_true', help='Read-only partial-result recovery; never executes a model.')
    parser.add_argument('--source-folder', type=Path, default=root / SOURCE_RELATIVE)
    parser.add_argument('--output-folder', type=Path, default=root / OUTPUT_RELATIVE)
    parser.add_argument('--review-summary', type=Path)
    parser.add_argument('--human-confirmation', type=Path)
    parser.add_argument('--protocol', type=Path, default=root / OUTPUT_RELATIVE / 'protocol.json')
    args = parser.parse_args()
    if args.prepare:
        if not args.review_summary or not args.human_confirmation:
            parser.error('--prepare requires --review-summary and --human-confirmation')
        print(prepare(root, args.source_folder, args.output_folder, args.review_summary, args.human_confirmation))
    elif args.register:
        register(root, args.protocol)
    else:
        import json
        print(json.dumps(inspect(root, args.protocol), ensure_ascii=False))


if __name__ == '__main__':
    main()
