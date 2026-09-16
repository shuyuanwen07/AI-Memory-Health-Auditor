"""Portable contracts for the offline human-annotation research dataset.

These models are deliberately separate from the production database models:
annotation data is a versioned research artefact, not user audit data.  They
provide a small, validated common format for measuring extraction,
relationship, test-generation, and evaluator quality.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas.domain import ConversationMessage, Dimension, RelationshipType


class AnnotationTestType(str, Enum):
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    PARAPHRASED = "paraphrased"
    INDIRECT = "indirect"


class TestQualityLabel(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


class GoldRelationship(BaseModel):
    type: RelationshipType
    target_memory_id: str


class GoldMemory(BaseModel):
    memory_id: str
    canonical_value: str = Field(min_length=1)
    source_message_ids: list[str] = Field(min_length=1)
    timestamp: datetime | None = None
    relationships: list[GoldRelationship] = Field(default_factory=list)


class GoldTestCase(BaseModel):
    test_id: str
    dimension: Dimension
    test_type: AnnotationTestType
    prompt: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    supporting_memory_ids: list[str] = Field(min_length=1)
    grounded: bool
    quality_label: TestQualityLabel
    quality_note: str = Field(min_length=1)


class GoldEvaluation(BaseModel):
    response_id: str
    test_id: str
    response_text: str = Field(min_length=1)
    passed: bool
    failure_type: Dimension | None = None
    reason: str = Field(min_length=1)
    evidence_memory_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def failure_matches_verdict(self) -> "GoldEvaluation":
        if self.passed and self.failure_type is not None:
            raise ValueError("A passing evaluation cannot have a failure_type.")
        if not self.passed and self.failure_type is None:
            raise ValueError("A failed evaluation must identify its failure_type.")
        return self


class AnnotationConversation(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage] = Field(min_length=1)
    gold_memories: list[GoldMemory] = Field(min_length=1)
    gold_tests: list[GoldTestCase] = Field(min_length=1)
    gold_evaluations: list[GoldEvaluation] = Field(min_length=1)

    @model_validator(mode="after")
    def references_are_traceable(self) -> "AnnotationConversation":
        message_ids = {message.message_id for message in self.messages}
        memory_ids = {memory.memory_id for memory in self.gold_memories}
        test_ids = {test.test_id for test in self.gold_tests}
        if len(message_ids) != len(self.messages) or len(memory_ids) != len(self.gold_memories):
            raise ValueError("Message and memory IDs must be unique within a conversation.")
        if len(test_ids) != len(self.gold_tests):
            raise ValueError("Test IDs must be unique within a conversation.")
        response_ids = {evaluation.response_id for evaluation in self.gold_evaluations}
        if len(response_ids) != len(self.gold_evaluations):
            raise ValueError("Evaluation response IDs must be unique within a conversation.")
        for memory in self.gold_memories:
            unknown_sources = set(memory.source_message_ids) - message_ids
            unknown_targets = {link.target_memory_id for link in memory.relationships} - memory_ids
            if unknown_sources or unknown_targets:
                raise ValueError("Gold memory references must stay inside its conversation.")
        for test in self.gold_tests:
            if not set(test.supporting_memory_ids).issubset(memory_ids):
                raise ValueError("Gold test evidence must reference known gold memories.")
        for evaluation in self.gold_evaluations:
            if evaluation.test_id not in test_ids or not set(evaluation.evidence_memory_ids).issubset(memory_ids):
                raise ValueError("Gold evaluation must reference known tests and evidence memories.")
        return self


class AnnotationDataset(BaseModel):
    """A releaseable dataset with an explicit authorisation and provenance record."""
    dataset_id: str
    dataset_version: str
    created_at: datetime
    authorised_for_research: bool
    data_origin: str = Field(min_length=1)
    deidentification_note: str = Field(min_length=1)
    conversations: list[AnnotationConversation] = Field(min_length=1)

    @model_validator(mode="after")
    def requires_authorisation_and_unique_conversations(self) -> "AnnotationDataset":
        if not self.authorised_for_research:
            raise ValueError("Research annotation data must be authorised.")
        ids = [conversation.conversation_id for conversation in self.conversations]
        if len(ids) != len(set(ids)):
            raise ValueError("Conversation IDs must be unique in an annotation dataset.")
        return self
