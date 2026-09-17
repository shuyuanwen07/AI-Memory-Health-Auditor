"""Materialise a frozen, human-labelled synthetic suite as fair audit groups."""
from __future__ import annotations

import hashlib
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    AuditRunModel, ConversationModel, ExperimentModel, MemoryModel,
    MemoryRelationshipModel, MessageModel, TestCaseModel,
)
from app.schemas.domain import (
    ExperimentStatus, GroundingStatus, MemoryStatus, TargetMemoryMaintenancePolicy,
    TargetMemoryWriterKind, TargetSystemAdapterKind, TestQualityStatus,
    TestSuiteConfiguration, TestSuiteMetadata, TestSuiteMode,
)
from app.schemas.formal_experiment import (
    FormalMatrixCreateRequest, FormalMatrixCreateResponse, FormalMatrixScenario,
)
from app.schemas.research import annotation_fingerprint


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

    VERSION = "synthetic-formal-matrix-v1"

    def create(self, db: Session, request: FormalMatrixCreateRequest) -> FormalMatrixCreateResponse:
        dataset = request.dataset
        dataset_hash = annotation_fingerprint(dataset)
        scenarios: list[FormalMatrixScenario] = []

        for source in dataset.conversations:
            conversation_id = _stable_id("SYN", dataset.dataset_id, dataset.dataset_version, source.conversation_id)
            if db.get(ConversationModel, conversation_id):
                raise HTTPException(
                    409,
                    f"Synthetic scenario {source.conversation_id} was already materialised for this dataset version. "
                    "Use its existing experiment rather than creating a second copy.",
                )

            conversation = ConversationModel(
                id=conversation_id, authorised=True,
                created_at=source.messages[0].timestamp.astimezone(timezone.utc),
            )
            db.add(conversation)
            for sequence, message in enumerate(source.messages):
                db.add(MessageModel(
                    id=_stable_id("MSG", conversation_id, message.message_id),
                    conversation_id=conversation_id, source_message_id=message.message_id,
                    sequence=sequence, role=message.role, content=message.content,
                    timestamp=message.timestamp,
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
                evaluator_model="rule-based-v4", dimensions=dimensions,
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
            for condition in request.conditions:
                run = AuditRunModel(
                    id=_stable_id("RUN", experiment.id, condition.memory_strategy.value),
                    conversation_id=conversation_id, experiment_id=experiment.id,
                    status="CREATED", target_configuration=condition.target_configuration.value,
                    provider=condition.provider.value, model=condition.model,
                    temperature=condition.temperature, random_seed=request.random_seed,
                    test_budget=len(source.gold_tests), prompt_template_version=self.VERSION,
                    pipeline_provider="rule_based", pipeline_model="frozen-human-suite",
                    evaluator_provider="rule_based", evaluator_model="rule-based-v4",
                    memory_strategy=condition.memory_strategy.value,
                    memory_maintenance_policy=TargetMemoryMaintenancePolicy.UPDATE_AWARE_CONSOLIDATION.value,
                    target_memory_capacity=50, target_memory_writer=TargetMemoryWriterKind.RULE_BASED.value,
                    target_memory_writer_version="rule-based-memory-extractor-v1",
                    target_system_adapter=TargetSystemAdapterKind.CONTROLLED_MEMORY.value,
                    target_system_adapter_version="controlled-memory-v1",
                    reproducibility_metadata={
                        "schema_version": "reproducibility-v1", "formal_matrix_version": self.VERSION,
                        "dataset_id": dataset.dataset_id, "dataset_version": dataset.dataset_version,
                        "dataset_fingerprint_sha256": dataset_hash, "pilot_id": request.pilot.pilot_id,
                        "suite_kind": "frozen_human_labelled_synthetic", "condition_label": condition.label,
                        "target_retry_policy": {"max_attempts": 3, "timeout_seconds": 60.0,
                                                  "retryable_status_codes": [408, 409, 425, 429, 500, 502, 503, 504]},
                        "execution_budget": {"max_target_calls": len(source.gold_tests), "max_execution_seconds": 300},
                    },
                )
                db.add(run)
                runs.append(run)
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
                    validation_notes=f"Frozen human-labelled synthetic suite: {gold.quality_note}",
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
            scenarios.append(FormalMatrixScenario(
                source_conversation_id=source.conversation_id, experiment_id=experiment.id,
                run_ids=[run.id for run in runs], test_count=len(source_tests),
            ))

        db.commit()
        return FormalMatrixCreateResponse(
            dataset_id=dataset.dataset_id, dataset_version=dataset.dataset_version,
            dataset_fingerprint_sha256=dataset_hash, pilot_id=request.pilot.pilot_id,
            condition_count=len(request.conditions), scenario_count=len(scenarios),
            total_audit_runs=sum(len(item.run_ids) for item in scenarios),
            total_target_calls=sum(item.test_count * len(item.run_ids) for item in scenarios),
            scenarios=scenarios,
            notice=("Synthetic scenarios were materialised with a frozen human-labelled test suite. "
                    "Runs are pending; execute them explicitly to record target responses and evaluations."),
        )
