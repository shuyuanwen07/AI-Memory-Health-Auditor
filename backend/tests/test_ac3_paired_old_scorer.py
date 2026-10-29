"""Isolated archived scorer checks; synthetic answer, no model request."""
import hashlib
from pathlib import Path
import pytest
from app.services.ac3_paired_old_scorer import score_old
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_snapshot_verify import formal_signature
from test_ac3_paired_scorer_input import sample


def test_archived_rule_scorer_binds_saved_answer_and_source():
    archive=Path('/output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6/paired-baseline-shared-environment-candidate.zip').read_bytes()
    info=formal_signature(archive)
    frozen={'protocol':{'evaluator_snapshots':{'old_evaluator':{'app_source_sha256':info['app_source_sha256'],
             'dependencies_lock_sha256':info['dependencies_lock_sha256']}},
             'component_sha256':{'old_evaluator':info['archive_sha256']}}}
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    test,answer,memories,question,config=sample()
    local='AC3'+hashlib.sha256(f"{sha}|{test.run_id}|T001".encode()).hexdigest()[:32].upper()
    test=test.model_copy(update={'test_id':local});answer=answer.model_copy(update={'test_id':local})
    result=score_old(frozen,{'old_evaluator':archive},test,answer,memories,question,
                     frozen_test_id='T001',answer_sha256=config['answer_sha256'])
    assert result['result']['verdict'] in ('pass','fail','uncertain')
    assert result['evaluator_version_sha256']==info['archive_sha256'] and not result['model_called']
    with pytest.raises(ValueError,match='frozen question or saved answer'):
        score_old(frozen,{'old_evaluator':archive},test,answer,memories,question,
                  frozen_test_id='T001',answer_sha256='0'*64)
