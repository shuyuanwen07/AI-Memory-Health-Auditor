"""Offline old/new scoring over one saved answer and one settled scorer receipt.

The caller must first validate the frozen source and receipt using locked
database reads. Neither this module nor its callees send model requests.
"""
import hashlib
from app.services.ac3_paired_old_scorer import score_old
from app.services.ac3_paired_scorer_replay import replay_candidate
from app.services.ac3_paired_scorer_step import verify_scorer_snapshot
from scripts.ac3_retest_paired_freeze import canonical


def replay_pair(frozen,components,judge,test,answer,memories,question,receipt,*,scope,frozen_test_id):
    scorer=frozen['protocol'].get('scorer') or {}
    if scorer.get('variant') not in ('hybrid','provider_only') or receipt.get('scope_id')!=scope:
        raise ValueError('Frozen scorer variant or receipt scope differs')
    if answer.test_id!=test.test_id or answer.run_id!=test.run_id:
        raise ValueError('Saved answer does not belong to this test')
    answer_sha=hashlib.sha256(answer.response_text.encode()).hexdigest()
    verify_scorer_snapshot(judge,frozen,components)
    old=score_old(frozen,components,test,answer,memories,question,
                  frozen_test_id=frozen_test_id,answer_sha256=answer_sha)
    new=replay_candidate(judge,test,answer,memories,receipt=receipt,frozen_test_id=frozen_test_id,answer_sha256=answer_sha)
    old_sha=hashlib.sha256(components['old_evaluator']).hexdigest()
    new_sha=hashlib.sha256(components['new_evaluator']).hexdigest()
    if (old['evaluator_version_sha256']!=old_sha or old_sha!=frozen['protocol']['component_sha256']['old_evaluator']
            or new_sha!=frozen['protocol']['component_sha256']['new_evaluator'] or old_sha==new_sha):
        raise ValueError('Scorer snapshot digests differ from the frozen protocol')
    def record(version,result):
        return {'test_id':frozen_test_id,'target_answer_sha256':answer_sha,'evaluator_version_sha256':version,
                'verdict':result['verdict'],'failure_type':result.get('failure_type')}
    return {'format':'ac3-paired-single-replay-v1','frozen_sha256':hashlib.sha256(canonical(frozen)).hexdigest(),
            'target_answer_sha256':answer_sha,'old':record(old_sha,old['result']),
            'new':record(new_sha,new[scorer['variant']]),'new_scorer_variant':scorer['variant'],
            'model_called':False,'human_truth_evaluated':False}
