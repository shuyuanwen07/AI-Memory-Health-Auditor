"""Known incomplete target output must not become an accuracy verdict."""
from app.schemas import EvaluationResult, TargetResponse, TestCase


def incomplete_output_evaluation(test: TestCase, response: TargetResponse, evaluator: str) -> EvaluationResult | None:
    if response.execution_metadata.completion_status != "truncated":
        return None
    return EvaluationResult(
        evaluation_id=f"E{test.test_id[1:]}", test_id=test.test_id, response_id=response.response_id,
        passed=None, failure_type=None,
        reason="Uncertain: the provider reports a truncated target answer at the output limit. Keywords in partial analysis do not establish a completed answer. Excluded from scoring; inspect the saved output and repeat under a declared output budget before comparing models.",
        evidence_memory_ids=[], evaluator=evaluator,
    )
