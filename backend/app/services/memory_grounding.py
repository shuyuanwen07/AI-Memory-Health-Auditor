"""Separate answer correctness from observable support in actual target input."""
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import EvaluationResult, TargetResponse, TestCase


def annotate_memory_grounding(
    evaluation: EvaluationResult, test: TestCase, response: TargetResponse,
    supplied_values: list[str] | None,
) -> EvaluationResult:
    if not evaluation.passed:
        return evaluation
    receipt = response.execution_metadata.memory_input
    if receipt is None or supplied_values is None:
        note = "Actual supplied-memory support could not be verified; this answer does not establish memory use."
    elif receipt.record_count == 0:
        note = "Correct answer with zero supplied memory: memory grounding is unsupported; human review required."
    else:
        judge = RuleBasedBehaviourEvaluator()
        terms = judge._required_terms(judge._expected_statement(test.expected_behavior))
        # Conflict behavior is an action rather than a factual value. Avoid
        # mistaking absence of the word 'clarification' in memory for a gap.
        if terms == ["conflict", "clarification"]:
            return evaluation
        words = set(judge._words(" ".join(supplied_values)))
        if terms and any(term not in words for term in terms):
            note = "Expected concrete answer absent from supplied memory: correctness is not evidence of memory grounding; human review required."
        else:
            return evaluation  # Presence still does not prove causal reliance.
    if note in evaluation.reason:
        return evaluation
    return evaluation.model_copy(update={"reason": f"{evaluation.reason} {note}"})
