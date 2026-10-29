"""Bind source-only AC1/AC2 references to the existing human-reviewed v6 data.

AC3 question wording is omitted entirely; this preparation does not freeze a
protocol, call a model or create human decisions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
from scripts.ac3_reviewed_fact_map import validate_fact_plan


def sha(raw): return hashlib.sha256(raw).hexdigest()


def prepare(source, fact_plan, manifest, ground_reviews, fact_reviews):
    files=[source,fact_plan,manifest,*ground_reviews,*fact_reviews]
    if any(Path(p).is_symlink() or not Path(p).is_file() for p in files):
        raise ValueError('All review evidence must be regular files')
    raw=[Path(p).read_bytes() for p in files]
    source_raw,plan_raw,manifest_raw=raw[:3]
    verified=verify_expanded_manifest(manifest,source_raw,raw[3:5],raw[5:7])
    suite=json.loads(source_raw); facts=json.loads(plan_raw)
    declared=validate_fact_plan(suite,facts,[json.loads(x) for x in raw[5:7]])
    if declared['fact_plan_sha256'] != verified['fact_plan_sha256']:
        raise ValueError('Reviewed facts differ from the expanded review evidence')
    if any(Path(p).read_bytes()!=data for p,data in zip(files,raw)):
        raise ValueError('Evidence changed during verification')
    histories=[{'history_id':case['history_id'],'source_messages':case['source_messages'],
                'reviewed_reference':facts['histories'][case['history_id']]} for case in suite['cases']]
    return {'format':'ac1-ac2-reviewed-source-v1','status':'source reviewed; protocol not frozen; no outputs collected',
            'scope':'Only source messages and reviewed memory/relationship references; no AC3 questions or target answers.',
            'source_version':'v6','history_count':len(histories),'identity_independently_authenticated':False,
            'review_provenance':'Both independent human reviews are user-reported and AI-assisted; original files and corrections remain preserved.',
            'question_scope_note':'The AC3 H19 question wording is excluded and is not used as AC1/AC2 evidence.',
            'reference_qualifications':[{'history_id':'AC3-H19','fact_id':'AC3-H19-F8','status':'unresolved',
                'reason':'The additional public-library location is not established by the cited source. Preserve the earlier reviewed fact, but do not count it as confirmed gold without independent resolution.'},
                {'history_id':'AC3-H19','relationship_type':'CONTEXTUAL_OVERRIDE',
                'memory_id':'AC3-H19-F8','target_memory_id':'AC3-H19-F7','status':'unresolved',
                'reason':'Offering digital instructions is an option and does not by itself override a paper preference. Preserve this earlier reviewed edge, but do not count it as a confirmed override without independent resolution.'}],
            'inputs':[{'path':str(Path(p).resolve()),'sha256':sha(data)} for p,data in zip(files,raw)],
            'expanded_composite_verification':verified,'histories':histories}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path);p.add_argument('--fact-plan',required=True,type=Path);p.add_argument('--manifest',required=True,type=Path)
    p.add_argument('--ground-review-1',required=True,type=Path);p.add_argument('--ground-review-2',required=True,type=Path)
    p.add_argument('--fact-review-1',required=True,type=Path);p.add_argument('--fact-review-2',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result=prepare(a.source,a.fact_plan,a.manifest,[a.ground_review_1,a.ground_review_2],[a.fact_review_1,a.fact_review_2])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream: json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'histories':result['history_count'],'source_sha256':sha(a.output.read_bytes()),'model_called':False,'protocol_frozen':False}))

if __name__=='__main__':main()
