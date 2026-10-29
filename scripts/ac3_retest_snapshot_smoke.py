"""Run a synthetic scoring check with provider calls mocked in isolated snapshots.

This is not an experiment or a formal evaluator comparison. No human review,
model response, population accuracy or historical environment is inferred.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from scripts.ac3_retest_snapshot_verify import formal_signature

CHILD = r'''import hashlib,importlib.util,json,sys
from datetime import datetime,timezone
root,kind=sys.argv[1:]
sys.path.insert(0,'/')
from scripts.ac3_retest_shared_environment import verify
verify(json.loads(open(root+'/dependencies.lock.json').read()))
sys.path.insert(0,root)
import httpx
def forbidden(*args,**kwargs): raise AssertionError('Network use forbidden in synthetic smoke check')
httpx.post=forbidden
import app.evaluator.rule_based as rules
assert rules.__file__.startswith(root+'/')
from app.schemas import TestCase,TargetResponse,Memory
test=TestCase(test_id='T1',run_id='R1',dimension='accuracy',prompt='Which day is the meeting?',
 expected_behavior='The meeting is on Tuesday.',supporting_memory_ids=['f1'],generator_version='synthetic')
answer=TargetResponse(response_id='A1',test_id='T1',run_id='R1',response_text='Tuesday',
 model='synthetic',temperature=0,created_at=datetime(2000,1,1,tzinfo=timezone.utc))
memories=[Memory(memory_id='f1',conversation_id='H1',canonical_value='The meeting is on Tuesday.',
 status='confirmed',source_message_ids=['m1'])]
result=rules.RuleBasedBehaviourEvaluator().evaluate(test,answer,memories)
def load_bridge(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module
rule_bridge=load_bridge('synthetic_rule_bridge','/app/app/services/ac3_retest_rule_adapter.py')
normalized=rule_bridge.score_rule(test,answer,memories)
record={'rule_passed':result.passed,'rule_failure_type':result.failure_type.value if result.failure_type else None,
 'normalized_rule':normalized,'answer_sha256':hashlib.sha256(answer.response_text.encode()).hexdigest(), 'model_called':False}
if kind=='candidate':
 sys.path.insert(0,root+'/research')
 from taxonomy_candidate import TaxonomyCandidate
 judge=TaxonomyCandidate('openrouter',model='openai/gpt-6-luna')
 judge._credential=lambda:'synthetic-only'
 judge._openrouter_output_budget=lambda:1024
 judge._judge=lambda *args:{'passed':True,'reason':'Synthetic fixed response',
  'evidence_memory_ids':['f1'],'failure_type':None,'classification_reason':'Synthetic test'}
 candidate,provider=judge.evaluate_with_provider(test,answer,memories)
 bridge=load_bridge('synthetic_taxonomy_bridge','/app/app/services/ac3_retest_taxonomy_adapter.py')
 paired=bridge.adapt_taxonomy(candidate,provider,['f1'])
 record.update(candidate_passed=candidate.passed,provider_fixed_result=provider is not None,
               normalized_hybrid=paired['hybrid'],normalized_provider=paired['provider_only'])
print(json.dumps(record))
'''


def check(base):
    results = {}
    for kind in ('baseline', 'candidate'):
        archive = base / f'paired-{kind}-shared-environment-candidate.zip'
        info = formal_signature(archive)  # Reject unsafe paths before extraction.
        with tempfile.TemporaryDirectory(prefix='ac3-synthetic-snapshot-') as tmp:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(tmp)
            proc = subprocess.run([sys.executable, '-I', '-c', CHILD, tmp, kind],
                                  capture_output=True, text=True, timeout=90)
            if proc.returncode:
                raise RuntimeError(f'{kind} synthetic check failed: {proc.stderr[-1200:]}')
            results[kind] = {'snapshot': info, 'synthetic': json.loads(proc.stdout)}
    if results['baseline']['synthetic']['answer_sha256'] != results['candidate']['synthetic']['answer_sha256']:
        raise ValueError('Synthetic answers differ')
    return {'format':'ac3-snapshot-synthetic-smoke-v1', 'results':results,
            'synthetic_only':True, 'model_called':False, 'formal_evidence':False}


if __name__ == '__main__':
    path=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6')
    print(json.dumps(check(path),ensure_ascii=False))
