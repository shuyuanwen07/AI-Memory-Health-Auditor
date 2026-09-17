"""Ephemeral contracts for a de-identified, double-annotated pilot release.

The operational audit database intentionally has no table for these records.
They are supplied as a request, validated, summarised and discarded so that
human research labels stay in the team's approved research storage.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas.domain import Dimension, RelationshipType


class PilotTask(str, Enum):
    MEMORY_INCLUSION = "memory_inclusion"
    RELATIONSHIP_TYPE = "relationship_type"
    TEST_VALIDITY = "test_validity"
    EVALUATOR_VERDICT = "evaluator_verdict"
    FAILURE_DIMENSION = "failure_dimension"


class PilotAdjudicationBasis(str, Enum):
    ADJUDICATED = "adjudicated"
    EXTERNAL_REFERENCE = "external_reference"


class PilotAnnotationMode(str, Enum):
    """Provenance mode for a double-labelling package.

    Only two independent human label sets can satisfy the formal-study gate.
    Synthetic AI-assisted packages remain useful for exercising the workflow,
    but must never be represented as human inter-rater evidence.
    """

    HUMAN_DOUBLE_ANNOTATION = "human_double_annotation"
    AI_ASSISTED_SYNTHETIC_DRY_RUN = "ai_assisted_synthetic_dry_run"


_TASK_LABELS: dict[PilotTask, set[str]] = {
    PilotTask.MEMORY_INCLUSION: {"include", "exclude"},
    PilotTask.RELATIONSHIP_TYPE: {"none", *(item.value for item in RelationshipType)},
    PilotTask.TEST_VALIDITY: {"accept", "reject"},
    PilotTask.EVALUATOR_VERDICT: {"pass", "fail"},
    PilotTask.FAILURE_DIMENSION: {"none", *(item.value for item in Dimension)},
}


class PilotItem(BaseModel):
    """A de-identified annotation unit; it contains no source conversation text."""

    item_id: str = Field(min_length=1)
    task: PilotTask


class PilotLabel(BaseModel):
    item_id: str = Field(min_length=1)
    task: PilotTask
    label: str = Field(min_length=1)

    @model_validator(mode="after")
    def label_is_valid_for_task(self) -> "PilotLabel":
        if self.label not in _TASK_LABELS[self.task]:
            allowed = ", ".join(sorted(_TASK_LABELS[self.task]))
            raise ValueError(f"Invalid {self.task.value} label. Allowed values: {allowed}.")
        return self


class PilotAnnotatorLabels(BaseModel):
    """One independent, pseudonymous annotator's pre-adjudication labels."""

    annotator_id: str = Field(min_length=1)
    labels: list[PilotLabel] = Field(default_factory=list)


class PilotAdjudication(PilotLabel):
    basis: PilotAdjudicationBasis
    decision_note: str = Field(min_length=1)


class PilotAnnotationPackage(BaseModel):
    """Two independent label sets and a separate adjudicated/reference release.

    ``items`` deliberately contains only stable de-identified identifiers and
    task types. Source text and participant data must remain outside this API.
    ``minimum_paired_items_per_task`` and ``minimum_kappa`` make readiness
    criteria explicit instead of silently applying a study-wide threshold.
    """

    pilot_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    created_at: datetime
    authorised_for_research: bool
    data_origin: str = Field(min_length=1)
    deidentification_note: str = Field(min_length=1)
    annotation_mode: PilotAnnotationMode = PilotAnnotationMode.HUMAN_DOUBLE_ANNOTATION
    minimum_paired_items_per_task: int = Field(default=5, ge=1)
    minimum_kappa: float | None = Field(default=0.6, ge=-1, le=1)
    items: list[PilotItem] = Field(min_length=1)
    annotators: list[PilotAnnotatorLabels] = Field(min_length=2, max_length=2)
    adjudications: list[PilotAdjudication] = Field(default_factory=list)

    @model_validator(mode="after")
    def package_is_traceable_and_double_annotated(self) -> "PilotAnnotationPackage":
        if not self.authorised_for_research:
            raise ValueError("Pilot annotation data must be authorised for research.")
        annotator_ids = [annotator.annotator_id for annotator in self.annotators]
        if len(set(annotator_ids)) != 2:
            raise ValueError("Pilot packages require exactly two distinct annotator IDs.")

        item_tasks = {(item.item_id, item.task) for item in self.items}
        if len(item_tasks) != len(self.items):
            raise ValueError("Pilot item IDs must be unique within each task.")
        for annotator in self.annotators:
            keys = [(label.item_id, label.task) for label in annotator.labels]
            if len(keys) != len(set(keys)):
                raise ValueError("An annotator may label each pilot item only once.")
            if not set(keys).issubset(item_tasks):
                raise ValueError("Annotator labels must reference declared pilot items with the same task.")
        adjudication_keys = [(label.item_id, label.task) for label in self.adjudications]
        if len(adjudication_keys) != len(set(adjudication_keys)):
            raise ValueError("Each pilot item may have at most one adjudication/reference label.")
        if not set(adjudication_keys).issubset(item_tasks):
            raise ValueError("Adjudications must reference declared pilot items with the same task.")
        return self


class PilotAnalysisRequest(BaseModel):
    package: PilotAnnotationPackage


class PilotAgreementMetrics(BaseModel):
    task: PilotTask | None = None
    declared_items: int
    annotator_a_labelled: int
    annotator_b_labelled: int
    paired_items: int
    adjudicated_items: int
    agreement_count: int
    disagreement_count: int
    percent_agreement: float | None
    cohens_kappa: float | None
    kappa_applicable: bool
    disagreements_adjudicated: int
    unresolved_disagreements: int


class PilotReadinessReport(BaseModel):
    pilot_id: str
    dataset_id: str
    dataset_version: str
    fingerprint_sha256: str
    annotator_ids: list[str]
    annotation_mode: PilotAnnotationMode = PilotAnnotationMode.HUMAN_DOUBLE_ANNOTATION
    minimum_paired_items_per_task: int
    minimum_kappa: float | None
    overall: PilotAgreementMetrics
    by_task: list[PilotAgreementMetrics]
    ready_for_formal_evaluation: bool
    blocking_reasons: list[str]
    retention: str = "request_scoped_not_persisted"
