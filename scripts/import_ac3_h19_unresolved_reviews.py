"""Merge prior 120 question reviews with two H19 fact/edge rechecks.

The disputed edge is excluded from the confirmed fact plan and remains
unresolved, not invalid. Reviewer identities are self-reported.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.ac3_evidence_paths import resolve_evidence_path
from scripts.ac3_reviewed_fact_map import validate_fact_plan
from scripts.import_ac3_expanded_reviews import verify_expanded_manifest,sha,canonical_sha
from scripts.prepare_ac3_h19_unresolved import build,encode


def verify_v8_user_confirmation(confirmed_raws,original_raws,confirmation_raw):
    """Bind user's oral confirmation to preserved AI-assisted draft returns.

    The record calls the source files "blank"; the files actually contain AI
    draft decisions and explanatory notes. Their exact bytes remain retained.
    """
    record=json.loads(confirmation_raw)
    if (record.get('format')!='ac3-h19-fact-edge-user-confirmation-v1' or
        record.get('user_response')!='H19两位人工均确认`fact_validity=valid`、`edge_handling=accept`'):
        raise ValueError('H19 fact/edge user confirmation is missing or changed.')
    rows=record.get('files')
    if not isinstance(rows,list) or len(rows)!=2 or {x.get('slot') for x in rows}!={1,2}:
        raise ValueError('H19 fact/edge confirmation needs two distinct slots.')
    slots={x['slot']:x for x in rows}
    for slot,(original_raw,confirmed_raw) in enumerate(zip(original_raws,confirmed_raws),1):
        if (slots[slot].get('blank_sha256')!=sha(original_raw) or
                slots[slot].get('confirmed_sha256')!=sha(confirmed_raw)):
            raise ValueError('H19 fact/edge confirmation hashes differ from source copies.')
        old=json.loads(original_raw);new=json.loads(confirmed_raw)
        old_decl=old.pop('reviewer_declaration',{});new_decl=new.pop('reviewer_declaration',{})
        old_review=old.pop('review',{});new_review=new.pop('review',{})
        if (old!=new or old_decl.get('completed_by_human') is not False or
            old_decl.get('used_ai_assistance') is not True or new_decl.get('completed_by_human') is not True or
            new_decl.get('completed_independently') is not True or new_decl.get('used_ai_assistance') is not True or
            old_review.get('fact_validity')!='valid' or new_review.get('fact_validity')!='valid' or
            old_review.get('edge_handling')!='accept' or new_review.get('edge_handling')!='accept'):
            raise ValueError('H19 confirmed copy changes content beyond documented user approval.')


def convert(v7_source_raw,v7_plan_raw,v7_manifest_path,v7_ground_raws,v7_fact_raws,
            v8_source_raw,v8_plan_raw,v8_manifest_raw,review_raws):
    prior=verify_expanded_manifest(v7_manifest_path,v7_source_raw,v7_ground_raws,v7_fact_raws)
    if prior['fact_plan_sha256']!=canonical_sha(json.loads(v7_plan_raw)):
        raise ValueError('V7 reviewed evidence does not bind the prior fact plan.')
    source,plan,inputs,paths,case,old_fact,new_fact,removed,q4=build()
    if inputs['source']!=v7_source_raw or inputs['parent_plan']!=v7_plan_raw or v8_source_raw!=v7_source_raw or encode(plan)!=v8_plan_raw:
        raise ValueError('V8 differs from the exact source-faithful projection.')
    manifest=json.loads(v8_manifest_raw)
    if (manifest.get('format')!='ac3-h19-unresolved-revision-v1' or
            manifest.get('source_sha256')!=sha(v8_source_raw) or manifest.get('parent_fact_plan_sha256')!=sha(v7_plan_raw) or
            manifest.get('revised_fact_plan_sha256')!=sha(v8_plan_raw) or manifest.get('changed_history_ids')!=['AC3-H19'] or
            manifest.get('changed_fact_ids')!=['AC3-H19-F8'] or manifest.get('unresolved_edge')!=removed or
            manifest.get('unresolved_edge_status')!='unresolved_not_written_as_confirmed' or
            manifest.get('question_and_source_unchanged') is not True):
        raise ValueError('V8 revision manifest differs from the exact user-directed change.')
    evidence=manifest.get('evidence')
    if not isinstance(evidence,dict) or set(evidence)!=set(paths):raise ValueError('V8 source evidence is incomplete.')
    for name,path in paths.items():
        if resolve_evidence_path(evidence[name].get('path'))!=path.resolve() or evidence[name].get('sha256')!=sha(inputs[name]):
            raise ValueError('V8 evidence differs from preserved source files.')
    if len(review_raws)!=2:raise ValueError('Two independent H19 fact/edge reviews are required.')
    names=[];facts=[]
    for slot,raw in enumerate(review_raws,1):
        review=json.loads(raw);declaration=review.get('reviewer_declaration',{});label=declaration.get('reviewer_label')
        normalized=unicodedata.normalize('NFKC',label).strip().casefold() if isinstance(label,str) else ''
        if (review.get('format')!='ac3-h19-unresolved-review-v1' or review.get('reviewer_slot')!=slot or
            review.get('source_sha256')!=sha(v8_source_raw) or review.get('revised_fact_plan_sha256')!=sha(v8_plan_raw) or
            review.get('manifest_sha256')!=sha(v8_manifest_raw) or not normalized or
            declaration.get('completed_by_human') is not True or declaration.get('completed_independently') is not True or
            type(declaration.get('used_ai_assistance')) is not bool):
            raise ValueError('Each H19 fact/edge review must be human, independent and source-bound.')
        names.append(normalized)
        if (review.get('history_id')!='AC3-H19' or review.get('source_messages')!=case['source_messages'] or
            review.get('question')!=q4 or review.get('previous_fact')!=old_fact or review.get('proposed_fact')!=new_fact or
            review.get('previous_edge')!=removed or review.get('edge_status')!='unresolved_not_written_as_confirmed'):
            raise ValueError('H19 review presents altered source, fact or edge information.')
        decision=review.get('review',{})
        if decision.get('fact_validity')!='valid' or decision.get('edge_handling')!='accept':
            raise ValueError('H19 fact or unresolved edge handling was not accepted; retain and resolve it first.')
        if not isinstance(decision.get('comment',''),str):raise ValueError('Review comment must be text.')
        previous=json.loads(v7_fact_raws[slot-1]); item=copy.deepcopy(previous)
        item.update({'reviewer_label':f'Composite unresolved-edge slot {slot}',
                     'fact_plan_sha256':canonical_sha(plan),
                     'used_ai_assistance':bool(previous.get('used_ai_assistance') or declaration['used_ai_assistance']),
                     'note':'Prior reviewed facts and remaining relations are inherited; the source-faithful H19 fact and unresolved edge exclusion were separately reviewed. The excluded edge is unresolved, not invalid. Reviewers may differ across rounds; identity and independence are not authenticated.',
                     'h19_recheck_source_sha256':sha(raw)})
        facts.append(item)
    if names[0]==names[1]:raise ValueError('H19 fact/edge reviewer labels must differ.')
    validate_fact_plan(source,plan,facts)
    # Question/source bytes do not change. Preserve all prior question review
    # judgments rather than representing these fact rechecks as question reviews.
    grounds=[json.loads(raw) for raw in v7_ground_raws]
    return grounds,facts


def verify_unresolved_manifest(manifest_path,source_raw,ground_raws,fact_raws=None):
    path=Path(manifest_path)
    if path.is_symlink() or not path.is_file():raise ValueError('V8 composite manifest must be a regular file.')
    manifest=json.loads(path.read_bytes());entries=manifest.get('inputs')
    formats={'ac3-expanded-h19-unresolved-composite-review-v1':12,
             'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1':15}
    if manifest.get('format') not in formats or not isinstance(entries,list) or len(entries)!=formats[manifest['format']]:
        raise ValueError('Invalid V8 composite manifest.')
    paths=[resolve_evidence_path(row['path']) for row in entries]
    if any(x.is_symlink() or not x.is_file() for x in paths):raise ValueError('V8 inputs must be regular files.')
    raw=[x.read_bytes() for x in paths]
    if any(sha(x)!=entry['sha256'] for x,entry in zip(raw,entries)) or raw[7]!=source_raw:
        raise ValueError('V8 composite sources changed.')
    if manifest['format']=='ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1':
        verify_v8_user_confirmation(raw[10:12],raw[13:15],raw[12])
    grounds,facts=convert(raw[0],raw[1],paths[2],raw[3:5],raw[5:7],raw[7],raw[8],raw[9],raw[10:12])
    if [json.loads(x) for x in ground_raws]!=grounds or (fact_raws is not None and [json.loads(x) for x in fact_raws]!=facts):
        raise ValueError('V8 declarations differ from reviewed inputs.')
    if any(path.read_bytes()!=data for path,data in zip(paths,raw)):raise ValueError('V8 inputs changed during verification.')
    return {'source_sha256':sha(source_raw),'fact_plan_sha256':canonical_sha(json.loads(raw[8])),
            'history_count':30,'question_count':120,'identity_authenticated':False,'unresolved_edge_count':1}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('v7-source','v7-plan','v7-manifest','v7-ground-1','v7-ground-2','v7-fact-1','v7-fact-2',
                'v8-source','v8-plan','v8-manifest','review-1','review-2','output-dir'):
        p.add_argument('--'+key,required=True,type=Path)
    for key in ('review-confirmation','original-review-1','original-review-2'):
        p.add_argument('--'+key,type=Path)
    a=p.parse_args();paths=[a.v7_source,a.v7_plan,a.v7_manifest,a.v7_ground_1,a.v7_ground_2,a.v7_fact_1,a.v7_fact_2,
        a.v8_source,a.v8_plan,a.v8_manifest,a.review_1,a.review_2]
    confirmation_paths=[a.review_confirmation,a.original_review_1,a.original_review_2]
    if any(confirmation_paths) and not all(confirmation_paths):raise ValueError('H19 user confirmation requires both original AI review files.')
    if all(confirmation_paths):paths.extend(confirmation_paths)
    if any(x.is_symlink() or not x.is_file() for x in paths):raise ValueError('All inputs must be regular files.')
    raw=[x.read_bytes() for x in paths]
    if all(confirmation_paths):verify_v8_user_confirmation(raw[10:12],raw[13:15],raw[12])
    grounds,facts=convert(raw[0],raw[1],paths[2],raw[3:5],raw[5:7],raw[7],raw[8],raw[9],raw[10:12])
    if any(x.read_bytes()!=d for x,d in zip(paths,raw)):raise ValueError('V8 inputs changed during preparation.')
    a.output_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
    for prefix,rows in (('grounding-reviewer',grounds),('fact-reviewer',facts)):
        for slot,row in enumerate(rows,1):
            fd=os.open(a.output_dir/f'{prefix}-{slot}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'w',encoding='utf8') as stream:json.dump(row,stream,ensure_ascii=False,indent=2);stream.write('\n')
    manifest={'format':('ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1' if all(confirmation_paths)
                        else 'ac3-expanded-h19-unresolved-composite-review-v1'),
        'inputs':[{'path':str(x.resolve()),'sha256':sha(d)} for x,d in zip(paths,raw)],
        'unresolved_edge_count':1,'disclosure':'Original H19 edge remains unresolved, not invalid; prior decisions and AI qualifications are preserved. Reviewer identities are not independently authenticated.',
        'protocol_frozen':False,'model_called':False}
    with (a.output_dir/'manifest.json').open('x',encoding='utf8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(a.output_dir),'history_count':30,'questions':120,'unresolved_edge_count':1,'protocol_frozen':False}))


if __name__=='__main__':main()
