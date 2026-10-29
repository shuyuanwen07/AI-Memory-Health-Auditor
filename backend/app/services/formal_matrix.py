"""Materialise a frozen reviewed suite under its declared source permission."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    AuditRunModel, ConversationModel, ExperimentModel, MemoryModel,
    MemoryRelationshipModel, MessageModel, TestCaseModel,
)
from app.schemas.domain import (
    ExperimentStatus, GroundingStatus, MemoryStatus, TargetMemoryMaintenancePolicy,
    TargetMemoryWriterKind, TargetSystemAdapterKind, TestQualityStatus, TargetConfiguration,
    TestSuiteConfiguration, TestSuiteMetadata, TestSuiteMode,
)
from app.schemas.formal_experiment import (
    SyntheticMatrixCreateRequest, FormalMatrixCreateResponse, FormalMatrixScenario,
    FormalAcceptanceProtocol,
)
from app.schemas.research import annotation_fingerprint
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.extraction.rule_based import RuleBasedMemoryExtractor
from app.services.formal_freeze import formal_runtime_signature, formal_input_signature, assert_formal_inputs_frozen


def _stable_id(prefix: str, *parts: str) -> str:
    """Produce a short database ID stable across a frozen dataset version."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest().upper()
    return f"{prefix}{digest[:32]}"


