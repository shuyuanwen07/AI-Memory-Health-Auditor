"""Replays synthetic saved scorer JSON; never invokes a provider."""
import hashlib
import json
from unittest.mock import patch
import pytest
from app.services.ac3_paired_scorer_replay import replay_candidate
from app.evaluator.llm_judge import LLMJudgeRequestError
from test_ac3_paired_scorer_input import sample


def replay_inputs(monkeypatch):
    monkeypatch.syspath_prepend('/output/proposal-delivery/ac3-taxonomy-development-tools-2026-10-28')
    from taxonomy_candidate import TaxonomyCandidate
    test,answer,memories,_,_=sample()
    structured={'passed':False,'reason':'Synthetic source differs.',
                'evidence_memory_ids':['M001'],'failure_type':'accuracy',
                'classification_reason':'Synthetic factual mismatch.'}
    data={'model':'openai/gpt-6-luna','choices':[{'finish_reason':'stop','message':{'content':json.dumps(structured)}}]}
    sha=hashlib.sha256(answer.response_text.encode()).hexdigest()
    receipt={'role':'scorer','status':'settled','test_id':'T001','target_answer_sha256':sha,
             'contract_sha256':'a'*64,'response_text':json.dumps(data),'reported_cost_usd':'0.0001'}
    return TaxonomyCandidate('openrouter',model='openai/gpt-6-luna'),test,answer,memories,receipt,sha


def test_replays_saved_judgment_without_network(monkeypatch):
    judge,test,answer,memories,receipt,sha=replay_inputs(monkeypatch)
    with patch('httpx.post') as post:
        result=replay_candidate(judge,test,answer,memories,receipt=receipt,frozen_test_id='T001',answer_sha256=sha)
    post.assert_not_called()
    assert result['provider_only']['verdict']=='fail' and result['provider_only']['failure_type']=='accuracy'
    assert not result['provider_called_during_replay'] and not result['human_truth_evaluated']


def test_rejects_unsettled_mismatched_and_truncated_records(monkeypatch):
    judge,test,answer,memories,receipt,sha=replay_inputs(monkeypatch)
    with pytest.raises(ValueError,match='settled'):
        replay_candidate(judge,test,answer,memories,receipt={**receipt,'status':'pending'},frozen_test_id='T001',answer_sha256=sha)
    with pytest.raises(ValueError,match='settled'):
        replay_candidate(judge,test,answer,memories,receipt={**receipt,'target_answer_sha256':'0'*64},frozen_test_id='T001',answer_sha256=sha)
    data=json.loads(receipt['response_text']);data['choices'][0]['finish_reason']='length'
    with pytest.raises(LLMJudgeRequestError,match='truncated'):
        replay_candidate(judge,test,answer,memories,receipt={**receipt,'response_text':json.dumps(data)},frozen_test_id='T001',answer_sha256=sha)
