from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from app.schemas import TargetResponse
from app.target_ai.providers import HttpTargetAIConnector
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from test_openrouter import make_case

@pytest.mark.parametrize('provider,payload', [
    ('ollama', {'done_reason':'length'}),
    ('openrouter', {'choices':[{'finish_reason':'length'}]}),
    ('openai', {'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}}),
    ('gemini', {'candidates':[{'finishReason':'MAX_TOKENS'}]}),
])
def test_provider_preserves_explicit_output_limit(provider, payload):
    from app.schemas import TargetProvider
    metadata = HttpTargetAIConnector._usage(payload, TargetProvider(provider))
    assert metadata['completion_status'] == 'truncated'

@pytest.mark.parametrize('judge', [RuleBasedBehaviourEvaluator(), LLMBehaviourEvaluator('ollama', model='test')])
def test_explicitly_truncated_answer_is_unscored_without_another_model_call(judge, monkeypatch):
    test = make_case().model_copy(update={'expected_behavior':'Use the later record: PostgreSQL.'})
    response = TargetResponse(response_id='R001', test_id=test.test_id, run_id=test.run_id, response_text='Let me think. PostgreSQL is in the records, but', model='test', temperature=0,
        execution_metadata={'completion_status':'truncated','finish_reason':'length'}, created_at=datetime.now(timezone.utc))
    network = Mock(side_effect=AssertionError('must not call judge for known truncated target output'))
    if isinstance(judge, LLMBehaviourEvaluator): monkeypatch.setattr(judge, '_judge', network)
    result = judge.evaluate(test, response, [])
    assert result.passed is None
    assert 'truncated' in result.reason.lower()
    assert result.failure_type is None
    network.assert_not_called()

def test_unknown_legacy_completion_is_not_assumed_truncated():
    response = TargetResponse(response_id='R001', test_id='T001', run_id='RUN1', response_text='PostgreSQL', model='test', temperature=0, created_at=datetime.now(timezone.utc))
    assert response.execution_metadata.completion_status is None
