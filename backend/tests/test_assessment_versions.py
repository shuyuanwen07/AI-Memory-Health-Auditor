from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import EvaluationResult, JudgeExecutionEvidence
from app.services.assessment_versions import assessment_version_warnings


def assessment(evaluator, cross_check=None):
    return EvaluationResult(evaluation_id='E',test_id='T',response_id='R',passed=True,
        reason='Saved decision.',evidence_memory_ids=[],evaluator=evaluator,
        judge_execution=JudgeExecutionEvidence(provider='openrouter',model='fixture',
            request_attempts=1,failed_http_attempts=0,elapsed_ms=1,
            verdict_status='valid',cross_check_version=cross_check) if cross_check else None)


def test_matching_current_versions_do_not_raise_a_difference_notice():
    version = RuleBasedBehaviourEvaluator.VERSION
    assert assessment_version_warnings([assessment(version),assessment('llm-judge-openrouter-v6',version)]) == []


def test_changed_standalone_fallback_and_semantic_crosscheck_versions_preserve_saved_decisions():
    old = 'rule-based-v1'
    rows = [assessment(old),assessment('fallback-'+old),assessment('llm-judge-openrouter-v6',old)]
    original = [row.model_dump() for row in rows]
    warnings = assessment_version_warnings(rows)
    assert len(warnings) == 1 and warnings[0].startswith('3 saved assessments')
    assert 'without a second target call' in warnings[0]
    assert 'does not establish' in warnings[0]
    assert [row.model_dump() for row in rows] == original


def test_unknown_versions_are_not_invented_and_one_assessment_is_counted_once():
    assert assessment_version_warnings([assessment('third-party'),assessment('rule_based'),assessment('output-completion-v1')]) == []
    warnings = assessment_version_warnings([assessment('rule-based-v1','rule-based-v2')])
    assert warnings[0].startswith('1 saved assessment used')
