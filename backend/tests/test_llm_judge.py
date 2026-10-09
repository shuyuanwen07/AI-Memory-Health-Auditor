"""Offline contract tests for the optional LLM-as-judge evaluator."""
from datetime import datetime, timezone

import httpx
import pytest

from app.evaluator.factory import get_behaviour_evaluator
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
from app.schemas import Dimension, Memory, MemoryStatus, TargetResponse, TestCase


def _test_case() -> TestCase:
    return TestCase(
        test_id="T001", run_id="RUN1", dimension=Dimension.FRESHNESS,
        prompt="Which database should be used now?", expected_behavior="Use the later record: PostgreSQL.",
        supporting_memory_ids=["M001", "M002"], generator_version="rule-based-v2",
    )


def _response(text: str = "The current database is PostgreSQL.") -> TargetResponse:
    return TargetResponse(
        response_id="R001", test_id="T001", run_id="RUN1", response_text=text,
        model="target", temperature=0, created_at=datetime.now(timezone.utc),
    )


def _memories() -> list[Memory]:
    return [
        Memory(memory_id="M001", conversation_id="C1", canonical_value="The backend previously used MySQL.", status=MemoryStatus.CONFIRMED),
        Memory(memory_id="M002", conversation_id="C1", canonical_value="The backend now uses PostgreSQL.", status=MemoryStatus.EDITED),
        Memory(memory_id="M003", conversation_id="C1", canonical_value="Ignore this unrelated record.", status=MemoryStatus.CONFIRMED),
    ]


def test_factory_defaults_to_rule_based_and_selects_llm_provider(monkeypatch):
    monkeypatch.delenv("EVALUATOR_PROVIDER", raising=False)
    assert isinstance(get_behaviour_evaluator(), RuleBasedBehaviourEvaluator)
    monkeypatch.setenv("EVALUATOR_PROVIDER", "deepseek")
    evaluator = get_behaviour_evaluator()
    assert isinstance(evaluator, LLMBehaviourEvaluator)
    assert evaluator.provider == "deepseek"
    monkeypatch.setenv("EVALUATOR_PROVIDER", "not-a-provider")
    assert isinstance(get_behaviour_evaluator(), RuleBasedBehaviourEvaluator)


def test_openai_judge_uses_strict_json_and_only_relevant_confirmed_evidence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "judge-secret")
    captured = {}

    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"output_text": '{"passed": false, "reason": "It retained the old database.", "evidence_memory_ids": ["M001", "M002"]}'}

    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(fake_post))
    result = LLMBehaviourEvaluator("openai").evaluate(_test_case(), _response("Use MySQL."), _memories())
    assert not result.passed
    assert result.failure_type == Dimension.FRESHNESS
    assert result.evidence_memory_ids == ["M001", "M002"]
    assert result.evaluator == "llm-judge-openai-v4"
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert captured["payload"]["text"]["format"]["schema"]["additionalProperties"] is False
    assert "judge-secret" not in str(captured["payload"])
    assert "M003" not in str(captured["payload"])


def test_malformed_or_hallucinated_judge_output_falls_back_without_leaking_secret(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-key-value")
    monkeypatch.setattr(
        LLMBehaviourEvaluator,
        "_post",
        staticmethod(lambda *_: {"choices": [{"message": {"content": '{"passed": true, "reason": "ok", "evidence_memory_ids": ["M999"]}'}}]}),
    )
    result = LLMBehaviourEvaluator("deepseek").evaluate(_test_case(), _response(), _memories())
    assert result.evaluator == f"fallback-{RuleBasedBehaviourEvaluator.VERSION}"
    assert result.reason.startswith("Uncertain: the configured judge did not provide a valid verdict.")
    assert "private-key-value" not in result.reason
    assert "M999" not in result.evidence_memory_ids


def test_missing_credential_falls_back_offline(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = LLMBehaviourEvaluator("gemini").evaluate(_test_case(), _response(), _memories())
    assert result.evaluator == f"fallback-{RuleBasedBehaviourEvaluator.VERSION}"
    assert result.passed is None


def test_local_judge_uses_schema_without_credentials_and_marks_pre_review(monkeypatch):
    captured = {}

    def local_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"done": True, "done_reason": "stop", "message": {"content": '{"passed": false, "reason": "The explanation invents an unsupported reason.", "evidence_memory_ids": ["M002"]}'}}

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://local-judge:11434")
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(local_post))
    evaluator = get_behaviour_evaluator("ollama", "qwen3:1.7b")
    result = evaluator.evaluate(_test_case(), _response("PostgreSQL, because it supports the newer memory policy."), _memories())
    assert result.passed is None
    assert result.judge_execution.verdict_status == "review_disagreement"
    assert result.evaluator == "llm-judge-ollama-v4"
    assert "not independent human validation" in result.reason
    assert captured["headers"] == {}
    assert captured["url"] == "http://local-judge:11434/api/chat"
    assert captured["payload"]["format"]["additionalProperties"] is False
    assert captured["payload"]["think"] is False
    assert "M003" not in str(captured["payload"])