class FormalSyntheticMatrixService:
    """Create pending audit runs; execution remains an explicit UI action.

    Gold tests are copied as an accepted, grounded *fixed* suite.  Every
    condition receives a cloned copy linked to one canonical source test, so
    the target AI never sees expected behaviour or gold memories while being
    answered, and comparisons remain paired.
    """

    VERSION = "synthetic-formal-matrix-v9"

    def create(self, db: Session, request: SyntheticMatrixCreateRequest, *, study_mode: str) -> FormalMatrixCreateResponse:
        from app.api.routes import reproducibility_snapshot
        dataset = request.dataset
        dataset_hash = annotation_fingerprint(dataset)
        release = getattr(request, 'source_release', None)
        source_origin = 'deidentified' if release is not None else 'synthetic'
        source_label = 'deidentified research' if release is not None else 'synthetic'
        runtime = formal_runtime_signature()
        protocol = FormalAcceptanceProtocol(
            format='formal-acceptance-protocol-v2',
            reader_control='fixed_strong_reader',
            study_mode=study_mode,
            frozen_at=datetime.now(timezone.utc), criteria=request.success_criteria,
            dataset_fingerprint_sha256=dataset_hash,
            runtime_source_sha256=runtime['source_sha256'],
            development_dataset_fingerprint_sha256=annotation_fingerprint(request.development_dataset) if request.development_dataset else None,
            distinct_history_check='no_normalized_history_overlap' if request.development_dataset else 'not_checked',
            study_design=request.study_design,
            source_release=release.model_dump(mode='json') if release is not None else None,
        )
        scenarios: list[FormalMatrixScenario] = []
        all_runs: list[AuditRunModel] = []

        for source in dataset.conversations:
            conversation_id = _stable_id("RESEARCH" if release is not None else "SYN", dataset.dataset_id, dataset.dataset_version, source.conversation_id)
            if db.get(ConversationModel, conversation_id):
                raise HTTPException(
                    409,
                    f"Reviewed scenario {source.conversation_id} was already materialised for this dataset version. "
                    "Use its existing experiment rather than creating a second copy.",
                )

            conversation = ConversationModel(
                id=conversation_id, authorised=True, source_origin=source_origin,
                created_at=source.messages[0].timestamp.astimezone(timezone.utc),
            )
            db.add(conversation)
            for sequence, message in enumerate(source.messages):
                db.add(MessageModel(
                    id=_stable_id("MSG", conversation_id, message.message_id),
                    conversation_id=conversation_id, source_message_id=message.message_id,
                    sequence=sequence, role=message.role, content=message.content,
                    timestamp=MessageModel.timestamp_for_storage(message.timestamp),
                    original_timestamp=message.timestamp.isoformat(),
                ))

            memory_ids = {
                memory.memory_id: _stable_id("MEM", conversation_id, memory.memory_id)
                for memory in source.gold_memories
            }
            for memory in source.gold_memories:
                db.add(MemoryModel(
                    id=memory_ids[memory.memory_id], conversation_id=conversation_id,
                    canonical_value=memory.canonical_value, status=MemoryStatus.CONFIRMED.value,
                    source_message_ids=list(memory.source_message_ids), timestamp=memory.timestamp,
                ))
            for memory in source.gold_memories:
                for relationship in memory.relationships:
                    db.add(MemoryRelationshipModel(
                        id=_stable_id("MR", conversation_id, memory.memory_id, relationship.type.value, relationship.target_memory_id),
                        memory_id=memory_ids[memory.memory_id], relationship_type=relationship.type.value,
                        target_memory_id=memory_ids[relationship.target_memory_id],
                    ))

            dimensions = list(dict.fromkeys(test.dimension for test in source.gold_tests))
            suite_configuration = TestSuiteConfiguration(
                test_budget=len(source.gold_tests), random_seed=request.random_seed,
                prompt_template_version=self.VERSION, pipeline_provider="rule_based",
                pipeline_model="frozen-human-suite", evaluator_provider="rule_based",
                evaluator_model=RuleBasedBehaviourEvaluator.VERSION, dimensions=dimensions,
                suite_mode=TestSuiteMode.FIXED_TEMPLATE,
            )
            experiment = ExperimentModel(
                id=_stable_id("EXP", dataset.dataset_id, dataset.dataset_version, source.conversation_id),
                conversation_id=conversation_id,
                label=f"{request.label_prefix}: {source.conversation_id}",
                status=ExperimentStatus.CREATED.value,
                test_suite_configuration=suite_configuration.model_dump(mode="json"),
                test_suite_metadata=TestSuiteMetadata().model_dump(mode="json"),
            )
            db.add(experiment)
            db.flush()

            runs: list[AuditRunModel] = []
            for repetition in range(request.repetitions):
                for condition in request.conditions:
                    run = AuditRunModel(
                        id=_stable_id("RUN", experiment.id, json.dumps((condition.identity, repetition), separators=(",", ":"))),
                        conversation_id=conversation_id, experiment_id=experiment.id,
                        status="CREATED", target_configuration=condition.target_configuration.value,
                        provider=condition.provider.value, model=condition.model,
                        temperature=condition.temperature, random_seed=request.random_seed,
                        test_budget=len(source.gold_tests), prompt_template_version=self.VERSION,
                        pipeline_provider="rule_based", pipeline_model="frozen-human-suite",
                        evaluator_provider="rule_based", evaluator_model=RuleBasedBehaviourEvaluator.VERSION,
                        memory_strategy=condition.memory_strategy.value,
                        memory_maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION.value,
                        target_memory_capacity=50, target_memory_writer=TargetMemoryWriterKind.RULE_BASED.value,
                        target_memory_writer_version=RuleBasedMemoryExtractor.VERSION,
                        target_system_adapter=TargetSystemAdapterKind.CONTROLLED_MEMORY.value,
                        target_system_adapter_version=runtime['adapter'],
                        reproducibility_metadata={
                            **reproducibility_snapshot(provider=condition.provider.value, model=condition.model,
                            temperature=condition.temperature, random_seed=request.random_seed,
                            test_budget=len(source.gold_tests), prompt_template_version=self.VERSION,
                            pipeline_provider='rule_based', pipeline_model='frozen-human-suite',
                            evaluator_provider='rule_based', evaluator_model=RuleBasedBehaviourEvaluator.VERSION,
                            memory_strategy=condition.memory_strategy.value,
                            memory_maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION.value,
                            target_memory_writer=TargetMemoryWriterKind.RULE_BASED,
                            target_memory_capacity=50, target_system_adapter=TargetSystemAdapterKind.CONTROLLED_MEMORY),
                            "formal_matrix_version": self.VERSION,
                            "formal_repetition_index": repetition + 1,
                            "formal_repetition_count": request.repetitions,
                            "formal_runtime_signature": runtime,
                            "formal_acceptance_protocol": protocol.model_dump(mode='json'),
                            "dataset_id": dataset.dataset_id, "dataset_version": dataset.dataset_version,
                            "dataset_fingerprint_sha256": dataset_hash, "pilot_id": request.pilot.pilot_id,
                            "suite_kind": f"frozen_human_labelled_{source_origin}", "condition_label": condition.label,
                            "source_origin": source_origin,
                            "target_retry_policy": {"max_attempts": 3, "timeout_seconds": 60.0,
                                                      "retryable_status_codes": [408, 409, 425, 429, 500, 502, 503, 504]},
                            "execution_budget": {"max_target_calls": len(source.gold_tests), "max_execution_seconds": 300},
                        },
                    )
                    db.add(run)
                    runs.append(run)
                    all_runs.append(run)
            db.flush()

            source_run = runs[0]
            source_tests: list[TestCaseModel] = []
            for gold in source.gold_tests:
                test = TestCaseModel(
                    id=_stable_id("T", source_run.id, gold.test_id), run_id=source_run.id,
                    dimension=gold.dimension.value, prompt=gold.prompt,
                    expected_behavior=gold.expected_behavior,
                    supporting_memory_ids=[memory_ids[item] for item in gold.supporting_memory_ids],
                    generator_version=self.VERSION, test_type=gold.test_type.value,
                    quality_status=TestQualityStatus.ACCEPTED.value,
                    grounding_status=GroundingStatus.GROUNDED.value,
                    validation_notes=f"Frozen human-labelled {source_label} suite: {gold.quality_note}",
                    target_memory_context=[],
                )
                db.add(test)
                source_tests.append(test)
            db.flush()
            for peer in runs[1:]:
                for source_test in source_tests:
                    db.add(TestCaseModel(
                        id=_stable_id("T", peer.id, source_test.id), run_id=peer.id,
                        suite_test_id=source_test.id, dimension=source_test.dimension,
                        prompt=source_test.prompt, expected_behavior=source_test.expected_behavior,
                        supporting_memory_ids=list(source_test.supporting_memory_ids),
                        generator_version=source_test.generator_version, test_type=source_test.test_type,
                        quality_status=source_test.quality_status, grounding_status=source_test.grounding_status,
                        validation_notes=source_test.validation_notes, target_memory_context=[],
                    ))
                peer.status = "TESTS_GENERATED"
            source_run.status = "TESTS_GENERATED"
            experiment.test_suite_source_run_id = source_run.id
            experiment.status = ExperimentStatus.TEST_SUITE_GENERATED.value
            experiment.test_suite_metadata = TestSuiteMetadata(
                test_count=len(source_tests), dimensions=dimensions, generator_version=self.VERSION,
                generated_at=source.messages[-1].timestamp,
            ).model_dump(mode="json")
            db.flush()
            scenarios.append(FormalMatrixScenario(
                source_conversation_id=source.conversation_id, experiment_id=experiment.id,
                run_ids=[run.id for run in runs], test_count=len(source_tests),
            ))

        plan = FormalMatrixCreateResponse(
            acceptance_protocol=protocol,
            dataset_id=dataset.dataset_id, dataset_version=dataset.dataset_version,
            dataset_fingerprint_sha256=dataset_hash, pilot_id=request.pilot.pilot_id,
            condition_count=len(request.conditions), repetition_count=request.repetitions, scenario_count=len(scenarios),
            total_audit_runs=sum(len(item.run_ids) for item in scenarios),
            total_target_calls=sum(item.test_count * len(item.run_ids) for item in scenarios),
            scenarios=scenarios,
            notice=(f"Reviewed {source_label} scenarios were materialised with a frozen supplied test suite. "
                    "Runs are pending; execute them explicitly to record target responses and evaluations. "
                    "Permission, deidentification and independent human authorship are caller declarations, not authenticated by the service."),
        )

        # Save one complete manifest in every condition before signing its inputs.
        # Recovery must not infer a complete matrix from whichever rows survive.
        manifest = plan.model_dump(mode='json')
        for run in all_runs:
            run.reproducibility_metadata = {**run.reproducibility_metadata, 'formal_matrix_manifest': manifest}
        db.flush()
        for run in all_runs:
            run.reproducibility_metadata = {**run.reproducibility_metadata, 'formal_input_sha256': formal_input_signature(db, run)}
        db.commit()
        return plan

    def restore(self, db: Session, run_id: str) -> FormalMatrixCreateResponse:
        from pydantic import ValidationError
        from sqlalchemy import select
        selected = db.get(AuditRunModel, run_id)
        if not selected:
            raise HTTPException(404, 'The saved experiment could not be found.')
        metadata = selected.reproducibility_metadata or {}
        if metadata.get('coverage_policy', 'strict_full_v1') != 'strict_full_v1':
            raise HTTPException(409, 'Formal matrix restoration requires strict coverage.')
        try:
            plan = FormalMatrixCreateResponse.model_validate(metadata.get('formal_matrix_manifest'))
        except ValidationError as error:
            raise HTTPException(409, 'This older experiment has no complete saved execution plan. Its results remain available; create a newly reviewed experiment to collect more results.') from error
        if (plan.acceptance_protocol.study_mode == 'formal_experiment_b'
                and plan.repetition_count < 3):
            raise HTTPException(409, 'Formal Experiment B requires at least three repetitions per condition. This saved plan cannot be analysed as a formal B study.')
        if (plan.acceptance_protocol.study_mode == 'formal_experiment_b'
                and plan.acceptance_protocol.reader_control != 'fixed_strong_reader'):
            raise HTTPException(409,
                'This older plan did not freeze one Strong reader across the memory strategies. '
                'Its historical answers and results are preserved, but it cannot be resumed as a controlled Experiment B study. '
                'Create a newly reviewed study to compare memory strategies with one fixed reader.')
        ids = [item for scenario in plan.scenarios for item in scenario.run_ids]
        if run_id not in ids or len(ids) != len(set(ids)) or len(ids) != plan.total_audit_runs or len(plan.scenarios) != plan.scenario_count:
            raise HTTPException(409, 'The saved execution plan is inconsistent. Existing results are preserved.')
        rows = {run.id: run for run in db.scalars(select(AuditRunModel).where(AuditRunModel.id.in_(ids)))}
        if len(rows) != len(ids):
            raise HTTPException(409, 'Some conditions in the saved plan are missing. This experiment cannot be resumed as a complete matrix.')
        # Compare peers against the original signed JSON, not a current-schema
        # dump that injects new optional defaults into older saved manifests.
        manifest = metadata['formal_matrix_manifest']
        for scenario in plan.scenarios:
            if len(scenario.run_ids) != plan.condition_count * plan.repetition_count:
                raise HTTPException(409, 'The saved condition count no longer matches its plan.')
            for item in scenario.run_ids:
                run = rows[item]
                saved = run.reproducibility_metadata or {}
                if saved.get('coverage_policy', 'strict_full_v1') != 'strict_full_v1':
                    raise HTTPException(409, 'Every formal matrix condition requires strict coverage.')
                if run.experiment_id != scenario.experiment_id or saved.get('formal_matrix_manifest') != manifest or saved.get('formal_acceptance_protocol') != manifest['acceptance_protocol']:
                    raise HTTPException(409, 'The saved conditions no longer belong to the same frozen plan.')
                if (plan.acceptance_protocol.reader_control == 'fixed_strong_reader'
                        and run.target_configuration != TargetConfiguration.STRONG.value):
                    raise HTTPException(409, 'A saved condition no longer uses the frozen Strong reader. Existing results are preserved.')
                assert_formal_inputs_frozen(db, run)
        if plan.total_target_calls != sum(scenario.test_count * len(scenario.run_ids) for scenario in plan.scenarios):
            raise HTTPException(409, 'The saved call budget no longer matches its plan.')
        return plan
