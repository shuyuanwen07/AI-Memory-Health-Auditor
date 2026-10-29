"""Isolated development judge; no class label sent and no HTTP retry.

It uses the existing product judge and retains its rule-disagreement abstain
gate. This file has not been integrated into the product.
"""
import re
import httpx

from app.evaluator.llm_judge import LLMBehaviourEvaluator, LLMJudgeRequestError, _JUDGE_METER
from app.target_ai.openrouter import CHAT_COMPLETIONS_URL, completion_error


class BlindSingleAttemptJudge(LLMBehaviourEvaluator):
    VERSION_PREFIX = 'isolated-dimension-blind-llm-judge'

    def _judge_prompt(self, test, response, memories):
        prompt = super()._judge_prompt(test, response, memories)
        dimension_line = f'Test dimension: {test.dimension.value}\n'
        if prompt.count(dimension_line) != 1:
            raise ValueError('Unexpected judge prompt structure; refusing to send.')
        result = prompt.replace(dimension_line, '', 1)
        if re.search(r'^Test dimension:', result, re.M):
            raise ValueError('Unexpected dimension label remains; refusing to send.')
        return result

    @staticmethod
    def _post(url, headers, payload):
        if url != CHAT_COMPLETIONS_URL or payload.get('model') != 'openai/gpt-6-luna' or payload.get('max_tokens') != 1024:
            raise LLMJudgeRequestError('The isolated provider/model/output budget is not configured.')
        meter = _JUDGE_METER.get()
        if meter is not None:
            meter['request_attempts'] += 1
            meter['sampling_control'] = 'fixed' if payload.get('temperature') is not None else 'model_default'
            meter['sent_temperature'] = payload.get('temperature')
        try:
            response = httpx.post(url, headers={'Content-Type':'application/json', **headers}, json=payload, timeout=60.0)
        except httpx.TransportError as exc:
            if meter is not None: meter['failed_http_attempts'] += 1
            raise LLMJudgeRequestError('The single judge request had a transport failure.') from exc
        if not response.is_success:
            if meter is not None: meter['failed_http_attempts'] += 1
            raise LLMJudgeRequestError('The single judge request did not succeed.')
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMJudgeRequestError('The judge returned invalid JSON.') from exc
        if not isinstance(data, dict):
            raise LLMJudgeRequestError('The judge returned an unexpected response.')
        LLMBehaviourEvaluator._record_usage(data, meter, provider='openrouter')
        error = completion_error(data)
        if error:
            if meter is not None: meter.update(error)
            raise LLMJudgeRequestError('The judge reported an unsuccessful completion.')
        return data