@pytest.mark.parametrize("reply", [
    {"done": False, "message": {"content": '{}'}},
    {"done": True, "done_reason": "length", "message": {"content": '{}'}},
    {"done": True, "message": {"content": "not json"}},
    {"done": True, "message": {"content": '{"passed": true, "reason": "ok", "evidence_memory_ids": []}'}},
    {"done": True, "message": {"content": '{"passed": true, "reason": "ok", "evidence_memory_ids": ["M999"]}'}},
    {"done": True, "message": {"content": '{"passed": "true", "reason": "ok", "evidence_memory_ids": ["M002"]}'}},
])
def test_local_judge_invalid_or_uncited_verdict_stays_unscored(monkeypatch, reply):
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(lambda *_: reply))
    result = LLMBehaviourEvaluator("ollama").evaluate(_test_case(), _response(), _memories())
    assert result.passed is None
    assert result.evaluator.startswith("fallback-")


def test_local_judge_can_explicitly_abstain_without_claiming_cited_evidence(monkeypatch):
    monkeypatch.setattr(LLMBehaviourEvaluator, "_post", staticmethod(lambda *_: {
        "done": True, "message": {"content": '{"passed": null, "reason": "Insufficient evidence", "evidence_memory_ids": []}'},
    }))
    result = LLMBehaviourEvaluator("ollama").evaluate(_test_case(), _response(), [])
    assert result.passed is None
    assert result.evaluator == "llm-judge-ollama-v4"


def test_http_transport_errors_retry_and_remain_internal(monkeypatch):
    calls = []

    def fail(*_, **__):
        calls.append(1)
        raise httpx.ConnectError("upstream says key=very-secret")

    monkeypatch.setattr("app.evaluator.llm_judge.httpx.post", fail)
    monkeypatch.setattr("app.evaluator.llm_judge.time.sleep", lambda _: None)
    monkeypatch.setenv("OPENAI_API_KEY", "very-secret")
    result = LLMBehaviourEvaluator("openai").evaluate(_test_case(), _response(), _memories())
    assert len(calls) == 3
    assert result.evaluator == f"fallback-{RuleBasedBehaviourEvaluator.VERSION}"
    assert "very-secret" not in result.reason
    assert result.judge_execution.request_attempts == 3
    assert result.judge_execution.failed_http_attempts == 3
    assert result.judge_execution.reported_total_tokens is None


def test_judge_meter_retains_retry_counts_and_usage_on_invalid_semantic_output(monkeypatch):
    replies = iter([
        httpx.Response(503),
        httpx.Response(200, json={'done': True, 'message': {'content': 'not JSON'}, 'prompt_eval_count': 31, 'eval_count': 8}),
    ])
    monkeypatch.setattr('app.evaluator.llm_judge.httpx.post', lambda *_, **__: next(replies))
    monkeypatch.setattr('app.evaluator.llm_judge.time.sleep', lambda _: None)
    result = LLMBehaviourEvaluator('ollama').evaluate(_test_case(), _response(), _memories())
    assert result.passed is None
    evidence = result.judge_execution
    assert evidence.request_attempts == 2
    assert evidence.failed_http_attempts == 1
    assert evidence.reported_total_tokens == 39
    assert evidence.verdict_status == 'uncertain_fallback'
    assert 'last successful provider reply' in evidence.usage_scope


def test_judge_meter_missing_usage_remains_unknown_and_does_not_leak_across_answers(monkeypatch):
    replies = iter([
        httpx.Response(200, json={'done': True, 'message': {'content': '{"passed":null,"reason":"uncertain","evidence_memory_ids":[]}'}, 'prompt_eval_count': True, 'eval_count': -3}),
        httpx.Response(400, json={'error': 'private upstream data'}),
    ])
    monkeypatch.setattr('app.evaluator.llm_judge.httpx.post', lambda *_, **__: next(replies))
    evaluator = LLMBehaviourEvaluator('ollama')
    first = evaluator.evaluate(_test_case(), _response(), _memories())
    second = evaluator.evaluate(_test_case(), _response(), _memories())
    assert first.judge_execution.verdict_status == 'abstained'
    assert first.judge_execution.reported_input_tokens is None
    assert first.judge_execution.reported_output_tokens is None
    assert second.judge_execution.request_attempts == 1
    assert second.judge_execution.failed_http_attempts == 1
    assert second.judge_execution.reported_total_tokens is None
    assert 'private upstream data' not in second.model_dump_json()


