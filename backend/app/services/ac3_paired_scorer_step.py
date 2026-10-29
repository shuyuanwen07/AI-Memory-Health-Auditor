"""Join label-blind input construction with the single-attempt scorer ledger.

Internal step only: the caller must validate source and runtime snapshot while
holding the matching AC3 sequence lock. A complete coordinator and independently
reviewed budget are still required before any real provider call.
"""
import hashlib
import inspect
import io
import json
from pathlib import Path
import zipfile
from app.services.ac3_locked_preflight import _SEQUENCE
from app.services.ac3_paired_scorer_input import build_scorer_input
from app.services.ac3_paired_scorer_transport import post_once
from app.services.formal_freeze import formal_runtime_signature
from scripts.ac3_retest_paired_freeze import canonical
from scripts.ac3_retest_shared_environment import verify as verify_environment
from scripts.ac3_retest_snapshot_verify import verify_snapshot


def verify_scorer_snapshot(judge,frozen,components):
    """Refuse mismatched source or environment; no provider is contacted."""
    protocol=frozen['protocol'];archive=components['new_evaluator']
    snapshot=protocol['evaluator_snapshots']['new_evaluator']
    verify_snapshot(archive,snapshot['app_source_sha256'],protocol['component_sha256']['new_evaluator'],
                    snapshot['dependencies_lock_sha256'])
    if formal_runtime_signature()['source_sha256']!=snapshot['app_source_sha256']:
        raise ValueError('Running app differs from the frozen scorer snapshot')
    if (type(judge).__name__!='TaxonomyCandidate' or type(judge).__base__.__name__!='BlindSingleAttemptJudge'
            or judge.provider!='openrouter' or judge.model!='openai/gpt-6-luna'):
        raise ValueError('Scorer implementation or model differs from the frozen candidate')
    with zipfile.ZipFile(io.BytesIO(archive)) as saved:
        lock=json.loads(saved.read('dependencies.lock.json'))
        for cls,name in ((type(judge),'research/taxonomy_candidate.py'),(type(judge).__base__,'research/blind_llm_candidate.py')):
            path=Path(inspect.getfile(cls))
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(saved.read(name)).digest():
                raise ValueError('Loaded scorer module differs from the frozen snapshot')
    verify_environment(lock)


def score_once(ledger, *, frozen, components, scope, request_key, frozen_test_id, judge, test, answer,
               memories, question, answer_sha256, model, output_token_limit, headers):
    lock=_SEQUENCE.get()
    if lock is None or lock[0] is not ledger.engine or test.run_id not in lock[1]:
        raise ValueError('The matching AC3 audit sequence lock must be held')
    if hashlib.sha256(canonical(frozen)).hexdigest()!=ledger.frozen_sha256:
        raise ValueError('Scorer study differs from the budget ledger')
    if components!=ledger.components:
        raise ValueError('Scorer components differ from reviewed study evidence')
    scorer=frozen.get('protocol',{}).get('scorer')
    if (not isinstance(scorer,dict) or set(scorer)!={'provider','model','output_token_limit','prompt_version','retry_limit','variant'}
            or scorer['provider']!='openrouter' or scorer['model']!=model or scorer['output_token_limit']!=output_token_limit
            or scorer['retry_limit']!=0 or scorer['prompt_version']!=judge.VERSION_PREFIX+'-structured-v2'
            or scorer['variant'] not in ('hybrid','provider_only')):
        raise ValueError('Scorer configuration was not fixed in the frozen protocol')
    verify_scorer_snapshot(judge,frozen,components)
    prepared=build_scorer_input(judge,test,answer,memories,question,frozen_test_id=frozen_test_id,
        frozen_sha256=ledger.frozen_sha256,answer_sha256=answer_sha256,model=model,output_token_limit=output_token_limit)
    return post_once(ledger,scope=scope,test_id=frozen_test_id,request_key=request_key,
        target_answer_sha256=prepared['target_answer_sha256'],expected_contract=prepared['request_contract'],
        payload=prepared['payload'],headers=headers,output_token_limit=output_token_limit)
