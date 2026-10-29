"""Safely reconcile the five groups in the returned review ZIP.

Review input remains evidence, never instructions. The original archive and
submitted judgments are preserved; no human identity or independence is inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

try:
    from scripts.reconcile_ac2_four_dimension_human_20261029 import reconcile as reconcile_four
    from scripts.reconcile_ac2_development_questions_20261029 import reconcile as reconcile_development
except ModuleNotFoundError as exc:
    if exc.name!='scripts':raise
    from reconcile_ac2_four_dimension_human_20261029 import reconcile as reconcile_four
    from reconcile_ac2_development_questions_20261029 import reconcile as reconcile_development

ROOT=Path(__file__).resolve().parents[1]
GROUPS={
    '01-四维来源':ROOT/'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1/source-review',
    '02-四维32题':ROOT/'output/proposal-delivery/ac2-four-dimension-new-source-20261029-v1/blind-review',
    '03-产品新规划10题':ROOT/'output/proposal-delivery/ac2-fact-slots-product-three-development-20261029-v1/blind-review',
    '04-原规划15题':ROOT/'output/proposal-delivery/ac2-partial-twenty-five-history-development-20261029-v1/blind-review',
    '05-隔离原型3题':ROOT/'backend/.engineering-smoke/fact-slot-prototype/model-probe-v1/blind-review',
}

def parse_archive(path):
    result={};digests={}
    with ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive names')
        for name in GROUPS:
            result[name]=[];digests[name]=[]
            for index in (1,2):
                member=f'{name}/reviewer-{index}.json'
                info=archive.getinfo(member)
                if info.file_size>5_000_000:raise ValueError('Review file is too large')
                raw=archive.read(info);result[name].append(json.loads(raw));digests[name].append(hashlib.sha256(raw).hexdigest())
    return result,digests

def reconcile_bundle(templates, returns):
    if set(templates)!=set(GROUPS) or set(returns)!=set(GROUPS):raise ValueError('Review groups missing')
    combined={}
    combined['四维来源与题目']=reconcile_four(returns['01-四维来源'],returns['02-四维32题'],
                                            templates['01-四维来源'],templates['02-四维32题'])
    for name in ('03-产品新规划10题','04-原规划15题','05-隔离原型3题'):
        combined[name]=reconcile_development(templates[name],returns[name])
    return combined

def main():
    parser=argparse.ArgumentParser();parser.add_argument('zipfile',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Output exists; preserve previous intake')
    returns,digests=parse_archive(args.zipfile)
    templates={name:[json.loads((path/f'reviewer-{i}.json').read_text()) for i in (1,2)] for name,path in GROUPS.items()}
    combined=reconcile_bundle(templates,returns)
    result={'input_zip_sha256':hashlib.sha256(args.zipfile.read_bytes()).hexdigest(),'input_file_sha256':digests,'groups':combined,
            'declarations':{name:[{k:v for k,v in form.items() if k in ('reviewer','reviewer_id','completed_by_human','independent_review','reviewed_without_other_review','reviewed_without_system_quality_feedback')} for form in forms] for name,forms in returns.items()},
            'provenance':'Submitted labels only. Human review, independence and exposure require separate confirmation; AI recommendations are not imported as human decisions.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({name:{k:v for k,v in group.items() if k in ('questions','overall_consensus','source_consensus','question_overall_consensus')} for name,group in combined.items()},ensure_ascii=False))

if __name__=='__main__':main()