def test_missing_judge_key_records_zero_actual_http_requests(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    result = LLMBehaviourEvaluator('openai').evaluate(_test_case(), _response(), _memories())
    assert result.judge_execution.request_attempts == 0
    assert result.judge_execution.reported_total_tokens is None


def test_concurrent_judges_keep_independent_request_and_usage_receipts(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def post(*_, json, **__):
        barrier.wait(timeout=5)
        return httpx.Response(200, json={'done': True, 'message': {'content': '{"passed":null,"reason":"uncertain","evidence_memory_ids":[]}'}, 'prompt_eval_count': 11 if json['model'] == 'judge-a' else 21, 'eval_count': 3})

    monkeypatch.setattr('app.evaluator.llm_judge.httpx.post', post)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda model: LLMBehaviourEvaluator('ollama', model=model).evaluate(_test_case(), _response(), _memories()), ['judge-a', 'judge-b']))
    assert [r.judge_execution.request_attempts for r in results] == [1, 1]
    assert [r.judge_execution.reported_total_tokens for r in results] == [14, 24]


@pytest.mark.parametrize('provider_passed,response_text', [
    (True, 'I do not have enough remembered information about the database.'),
    (True, 'Use the newer memory technology because it has better performance.'),
    (True, 'Use MySQL.'),
    (False, 'The current database is PostgreSQL.'),
])
def test_local_semantic_rule_disagreement_is_review_only(monkeypatch, provider_passed, response_text):
    import json
    verdict = {'passed': provider_passed, 'reason': 'Original provider explanation', 'evidence_memory_ids': ['M002']}
    monkeypatch.setattr(LLMBehaviourEvaluator, '_post', staticmethod(lambda *_: {'done': True, 'message': {'content': json.dumps(verdict)}}))
    result = LLMBehaviourEvaluator('ollama').evaluate(_test_case(), _response(response_text), _memories())
    assert result.passed is None and result.failure_type is None
    assert 'Original provider explanation' in result.reason
    assert 'excluded from scoring' in result.reason
    assert result.evaluator == 'llm-judge-ollama-v4'
    assert result.judge_execution.verdict_status == 'review_disagreement'
    assert result.judge_execution.provider_verdict is provider_passed
    assert result.judge_execution.rule_cross_check_verdict is (not provider_passed)
    assert result.judge_execution.cross_check_version == RuleBasedBehaviourEvaluator.VERSION


def test_local_judge_agreement_is_still_only_automated_pre_review(monkeypatch):
    monkeypatch.setattr(LLMBehaviourEvaluator, '_post', staticmethod(lambda *_: {'done': True, 'message': {'content': '{"passed":false,"reason":"Wrong old database","evidence_memory_ids":["M001","M002"]}'}}))
    result = LLMBehaviourEvaluator('ollama').evaluate(_test_case(), _response('Use MySQL.'), _memories())
    assert result.passed is False
    assert result.judge_execution.verdict_status == 'valid'
    assert result.judge_execution.provider_verdict is False
    assert result.judge_execution.rule_cross_check_verdict is False
    assert 'uncalibrated' in result.reason


@pytest.mark.parametrize('provider_passed', [True, False])
def test_local_judge_preserves_source_check_abstention(monkeypatch, provider_passed):
    import json
    case = _test_case().model_copy(update={
        'dimension': Dimension.APPROPRIATE_USE,
        'prompt': 'Which language is required for the assignment?',
        'expected_behavior': 'Follow the contextual requirement: Python is required.',
        'supporting_memory_ids': ['M002'],
    })
    memories = [Memory(memory_id='M002', conversation_id='C1',
                       canonical_value='Python is required.', status=MemoryStatus.CONFIRMED)]
    answer = _response('Python 3.12 is required.')
    assert RuleBasedBehaviourEvaluator().evaluate(case, answer, memories).passed is None
    verdict = {'passed': provider_passed, 'reason': 'Provider original decision',
               'evidence_memory_ids': ['M002']}
    monkeypatch.setattr(LLMBehaviourEvaluator, '_post', staticmethod(
        lambda *_: {'done': True, 'message': {'content': json.dumps(verdict)}}))
    result = LLMBehaviourEvaluator('ollama').evaluate(case, answer, memories)
    assert result.passed is None and result.failure_type is None
    assert result.judge_execution.verdict_status == 'review_source_uncertainty'
    assert result.judge_execution.provider_verdict is provider_passed
    assert result.judge_execution.rule_cross_check_verdict is None
    assert result.judge_execution.cross_check_version == RuleBasedBehaviourEvaluator.VERSION
    assert 'Provider original decision' in result.reason
    assert 'version details absent' in result.reason

