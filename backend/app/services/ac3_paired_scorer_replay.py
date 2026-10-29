"""Replay one settled scorer response without any provider request.

The caller must independently verify the scorer snapshot, frozen source, saved
answer and receipt under the experiment locks. Results are exploratory until
compared with independent human labels.
"""
import hashlib
import json
from unittest.mock import patch
from app.evaluator.llm_judge import LLMBehaviourEvaluator
from app.services.ac3_budget_guard import money
from app.services.ac3_retest_taxonomy_adapter import adapt_taxonomy


def replay_candidate(judge, test, answer, memories, *, receipt, frozen_test_id, answer_sha256):
    if (not isinstance(receipt,dict) or receipt.get('role')!='scorer' or receipt.get('status')!='settled'
            or receipt.get('test_id')!=frozen_test_id or receipt.get('target_answer_sha256')!=answer_sha256
            or hashlib.sha256(answer.response_text.encode()).hexdigest()!=answer_sha256
            or not isinstance(receipt.get('response_text'),str) or not isinstance(receipt.get('contract_sha256'),str)
            or len(receipt['contract_sha256'])!=64 or any(c not in '0123456789abcdef' for c in receipt['contract_sha256'])):
        raise ValueError('A settled scorer receipt bound to this saved answer is required')
    money(receipt.get('reported_cost_usd'))
    data=json.loads(receipt['response_text'])
    if not isinstance(data,dict) or data.get('model')!='openai/gpt-6-luna':
        raise ValueError('Saved scorer response has an unexpected model')
    LLMBehaviourEvaluator._check_openrouter_completion(data)
    if not data.get('choices') or data['choices'][0].get('finish_reason')!='stop':
        raise ValueError('Saved scorer response did not confirm completion')
    structured=LLMBehaviourEvaluator._parse_json(LLMBehaviourEvaluator._deepseek_text(data))
    allowed={m.memory_id for m in memories if m.memory_id in test.supporting_memory_ids}
    LLMBehaviourEvaluator._validated_result(structured,allowed)
    # Replay the exact stored structured output through the original scorer's
    # rule-disagreement gate; no transport or credentials are touched.
    with patch.object(judge,'_credential',return_value=''), \
         patch.object(judge,'_openrouter_output_budget',return_value={'requested_output_token_limit':1}), \
         patch.object(judge,'_judge',return_value=structured):
        result,provider=judge.evaluate_with_provider(test,answer,memories)
    observed=adapt_taxonomy(result,provider,allowed)
    return {'format':'ac3-paired-scorer-replay-v1','test_id':frozen_test_id,
            'target_answer_sha256':answer_sha256,'request_contract_sha256':receipt.get('contract_sha256'),
            'hybrid':observed['hybrid'],'provider_only':observed['provider_only'],
            'provider_called_during_replay':False,'human_truth_evaluated':False}
