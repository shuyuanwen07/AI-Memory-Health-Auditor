"""Merge 119 reviewed v6 questions with two new reviews of restored H19-Q4.

The exact v5 wording and source evidence are independently rechecked. No
review decision is inferred, and reviewer identities are not authenticated.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ac3_reviewed_fact_map import validate_fact_plan
from scripts.ac3_evidence_paths import resolve_evidence_path
from scripts.import_ac3_expanded_reviews import verify_expanded_manifest, sha, canonical_sha
from scripts.prepare_ac3_h19_restoration import build, encode, TARGET


def verify_h19_user_confirmation(confirmed_raws, original_raws, confirmation_raw):
    """Bind the explicit user correction to originals; preserve all reviewer notes."""
    record=json.loads(confirmation_raw)
    if record.get('format')!='ac3-h19-user-confirmation-v1' or record.get('user_response')!='是，两人独立核对并认可':
        raise ValueError('H19 user confirmation is missing or changed.')
    rows=record.get('files')
    if not isinstance(rows,list) or len(rows)!=2 or {x.get('slot') for x in rows}!={1,2}:
        raise ValueError('H19 confirmation must bind two distinct reviewer slots.')
    by_slot={x['slot']:x for x in rows}
    for slot,(original_raw,confirmed_raw) in enumerate(zip(original_raws,confirmed_raws),1):
        if (by_slot[slot].get('original_sha256')!=sha(original_raw) or
                by_slot[slot].get('confirmed_copy_sha256')!=sha(confirmed_raw)):
            raise ValueError('H19 confirmation hashes do not match original and confirmed copies.')
        a=json.loads(original_raw);b=json.loads(confirmed_raw)
        old_decl=a.pop('reviewer_declaration',{});new_decl=b.pop('reviewer_declaration',{})
        old_review=a.pop('review',{});new_review=b.pop('review',{})
        if (a!=b or old_decl.get('completed_independently') is not None or
                new_decl.get('completed_independently') is not True or
                {k:v for k,v in old_decl.items() if k not in ('completed_independently','note')} !=
                {k:v for k,v in new_decl.items() if k not in ('completed_independently','note')} or
                not isinstance(old_decl.get('note'),str) or not isinstance(new_decl.get('note'),str) or
                not new_decl['note'].startswith(old_decl['note']) or
                old_review.get('question_validity') is not True or new_review.get('question_validity')!='valid' or
                {k:v for k,v in old_review.items() if k!='question_validity'} !=
                {k:v for k,v in new_review.items() if k!='question_validity'}):
            raise ValueError('Confirmed H19 copy changes more than the user-confirmed normalization and independence.')


def convert(v6_source_raw, v6_plan_raw, v6_manifest_path, v6_ground_raws, v6_fact_raws,
            v7_source_raw, restoration_manifest_raw, question_review_raws):
    prior=verify_expanded_manifest(v6_manifest_path,v6_source_raw,v6_ground_raws,v6_fact_raws)
    if prior['fact_plan_sha256']!=canonical_sha(json.loads(v6_plan_raw)):
        raise ValueError('V6 composite does not bind the supplied fact plan.')
    revised, original_raw, sources, before, after, supporting, related=build()
    if original_raw['v6_source']!=v6_source_raw or original_raw['v6_plan']!=v6_plan_raw or encode(revised)!=v7_source_raw:
        raise ValueError('Restored source differs from the exact one-question change.')
    manifest=json.loads(restoration_manifest_raw)
    if (manifest.get('format')!='ac3-h19-restoration-draft-v1' or manifest.get('test_id')!=TARGET or
        manifest.get('changed_fields')!=['question'] or manifest.get('parent_v6_source_sha256')!=sha(v6_source_raw) or
        manifest.get('parent_v6_plan_sha256')!=sha(v6_plan_raw) or manifest.get('revised_source_sha256')!=sha(v7_source_raw)):
        raise ValueError('Restoration manifest does not bind the exact question revision.')
    evidence=manifest.get('evidence')
    if not isinstance(evidence,dict) or set(evidence)!=set(sources):raise ValueError('Restoration evidence is incomplete.')
    for name,path in sources.items():
        if resolve_evidence_path(evidence[name].get('path')) != path.resolve() or evidence[name].get('sha256')!=sha(original_raw[name]):
            raise ValueError('Restoration source evidence differs from the exact saved originals.')
    if len(question_review_raws)!=2:raise ValueError('Two independent single-question reviews are required.')
    names,grounds=[],[]
    for slot,raw in enumerate(question_review_raws,1):
        review=json.loads(raw); declaration=review.get('reviewer_declaration',{}); label=declaration.get('reviewer_label')
        normalized=unicodedata.normalize('NFKC',label).strip().casefold() if isinstance(label,str) else ''
        if (review.get('format')!='ac3-h19-restoration-review-v1' or review.get('reviewer_slot')!=slot or
            review.get('revised_source_sha256')!=sha(v7_source_raw) or review.get('manifest_sha256')!=sha(restoration_manifest_raw) or
            not normalized or declaration.get('completed_by_human') is not True or declaration.get('completed_independently') is not True or
            type(declaration.get('used_ai_assistance')) is not bool):
            raise ValueError('Each restored-question review must be human, independent, and bound to the exact source.')
        names.append(normalized)
        if (review.get('history_id')!='AC3-H19' or review.get('supporting_source_messages')!=supporting or
            review.get('previous_question')!=before or review.get('restored_question')!=after or
            review.get('supporting_facts')!=related[0] or review.get('supporting_relationships')!=related[1]):
            raise ValueError('Reviewer saw different question, source, facts or relationships.')
        decision=review.get('review',{})
        if decision.get('question_validity')!='valid':
            raise ValueError('Restored question invalid, uncertain or unreviewed; retain and resolve it first.')
        comment=decision.get('comment','')
        if not isinstance(comment,str):raise ValueError('Review comment must be text.')
        previous=json.loads(v6_ground_raws[slot-1]); combined=copy.deepcopy(previous)
        combined['input_sha256']=sha(v7_source_raw)
        combined['reviewer_declaration']={'reviewer_label':f'Composite restored slot {slot}',
            'completed_by_human':True,'completed_independently':True,
            'used_ai_assistance':bool(previous['reviewer_declaration']['used_ai_assistance'] or declaration['used_ai_assistance']),
            'note':'119 items inherit their existing per-item reviews; H19-Q4 has its own new independent review. Different rounds need not have the same people; identities and independence are not authenticated.'}
        selected=[q for case in combined['cases'] if case['history_id']=='AC3-H19' for q in case['questions'] if q['test_id']==TARGET]
        if len(selected)!=1:raise ValueError('V6 composite lacks a unique H19-Q4.')
        selected[0].clear();selected[0].update(copy.deepcopy(after));selected[0]['review']={'question_validity':'valid',
            'rationale':comment.strip() or 'Reviewer marked the restored question valid; no separate rationale was supplied.'}
        grounds.append(combined)
    if names[0]==names[1]:raise ValueError('Restored-question reviewer labels must differ.')
    facts=[json.loads(raw) for raw in v6_fact_raws]
    validate_fact_plan(revised,json.loads(v6_plan_raw),facts)
    return grounds,facts


def verify_restored_manifest(manifest_path, source_raw, ground_raws, fact_raws=None):
    path=Path(manifest_path)
    if path.is_symlink() or not path.is_file():raise ValueError('Restored composite manifest must be a regular file.')
    manifest=json.loads(path.read_bytes());entries=manifest.get('inputs')
    valid_formats={'ac3-expanded-restored-composite-review-v1':11,'ac3-expanded-restored-user-confirmed-composite-review-v1':14}
    if manifest.get('format') not in valid_formats or not isinstance(entries,list) or len(entries)!=valid_formats[manifest['format']]:
        raise ValueError('Invalid restored composite manifest.')
    paths=[resolve_evidence_path(x['path']) for x in entries]
    if any(x.is_symlink() or not x.is_file() for x in paths):raise ValueError('Restoration inputs must be regular files.')
    raw=[x.read_bytes() for x in paths]
    if any(sha(x)!=item['sha256'] for x,item in zip(raw,entries)) or raw[7]!=source_raw:
        raise ValueError('Restored composite sources changed.')
    if manifest['format']=='ac3-expanded-restored-user-confirmed-composite-review-v1':
        verify_h19_user_confirmation(raw[9:11],raw[12:14],raw[11])
    grounds,facts=convert(raw[0],raw[1],paths[2],raw[3:5],raw[5:7],raw[7],raw[8],raw[9:11])
    if [json.loads(x) for x in ground_raws]!=grounds or (fact_raws is not None and [json.loads(x) for x in fact_raws]!=facts):
        raise ValueError('Restored declarations differ from reviewed input decisions.')
    if any(path.read_bytes()!=data for path,data in zip(paths,raw)):raise ValueError('Restoration evidence changed during verification.')
    return {'source_sha256':sha(source_raw),'fact_plan_sha256':canonical_sha(json.loads(raw[1])),
            'history_count':30,'question_count':120,'identity_authenticated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('v6-source','v6-plan','v6-manifest','v6-ground-1','v6-ground-2','v6-fact-1','v6-fact-2',
                'v7-source','restoration-manifest','question-review-1','question-review-2','output-dir'):
        p.add_argument('--'+key,required=True,type=Path)
    for key in ('review-confirmation','original-review-1','original-review-2'):
        p.add_argument('--'+key,type=Path)
    a=p.parse_args();paths=[a.v6_source,a.v6_plan,a.v6_manifest,a.v6_ground_1,a.v6_ground_2,a.v6_fact_1,a.v6_fact_2,
                            a.v7_source,a.restoration_manifest,a.question_review_1,a.question_review_2]
    confirmation_paths=[a.review_confirmation,a.original_review_1,a.original_review_2]
    if any(confirmation_paths) and not all(confirmation_paths):raise ValueError('H19 confirmation needs both original review files.')
    if all(confirmation_paths):paths.extend(confirmation_paths)
    if any(x.is_symlink() or not x.is_file() for x in paths):raise ValueError('All inputs must be regular files.')
    raw=[x.read_bytes() for x in paths]
    if all(confirmation_paths):verify_h19_user_confirmation(raw[9:11],raw[12:14],raw[11])
    grounds,facts=convert(raw[0],raw[1],paths[2],raw[3:5],raw[5:7],raw[7],raw[8],raw[9:11])
    if any(p.read_bytes()!=d for p,d in zip(paths,raw)):raise ValueError('Restoration inputs changed during preparation.')
    a.output_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
    for prefix,rows in (('grounding-reviewer',grounds),('fact-reviewer',facts)):
        for slot,row in enumerate(rows,1):
            fd=os.open(a.output_dir/f'{prefix}-{slot}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'w',encoding='utf8') as stream:json.dump(row,stream,ensure_ascii=False,indent=2);stream.write('\n')
    manifest={'format':('ac3-expanded-restored-user-confirmed-composite-review-v1' if all(confirmation_paths)
                        else 'ac3-expanded-restored-composite-review-v1'),
              'inputs':[{'path':str(p.resolve()),'sha256':sha(d)} for p,d in zip(paths,raw)],
              'disclosure':'119 prior per-item reviews plus separately reviewed restored question. Reviewers may differ across rounds; identities are not independently authenticated.',
              'protocol_frozen':False,'model_called':False}
    with (a.output_dir/'manifest.json').open('x',encoding='utf8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(a.output_dir),'history_count':30,'questions':120,'new_question_reviews':2,'protocol_frozen':False}))


if __name__=='__main__':main()