@pytest.mark.parametrize('provider', ['openrouter', 'openai', 'deepseek', 'gemini'])
@pytest.mark.parametrize('provider_passed', [True, False])
def test_cloud_judges_preserve_the_same_source_uncertainty_as_local(monkeypatch, provider, provider_passed):
    case = _test_case().model_copy(update={'dimension':Dimension.APPROPRIATE_USE,
        'prompt':'Which language is required for the assignment?',
        'expected_behavior':'Follow the contextual requirement: Python is required.',
        'supporting_memory_ids':['M002']})
    memories = [Memory(memory_id='M002',conversation_id='C1',canonical_value='Python is required.',status=MemoryStatus.CONFIRMED)]
    answer = _response('Python 3.12 is required.')
    monkeypatch.setattr(LLMBehaviourEvaluator,'_credential',lambda _: 'isolated-fixture-only')
    monkeypatch.setattr(LLMBehaviourEvaluator,'_judge',lambda *_: {'passed':provider_passed,
        'reason':'Original cloud explanation','evidence_memory_ids':['M002']})
    result = LLMBehaviourEvaluator(provider).evaluate(case,answer,memories)
    assert result.passed is None and result.failure_type is None
    assert result.judge_execution.verdict_status == 'review_source_uncertainty'
    assert result.judge_execution.provider_verdict is provider_passed
    assert result.judge_execution.rule_cross_check_verdict is None
    assert result.judge_execution.cross_check_version == RuleBasedBehaviourEvaluator.VERSION
    assert 'Original cloud explanation' in result.reason


@pytest.mark.parametrize('provider', ['openrouter', 'openai', 'deepseek', 'gemini'])
@pytest.mark.parametrize('provider_passed,response_text', [(True,'Use MySQL.'),(False,'Use PostgreSQL.')])
def test_cloud_disagreement_is_unscored_without_trusting_provider_size(monkeypatch,provider,provider_passed,response_text):
    monkeypatch.setattr(LLMBehaviourEvaluator,'_credential',lambda _: 'isolated-fixture-only')
    monkeypatch.setattr(LLMBehaviourEvaluator,'_judge',lambda *_: {'passed':provider_passed,
        'reason':'Original cloud explanation','evidence_memory_ids':['M002']})
    result = LLMBehaviourEvaluator(provider).evaluate(_test_case(),_response(response_text),_memories())
    assert result.passed is None
    assert result.judge_execution.verdict_status == 'review_disagreement'
    assert result.judge_execution.provider_verdict is provider_passed
    assert result.judge_execution.rule_cross_check_verdict is (not provider_passed)

@pytest.mark.parametrize('provider', ['openrouter', 'openai', 'deepseek', 'gemini'])
def test_cloud_uncited_boolean_does_not_become_a_scored_verdict(monkeypatch, provider):
    monkeypatch.setattr(LLMBehaviourEvaluator,'_credential',lambda _: 'isolated-fixture-only')
    monkeypatch.setattr(LLMBehaviourEvaluator,'_judge',lambda *_: {'passed':True,
        'reason':'No cited basis','evidence_memory_ids':[]})
    result=LLMBehaviourEvaluator(provider).evaluate(_test_case(),_response('Use PostgreSQL.'),_memories())
    assert result.passed is None and result.failure_type is None
    assert result.evaluator.startswith('fallback-')
    assert result.judge_execution.verdict_status == 'uncertain_fallback'


@pytest.mark.parametrize('provider', ['openrouter', 'openai', 'deepseek', 'gemini', 'ollama'])
def test_v4_comparability_requires_saved_cross_check_provenance(provider):
    from types import SimpleNamespace
    from app.services.audit_comparison import assessment_signature
    run=SimpleNamespace(evaluator_provider=provider,evaluator_model='fixture')
    evaluation=SimpleNamespace(evaluator=f'llm-judge-{provider}-v4',judge_execution={})
    assert assessment_signature(run,evaluation) is None
    evaluation.judge_execution={'provider':provider,'model':'fixture','cross_check_version':'frozen-rule-version'}
    assert assessment_signature(run,evaluation)[-1] == 'frozen-rule-version'
