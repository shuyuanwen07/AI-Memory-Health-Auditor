"""Request and response contracts for offline research-validity analysis."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.annotation import AnnotationDataset, TestQualityLabel
from app.schemas.domain import RelationshipType


class AnnotationImportRequest(BaseModel):
    """An ephemeral validation request for a versioned annotation release.

    The backend validates the supplied JSON and returns its SHA-256 fingerprint;
    it deliberately does not persist human research data in the audit database.
    """

    dataset: AnnotationDataset


class AnnotationImportReport(BaseModel):
    dataset_id: str
    dataset_version: str
    fingerprint_sha256: str
    conversations: int
    gold_memories: int
    gold_relationships: int
    gold_tests: int
    gold_evaluations: int
    created_at: datetime
    validation_status: str = "valid"


class MemoryPrediction(BaseModel):
    conversation_id: str
    candidate_id: str = Field(min_length=1)
    # Set only after an independent reviewer has matched the proposed memory
    # to one gold memory. A null match is counted as an unmatched candidate.
    matched_gold_memory_id: str | None = None


class RelationshipPrediction(BaseModel):
    conversation_id: str
    source_gold_memory_id: str
    type: RelationshipType
    target_gold_memory_id: str


class TestAssessmentPrediction(BaseModel):
    conversation_id: str
    test_id: str
    grounded: bool
    quality_label: TestQualityLabel


class EvaluatorPrediction(BaseModel):
    conversation_id: str
    response_id: str
    test_id: str
    passed: bool


class ResearchPredictionSet(BaseModel):
    """Machine outputs mapped onto a frozen human label release.

    IDs use the local IDs from ``AnnotationDataset``.  A caller must make an
    explicit human matching decision for memory candidates rather than relying
    on string similarity hidden inside a metric calculation.
    """

    dataset_id: str
    dataset_version: str
    memory_predictions: list[MemoryPrediction] = Field(default_factory=list)
    relationship_predictions: list[RelationshipPrediction] = Field(default_factory=list)
    test_assessments: list[TestAssessmentPrediction] = Field(default_factory=list)
    evaluator_predictions: list[EvaluatorPrediction] = Field(default_factory=list)

    @model_validator(mode="after")
    def prediction_ids_are_unique(self) -> "ResearchPredictionSet":
        for values, label, fields in (
            (self.memory_predictions, "memory candidate", ("conversation_id", "candidate_id")),
            (self.relationship_predictions, "relationship", ("conversation_id", "source_gold_memory_id", "type", "target_gold_memory_id")),
            (self.test_assessments, "test assessment", ("conversation_id", "test_id")),
            (self.evaluator_predictions, "evaluator prediction", ("conversation_id", "response_id")),
        ):
            keys = [tuple(str(getattr(value, field)) for field in fields) for value in values]
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate {label} entries are not allowed.")
        matches = [
            (item.conversation_id, item.matched_gold_memory_id)
            for item in self.memory_predictions
            if item.matched_gold_memory_id is not None
        ]
        if len(matches) != len(set(matches)):
            raise ValueError("One gold memory may be matched to at most one candidate memory.")
        return self


class ResearchValidityRequest(BaseModel):
    dataset: AnnotationDataset
    predictions: ResearchPredictionSet


class BinaryClassificationMetrics(BaseModel):
    """Percentages are 0--100; null denotes an absent denominator."""

    labelled_cases: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None
    accuracy: float | None
    false_positive_rate: float | None
    cohens_kappa: float | None


class ResearchValidityReport(BaseModel):
    dataset_id: str
    dataset_version: str
    conversations: int
    extraction: BinaryClassificationMetrics
    relationship: BinaryClassificationMetrics
    test_validity: BinaryClassificationMetrics
    evaluator: BinaryClassificationMetrics


def annotation_fingerprint(dataset: AnnotationDataset) -> str:
    """Stable content fingerprint for recording the exact frozen label release."""
    canonical = json.dumps(dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def annotation_import_report(dataset: AnnotationDataset) -> AnnotationImportReport:
    return AnnotationImportReport(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        fingerprint_sha256=annotation_fingerprint(dataset),
        conversations=len(dataset.conversations),
        gold_memories=sum(len(item.gold_memories) for item in dataset.conversations),
        gold_relationships=sum(len(memory.relationships) for item in dataset.conversations for memory in item.gold_memories),
        gold_tests=sum(len(item.gold_tests) for item in dataset.conversations),
        gold_evaluations=sum(len(item.gold_evaluations) for item in dataset.conversations),
        created_at=dataset.created_at,
    )
