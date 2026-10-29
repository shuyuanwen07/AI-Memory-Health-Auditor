"""Score one saved answer using the archived rule evaluator in a child process.

The caller must hold the study locks and verify the frozen inputs and database
binding before invoking this offline helper. It never sends a model request.
"""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from app.schemas import MemoryStatus
from scripts.ac3_retest_paired_freeze import PRIOR_RUNTIME_SHA256, canonical
from scripts.ac3_retest_snapshot_verify import verify_snapshot

CHILD=r'''
import json,sys
root=sys.argv[1];sys.path.insert(0,'/')
from scripts.ac3_retest_shared_environment import verify
verify(json.load(open(root+'/dependencies.lock.json')))
sys.path.insert(0,root)
import httpx
def forbidden(*args,**kwargs):raise RuntimeError('Network disabled for old scorer')
httpx.post=forbidden
from app.schemas import TestCase,TargetResponse,Memory
from app.evaluator.rule_based import RuleBasedBehaviourEvaluator
x=json.load(sys.stdin)
test=TestCase.model_validate(x['test']);answer=TargetResponse.model_validate(x['answer'])
memories=[Memory.model_validate(item) for item in x['memories']]
result=RuleBasedBehaviourEvaluator().evaluate(test,answer,memories)
verdict='uncertain' if result.passed is None else 'pass' if result.passed else 'fail'
classification=result.failure_classification
category=(result.failure_type.value if verdict=='fail' and result.failure_type is not None
          and classification.status=='classified' else None)
print(json.dumps({'verdict':verdict,'failure_type':category,'reason':result.reason,
                  'evidence_memory_ids':result.evidence_memory_ids,
                  'classification_status':classification.status,'evaluator':result.evaluator}))
'''


def score_old(frozen,components,test,answer,memories,question,*,frozen_test_id,answer_sha256):
    sha=hashlib.sha256(canonical(frozen)).hexdigest()
    expected='AC3'+hashlib.sha256(f'{sha}|{test.run_id}|{frozen_test_id}'.encode()).hexdigest()[:32].upper()
    if (not isinstance(question,dict) or question.get('test_id')!=frozen_test_id or test.test_id!=expected
            or question.get('question')!=test.prompt or question.get('expected_behavior')!=test.expected_behavior
            or question.get('supporting_memory_ids')!=test.supporting_memory_ids
            or answer.test_id!=test.test_id or answer.run_id!=test.run_id
            or hashlib.sha256(answer.response_text.encode()).hexdigest()!=answer_sha256):
        raise ValueError('Old scorer inputs differ from the frozen question or saved answer')
    by_id={m.memory_id:m for m in memories}
    if (len(by_id)!=len(memories) or not test.supporting_memory_ids
            or any(i not in by_id or by_id[i].status not in (MemoryStatus.CONFIRMED,MemoryStatus.EDITED) for i in test.supporting_memory_ids)
            or len({m.conversation_id for m in memories})!=1):
        raise ValueError('Reviewed supporting memories are missing or invalid')
    archive=components['old_evaluator'];config=frozen['protocol']
    expected_snapshot=config['evaluator_snapshots']['old_evaluator']
    if expected_snapshot['app_source_sha256']!=PRIOR_RUNTIME_SHA256:
        raise ValueError('Old evaluator does not match the prior formal runtime')
    info=verify_snapshot(archive,expected_snapshot['app_source_sha256'],config['component_sha256']['old_evaluator'],
                         expected_snapshot['dependencies_lock_sha256'])
    payload={'test':test.model_dump(mode='json'),'answer':answer.model_dump(mode='json'),
             'memories':[m.model_dump(mode='json') for m in memories]}
    with tempfile.TemporaryDirectory(prefix='ac3-old-score-') as root:
        with zipfile.ZipFile(io.BytesIO(archive)) as saved:saved.extractall(root)
        proc=subprocess.run([sys.executable,'-I','-c',CHILD,root],input=json.dumps(payload),capture_output=True,text=True,timeout=120)
        if proc.returncode:raise ValueError('Archived scorer failed; no result substituted')
        result=json.loads(proc.stdout)
    if (result.get('verdict') not in ('pass','fail','uncertain')
            or result.get('failure_type') not in (None,'accuracy','freshness','conflict_resolution','appropriate_use')
            or not set(result.get('evidence_memory_ids',[])).issubset(by_id)):
        raise ValueError('Archived scorer returned an invalid result')
    return {'format':'ac3-old-scorer-result-v1','test_id':frozen_test_id,'target_answer_sha256':answer_sha256,
            'evaluator_version_sha256':info['archive_sha256'],'result':result,
            'model_called':False,'human_truth_evaluated':False}
