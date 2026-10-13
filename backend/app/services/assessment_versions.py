"""Read-only compatibility notices for archived local evidence assessments."""
import re

from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import EvaluationResult


def assessment_version_warnings(evaluations: list[EvaluationResult]) -> list[str]:
    """Report known rule-version differences, without changing saved verdicts.

    This is not a semantic-model, prompt or source-hash equivalence guarantee.
    Missing/third-party version labels cannot establish a matching local rule
    version and are deliberately not guessed or rewritten here.
    """
    installed = RuleBasedBehaviourEvaluator.VERSION
    changed = 0
    for evaluation in evaluations:
        versions = [evaluation.evaluator.removeprefix('fallback-')]
        if evaluation.judge_execution and evaluation.judge_execution.cross_check_version:
            versions.append(evaluation.judge_execution.cross_check_version)
        if any(re.fullmatch(r'rule-based-v\d+', version) and version != installed for version in versions):
            changed += 1
    if not changed:
        return []
    noun = 'assessment' if changed == 1 else 'assessments'
    return [
        f"{changed} saved {noun} used a different version of the evidence rules. "
        "Original scores are preserved. Reassess saved answers checks the same replies "
        "with current rules without a second target call. "
        "A version difference alone does not establish that the saved verdict is wrong."
    ]
