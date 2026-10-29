"""Load one candidate snapshot in a separate process; no network calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from scripts.ac3_retest_snapshot_verify import formal_signature

CHILD=r'''
import json,sys
sys.path.insert(0,'/')
sys.path.insert(0,sys.argv[1])
sys.path.insert(0,sys.argv[1]+'/research')
from taxonomy_candidate import TaxonomyCandidate
from app.services.ac3_paired_scorer_step import verify_scorer_snapshot
archive=open(sys.argv[2],'rb').read(); info=json.loads(sys.argv[3])
protocol={'component_sha256':{'new_evaluator':info['archive_sha256']},
          'evaluator_snapshots':{'new_evaluator':{'app_source_sha256':info['app_source_sha256'],
              'dependencies_lock_sha256':info['dependencies_lock_sha256']}}}
verify_scorer_snapshot(TaxonomyCandidate('openrouter',model='openai/gpt-6-luna'),
                       {'protocol':protocol},{'new_evaluator':archive})
print('verified')
'''


def verify(path):
    info=formal_signature(path)
    with tempfile.TemporaryDirectory(prefix='ac3-loaded-scorer-') as directory:
        with zipfile.ZipFile(path) as bundle:bundle.extractall(directory)
        proc=subprocess.run([sys.executable,'-I','-c',CHILD,directory,str(path),json.dumps(info)],
                            capture_output=True,text=True,timeout=120)
        if proc.returncode or proc.stdout.strip()!='verified':
            raise RuntimeError('Isolated scorer verification failed: '+proc.stderr[-1500:])
    return {'format':'ac3-loaded-scorer-verification-v1','snapshot':info,
            'synthetic_only':True,'model_called':False,'protocol_frozen':False,
            'limitations':['Verifies current process dependencies and saved source, not OS/shared libraries or real provider behavior.']}


if __name__=='__main__':
    target=Path('/output/proposal-delivery/human-return-2026-10-29-ff607492/ac3-current-candidate-v2.zip')
    print(json.dumps(verify(target)))
