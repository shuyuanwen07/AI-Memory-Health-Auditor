"""One synthetic answer reused for two archived score observations."""
import hashlib
from unittest.mock import patch
import pytest
from app.services.ac3_paired_replay_pair import replay_pair
from test_ac3_paired_scorer_input import sample,BlindJudge


def test_pair_binds_both_results_to_same_answer_and_fixed_variant():
    test,answer,memories,question,_=sample()
    components={'old_evaluator':b'old','new_evaluator':b'new'}
    old_sha=hashlib.sha256(components['old_evaluator']).hexdigest()
    new_sha=hashlib.sha256(components['new_evaluator']).hexdigest()
    frozen={'protocol':{'scorer':{'variant':'hybrid'},'component_sha256':{'old_evaluator':old_sha,'new_evaluator':new_sha}}}
    receipt={'scope_id':'scope'}
    with patch('app.services.ac3_paired_replay_pair.verify_scorer_snapshot'), \
         patch('app.services.ac3_paired_replay_pair.score_old',return_value={'evaluator_version_sha256':old_sha,
             'result':{'verdict':'fail','failure_type':None}}), \
         patch('app.services.ac3_paired_replay_pair.replay_candidate',return_value={
             'hybrid':{'verdict':'uncertain','failure_type':None},'provider_only':{'verdict':'pass','failure_type':None}}):
        result=replay_pair(frozen,components,BlindJudge(),test,answer,memories,question,receipt,scope='scope',frozen_test_id='T001')
        assert result['old']['target_answer_sha256']==result['new']['target_answer_sha256']
        assert result['new']['verdict']=='uncertain' and not result['model_called']
        with pytest.raises(ValueError,match='scope'):
            replay_pair(frozen,components,BlindJudge(),test,answer,memories,question,receipt,scope='wrong',frozen_test_id='T001')
