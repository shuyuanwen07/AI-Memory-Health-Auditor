"""Scorer input construction tests; no provider or real review calls."""
import hashlib
from datetime import datetime,timezone
import pytest
from app.schemas import Memory,TargetResponse
from app.services.ac3_paired_scorer_input import build_scorer_input
from test_ac3_request_binding import inputs


class BlindJudge:
    def _judge_prompt(self,test,answer,memories):
        return f'{test.prompt} | {answer.response_text} | '+','.join(m.canonical_value for m in memories)
    def _system_instruction(self):return 'Evaluate supplied evidence.'
    def _openai_schema(self,ids):return {'type':'json_schema','name':'fixture','schema':{'type':'object'}}


def sample():
    test,_=inputs();test=test.model_copy(update={'supporting_memory_ids':['M001']})
    answer=TargetResponse(response_id='A001',test_id=test.test_id,run_id=test.run_id,response_text='synthetic answer',
                          model='fixture',temperature=0,created_at=datetime.now(timezone.utc))
    memories=[Memory(memory_id='M001',conversation_id='C001',canonical_value='synthetic evidence',
                     status='confirmed',source_message_ids=['S001'])]
    question={'test_id':'T001','question':test.prompt,'expected_behavior':test.expected_behavior,'supporting_memory_ids':['M001']}
    kwargs={'answer_sha256':hashlib.sha256(answer.response_text.encode()).hexdigest(),
            'model':'openai/gpt-6-luna','output_token_limit':20,'frozen_test_id':'T001','frozen_sha256':'a'*64}
    return test,answer,memories,question,kwargs


def test_builds_private_input_and_binding_without_calling_model():
    test,answer,memories,question,kwargs=sample()
    result=build_scorer_input(BlindJudge(),test,answer,memories,question,**kwargs)
    prompt=result['payload']['messages'][1]['content']
    assert 'synthetic answer' in prompt and 'synthetic evidence' in prompt
    assert test.expected_behavior not in prompt
    assert result['request_contract']['role']=='paired_scorer' and not result['model_called']


def test_rejects_changed_answers_and_private_reference_leak():
    test,answer,memories,question,kwargs=sample()
    with pytest.raises(ValueError,match='saved answer'):
        build_scorer_input(BlindJudge(),test,answer,memories,question,**{**kwargs,'answer_sha256':'0'*64})
    with pytest.raises(ValueError,match='Question'):
        build_scorer_input(BlindJudge(),test,answer,memories,question,**{**kwargs,'frozen_test_id':'another-q'})
    with pytest.raises(ValueError,match='identity'):
        build_scorer_input(BlindJudge(),test,answer,memories,question,**{**kwargs,'frozen_sha256':'b'*64})
    class LeakingJudge(BlindJudge):
        def _judge_prompt(self,test,answer,memories):return super()._judge_prompt(test,answer,memories)+test.expected_behavior
    with pytest.raises(ValueError,match='private labels'):
        build_scorer_input(LeakingJudge(),test,answer,memories,question,**kwargs)


def test_saved_taxonomy_candidate_uses_the_label_blind_builder(monkeypatch):
    monkeypatch.syspath_prepend('/output/proposal-delivery/ac3-taxonomy-development-tools-2026-10-28')
    from taxonomy_candidate import TaxonomyCandidate
    test,answer,memories,question,kwargs=sample()
    result=build_scorer_input(TaxonomyCandidate('openrouter',model='openai/gpt-6-luna'),
                              test,answer,memories,question,**kwargs)
    assert result['request_contract']['model']=='openai/gpt-6-luna'
    assert result['request_contract']['response_format']['present']
    assert not result['model_called']
