"""Export paired automatic stability from two independently bound saved runs.

The source and repeat frozen suites must both predate the first target answer.
The result is descriptive and does not claim repeat-answer human accuracy.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ac3_fixed_suite_adapter import compile_mock, mock_reservation_for_suite, sha
from scripts.ac3_stability import summarize


def read_bound(path, expected):
    if path.is_symlink() or not path.is_file(): raise ValueError('Evidence must be a regular non-symlink file.')
    raw=path.read_bytes()
    if sha(raw)!=expected: raise ValueError('Evidence digest mismatch.')
    return json.loads(raw)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('primary-frozen','primary-run','repeat-frozen','repeat-run'):
        p.add_argument('--'+key,required=True,type=Path)
        p.add_argument('--'+key+'-sha256',required=True)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    paths=[a.primary_frozen,a.primary_run,a.repeat_frozen,a.repeat_run]
    digests=[a.primary_frozen_sha256,a.primary_run_sha256,a.repeat_frozen_sha256,a.repeat_run_sha256]
    primary,first,child,second=[read_bound(path,digest) for path,digest in zip(paths,digests)]
    for frozen,path,digest in ((primary,paths[0],digests[0]),(child,paths[2],digests[2])):
        compile_mock(path,digest,mock_reservation_for_suite(frozen))
    if (Path(first.get('frozen_path','')).resolve()!=paths[0].resolve() or
            Path(second.get('frozen_path','')).resolve()!=paths[2].resolve()):
        raise ValueError('Saved run points to a different frozen suite.')
    result=summarize(primary,digests[0],first,digests[1],child,digests[2],second,digests[3])
    if any(sha(path.read_bytes())!=digest for path,digest in zip(paths,digests)):
        raise ValueError('Evidence changed during analysis.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(a.output),'pairs':result['pairs'],
                      'human_reviewed_repeat_answers':False,'provider_call':False}))


if __name__=='__main__':main()
