from datetime import datetime, timezone

from app.models.entities import AuditRunModel, ExperimentModel
from app.schemas.domain import (
    Dimension,
    ExperimentCreate,
    ExperimentStatus,
    TestSuiteConfiguration,
    TestSuiteMetadata,
)


def test_experiment_schema_freezes_generation_configuration():
    request = ExperimentCreate(
        conversation_id="C001",
        label="Strategy comparison",
        test_suite_configuration=TestSuiteConfiguration(
            test_budget=20,
            random_seed=7,
            dimensions=[Dimension.FRESHNESS, Dimension.CONFLICT_RESOLUTION],
        ),
    )

    assert request.test_suite_configuration.test_budget == 20
    assert request.test_suite_configuration.random_seed == 7
    assert request.test_suite_configuration.dimensions == [
        Dimension.FRESHNESS,
        Dimension.CONFLICT_RESOLUTION,
    ]
    assert TestSuiteMetadata(
        test_count=2,
        dimensions=request.test_suite_configuration.dimensions,
        generated_at=datetime.now(timezone.utc),
    ).test_count == 2


def test_experiment_and_audit_models_have_referential_shared_suite_contract():
    from app.models.entities import TestCaseModel

    experiment_columns = ExperimentModel.__table__.c
    audit_columns = AuditRunModel.__table__.c

    assert experiment_columns.test_suite_configuration.nullable is False
    assert experiment_columns.test_suite_metadata.nullable is False
    assert experiment_columns.test_suite_source_run_id.nullable is True
    assert audit_columns.experiment_id.nullable is True
    assert TestCaseModel.__table__.c.suite_test_id.nullable is True
    assert {fk.target_fullname for fk in experiment_columns.conversation_id.foreign_keys} == {
        "conversations.id"
    }
    assert {fk.target_fullname for fk in experiment_columns.test_suite_source_run_id.foreign_keys} == {
        "audit_runs.id"
    }
    assert {fk.target_fullname for fk in audit_columns.experiment_id.foreign_keys} == {
        "experiments.id"
    }
    assert {fk.target_fullname for fk in TestCaseModel.__table__.c.suite_test_id.foreign_keys} == {
        "test_cases.id"
    }
    assert ExperimentStatus.TEST_SUITE_GENERATED.value == "TEST_SUITE_GENERATED"


def test_experiment_migration_follows_the_current_schema_head():
    """Keep the migration chain explicit without requiring a live database."""
    from pathlib import Path

    migration = (Path(__file__).parents[1] / "alembic/versions/0006_experiment_groups.py").read_text()
    assert 'down_revision = "0005_memory_strategy"' in migration
    assert 'revision = "0006_experiment_groups"' in migration
    assert 'op.create_table(\n        "experiments"' in migration
    assert '"experiment_id"' in migration
    assert '"suite_test_id"' in migration
