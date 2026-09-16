"""Calculate Auditor validity metrics from a frozen human annotation release.

The input deliberately uses explicit human-to-candidate matching.  Semantic
matching of free-text memories is itself an experimental decision; silently
performing it in a metric would make the reported precision/recall misleading.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.annotation import AnnotationDataset, TestQualityLabel
from app.schemas.research import (
    BinaryClassificationMetrics,
    ResearchPredictionSet,
    ResearchValidityReport,
)


def _case(conversation_id: str, local_id: str) -> str:
    return f"{conversation_id}::{local_id}"


@dataclass(frozen=True)
class _Counts:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


def _binary_metrics(predicted_positive: set[str], actual_positive: set[str], universe: set[str]) -> BinaryClassificationMetrics:
    """Create a complete binary report, retaining undefined denominators as null."""
    tp = len(predicted_positive & actual_positive)
    fp = len(predicted_positive - actual_positive)
    fn = len(actual_positive - predicted_positive)
    tn = len(universe - (predicted_positive | actual_positive))
    counts = _Counts(tp, fp, tn, fn)
    total = tp + fp + tn + fn
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 1) if precision is not None and recall is not None and precision + recall else None
    return BinaryClassificationMetrics(
        labelled_cases=total,
        true_positives=counts.true_positives,
        false_positives=counts.false_positives,
        true_negatives=counts.true_negatives,
        false_negatives=counts.false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=_ratio(tp + tn, total),
        false_positive_rate=_ratio(fp, fp + tn),
        cohens_kappa=_kappa(counts),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def _kappa(counts: _Counts) -> float | None:
    total = sum((counts.true_positives, counts.false_positives, counts.true_negatives, counts.false_negatives))
    if not total:
        return None
    observed = (counts.true_positives + counts.true_negatives) / total
    actual_positive = (counts.true_positives + counts.false_negatives) / total
    predicted_positive = (counts.true_positives + counts.false_positives) / total
    expected = actual_positive * predicted_positive + (1 - actual_positive) * (1 - predicted_positive)
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


class ResearchValidityService:
    """Report extraction, relationship, test-review and evaluator validity.

    Positive classes are fixed and exposed in each report: a matched item for
    extraction/relationships, an acceptable test for test review, and a
    detected failure for evaluator validity.
    """

    def calculate(self, dataset: AnnotationDataset, predictions: ResearchPredictionSet) -> ResearchValidityReport:
        if predictions.dataset_id != dataset.dataset_id or predictions.dataset_version != dataset.dataset_version:
            raise ValueError("Prediction set dataset_id and dataset_version must match the annotation dataset.")

        self._validate_references(dataset, predictions)

        gold_memory_keys = {
            _case(conversation.conversation_id, memory.memory_id)
            for conversation in dataset.conversations
            for memory in conversation.gold_memories
        }
        # Candidates without an independently confirmed gold match are false
        # positives; they use their own stable candidate identifier.
        predicted_memory_keys = {
            _case(prediction.conversation_id, prediction.matched_gold_memory_id or f"candidate:{prediction.candidate_id}")
            for prediction in predictions.memory_predictions
        }
        extraction_universe = gold_memory_keys | predicted_memory_keys
        extraction = _binary_metrics(predicted_memory_keys, gold_memory_keys, extraction_universe)

        gold_relationships = {
            _relationship_key(conversation.conversation_id, memory.memory_id, relationship.type.value, relationship.target_memory_id)
            for conversation in dataset.conversations
            for memory in conversation.gold_memories
            for relationship in memory.relationships
        }
        predicted_relationships = {
            _relationship_key(item.conversation_id, item.source_gold_memory_id, item.type.value, item.target_gold_memory_id)
            for item in predictions.relationship_predictions
        }
        relationship = _binary_metrics(predicted_relationships, gold_relationships, gold_relationships | predicted_relationships)

        gold_tests = {
            _case(conversation.conversation_id, test.test_id): test.grounded and test.quality_label == TestQualityLabel.ACCEPT
            for conversation in dataset.conversations
            for test in conversation.gold_tests
        }
        predicted_tests = {_case(item.conversation_id, item.test_id): item.grounded and item.quality_label == TestQualityLabel.ACCEPT for item in predictions.test_assessments}
        test_universe = set(gold_tests) | set(predicted_tests)
        test_validity = _binary_metrics(
            {key for key, value in predicted_tests.items() if value},
            {key for key, value in gold_tests.items() if value},
            test_universe,
        )

        gold_evaluations = {
            _case(conversation.conversation_id, evaluation.response_id): not evaluation.passed
            for conversation in dataset.conversations
            for evaluation in conversation.gold_evaluations
        }
        predicted_evaluations = {_case(item.conversation_id, item.response_id): not item.passed for item in predictions.evaluator_predictions}
        evaluator_universe = set(gold_evaluations) | set(predicted_evaluations)
        evaluator = _binary_metrics(
            {key for key, value in predicted_evaluations.items() if value},
            {key for key, value in gold_evaluations.items() if value},
            evaluator_universe,
        )

        return ResearchValidityReport(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            conversations=len(dataset.conversations),
            extraction=extraction,
            relationship=relationship,
            test_validity=test_validity,
            evaluator=evaluator,
        )

    @staticmethod
    def _validate_references(dataset: AnnotationDataset, predictions: ResearchPredictionSet) -> None:
        """Reject joins that cannot be traced back to the supplied gold release."""
        conversations = {item.conversation_id: item for item in dataset.conversations}
        for item in predictions.memory_predictions:
            conversation = conversations.get(item.conversation_id)
            if conversation is None:
                raise ValueError(f"Unknown annotation conversation: {item.conversation_id}.")
            valid_memories = {memory.memory_id for memory in conversation.gold_memories}
            if item.matched_gold_memory_id is not None and item.matched_gold_memory_id not in valid_memories:
                raise ValueError(f"Unknown gold memory match: {item.matched_gold_memory_id}.")
        for item in predictions.relationship_predictions:
            conversation = conversations.get(item.conversation_id)
            valid_memories = {memory.memory_id for memory in conversation.gold_memories} if conversation else set()
            if not conversation or item.source_gold_memory_id not in valid_memories or item.target_gold_memory_id not in valid_memories:
                raise ValueError("Relationship predictions must reference gold memories in the same conversation.")
        valid_tests = {item.conversation_id: {test.test_id for test in item.gold_tests} for item in dataset.conversations}
        for item in [*predictions.test_assessments, *predictions.evaluator_predictions]:
            if item.test_id not in valid_tests.get(item.conversation_id, set()):
                raise ValueError("Test predictions must reference a gold test in the same conversation.")
        valid_responses = {item.conversation_id: {evaluation.response_id for evaluation in item.gold_evaluations} for item in dataset.conversations}
        for item in predictions.evaluator_predictions:
            if item.response_id not in valid_responses.get(item.conversation_id, set()):
                raise ValueError("Evaluator predictions must reference a gold response in the same conversation.")


def _relationship_key(conversation_id: str, source_id: str, relation_type: str, target_id: str) -> str:
    return f"{conversation_id}::{source_id}::{relation_type}::{target_id}"
