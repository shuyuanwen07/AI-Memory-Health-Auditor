"""Package authorised local C evidence without adding held-out answers to Git."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'artifacts/local/owner-c-delivery'
    out.mkdir(parents=True,exist_ok=True)
    names=[str(p.relative_to(ROOT)) for p in (ROOT/'handoff/owner-c').glob('*') if p.is_file()]
    names += ['scripts/run_owner_c_heldout.py','scripts/compare_owner_c_responses.py',
              'scripts/calculate_owner_c_metrics.py','scripts/package_owner_c_handoff.py',
              'handoff/owner-a-custodian/heldout/source_conversations.json']
    run='artifacts/local/owner-c-heldout-v1/'
    names += [run+n for n in ['configuration.json','freeze_manifest.json','frozen_suite.json','results.json','summary.json',
                              'actual_response_review_1.csv','actual_response_review_2.csv','response_adjudication_final.csv']]
    payloads={name:(ROOT/name).read_bytes() for name in sorted(set(names))}
    manifest={'delivery_id':'owner-c-engineering-handoff-2026-10-05','baseline_commit':'a241e3d28ee58bdd5a66bfd724f8aa02ab315bb9',
              'scope':'Qualified local engineering validation and D handoff; not a completed formal blind-double-annotation study',
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}}
    manifest_bytes=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=out/'owner-c-handoff-2026-10-05.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in [*payloads.items(),('manifest.json',manifest_bytes)]:
            info=zipfile.ZipInfo(name,date_time=(2026,10,5,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(payloads)|{'manifest.json'}
        for name,digest in manifest['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
    (out/'manifest.json').write_bytes(manifest_bytes)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'archive.sha256').write_text(f'{digest}  {archive.name}\n')
    print(json.dumps({'archive':str(archive.relative_to(ROOT)),'included_files':len(payloads),'zip_integrity':'passed','payload_hashes':'passed','archive_sha256':digest},indent=2))

if __name__=='__main__':main()
