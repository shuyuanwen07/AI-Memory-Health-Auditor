"""Synthetic joined scorer step; no external provider calls."""
from unittest.mock import MagicMock,patch
import hashlib
import pytest
from app.services.ac3_locked_preflight import _SEQUENCE
from app.services.ac3_paired_scorer_step import score_once
from test_ac3_paired_scorer_input import BlindJudge,sample
from scripts.ac3_retest_paired_freeze import canonical


def test_step_requires_lock_and_binds_same_frozen_question_and_answer():
    test,answer,memories,question,config=sample()
    engine=object();frozen={'format':'synthetic','protocol':{'scorer':{'provider':'openrouter',
        'model':config['model'],'output_token_limit':20,'prompt_version':'fixture-structured-v2','retry_limit':0,'variant':'hybrid'}}};components={}
    frozen_sha=hashlib.sha256(canonical(frozen)).hexdigest()
    local_id='AC3'+hashlib.sha256(f"{frozen_sha}|{test.run_id}|{config['frozen_test_id']}".encode()).hexdigest()[:32].upper()
    test=test.model_copy(update={'test_id':local_id});answer=answer.model_copy(update={'test_id':local_id})
    ledger=MagicMock(engine=engine,frozen_sha256=frozen_sha,components=components)
    judge=BlindJudge();judge.VERSION_PREFIX='fixture'
    args=dict(frozen=frozen,components=components,scope='s',request_key='key',frozen_test_id=config['frozen_test_id'],judge=judge,
              test=test,answer=answer,memories=memories,question=question,answer_sha256=config['answer_sha256'],
              model=config['model'],output_token_limit=config['output_token_limit'],headers={})
    with patch('app.services.ac3_paired_scorer_step.post_once',return_value={'status':'settled'}) as send, \
         patch('app.services.ac3_paired_scorer_step.verify_scorer_snapshot'):
        with pytest.raises(ValueError,match='lock'):score_once(ledger,**args)
        send.assert_not_called()
        token=_SEQUENCE.set((engine,frozenset({test.run_id})))
        try:
            with pytest.raises(ValueError,match='not fixed'):
                score_once(ledger,**{**args,'output_token_limit':21})
            send.assert_not_called()
            result=score_once(ledger,**args)
        finally:_SEQUENCE.reset(token)
    assert result['status']=='settled'
    assert send.call_args.kwargs['test_id']==config['frozen_test_id']
    assert send.call_args.kwargs['target_answer_sha256']==config['answer_sha256']
    assert send.call_args.kwargs['expected_contract']['role']=='paired_scorer'
