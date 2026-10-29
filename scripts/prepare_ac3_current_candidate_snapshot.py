"""Archive current app plus unchanged research judge for a prospective AC3 study.

Candidate preparation only: does not freeze a protocol, dispatch or score.
"""
import hashlib
import json
from pathlib import Path
import zipfile
from scripts.ac3_retest_snapshot_verify import formal_signature
from scripts.run_ac1_extraction import source_code_sha


def prepare(destination):
    base=Path('output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6')
    prior=base/'paired-candidate-shared-environment-candidate.zip'
    app=Path('backend/app')
    before=source_code_sha()
    with zipfile.ZipFile(prior) as previous, zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as output:
        for path in sorted(app.rglob('*.py')):
            if path.is_symlink() or not path.is_file():raise ValueError('App source must be regular files')
            output.write(path,'app/'+path.relative_to(app).as_posix())
        for name in ('requirements.txt','dependencies.lock.json','research/taxonomy_candidate.py','research/blind_llm_candidate.py'):
            output.writestr(name,previous.read(name))
    after=source_code_sha();info=formal_signature(destination)
    if before!=after or info['app_source_sha256']!=before:
        raise ValueError('Current app source changed during snapshot')
    with zipfile.ZipFile(prior) as previous,zipfile.ZipFile(destination) as current:
        for name in ('requirements.txt','dependencies.lock.json','research/taxonomy_candidate.py','research/blind_llm_candidate.py'):
            if current.read(name)!=previous.read(name):raise ValueError('Candidate judge or environment changed')
    return {'format':'ac3-current-candidate-snapshot-v1','snapshot':info,
            'previous_candidate_archive_sha256':hashlib.sha256(prior.read_bytes()).hexdigest(),
            'product_source_sha256':before,'product_source_rechecked':True,
            'judge_status':'Unchanged development-only taxonomy judge; not validated or integrated in product.',
            'protocol_frozen':False,'model_called':False,'results_generated':False,
            'limitations':['Installed shared environment must be separately verified; OS and shared libraries are not locked.',
                           'A full-app snapshot changes more than the scorer; do not claim an isolated scorer effect.',
                           'The source audit and billing controls remain prerequisites for any actual run.']}


if __name__=='__main__':
    target=Path('output/proposal-delivery/human-return-2026-10-29-ff607492/ac3-current-candidate.zip')
    result=prepare(target)
    with target.with_suffix('.manifest.json').open('x',encoding='utf8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
