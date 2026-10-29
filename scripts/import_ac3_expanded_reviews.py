"""Combine source-bound prior and new human reviews without inventing labels.

Old eight histories retain their verified v3 item-level evidence; the new 22
must each receive two independent human reviews of questions, facts and
relations.  Composite slots do not assert that reviewers in the two rounds
are the same people or that reviewer identities were independently verified.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.import_ac3_conflict_delta_reviews import verify_manifest as verify_prior
from scripts.ac3_reviewed_fact_map import validate_fact_plan
from scripts.ac3_evidence_paths import resolve_evidence_path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def _reviewer_label(document, slot):
    if document.get('format') != 'ac3-expanded-human-grounding-review-v1' or document.get('reviewer_slot') != slot:
        raise ValueError('New review format or reviewer slot differs from the expected packet.')
    declaration = document.get('reviewer_declaration', {})
    label = declaration.get('reviewer_label')
    normalized = unicodedata.normalize('NFKC', label).strip().casefold() if isinstance(label, str) else ''
    if (not normalized or declaration.get('completed_by_human') is not True or
            declaration.get('completed_independently') is not True or
            type(declaration.get('used_ai_assistance')) is not bool):
        raise ValueError('Both new reviews need explicit human, independent and AI-assistance declarations.')
    return normalized


def verify_parent_user_confirmation(parent_source_raw, parent_plan_raw, confirmed_raws, original_raws, confirmation_raw):
    """Bind user-reported independence to the unmodified source review files."""
    record=json.loads(confirmation_raw)
    if (record.get('format')!='ac3-expanded-v5-user-confirmation-v1' or
            record.get('user_response')!='是，两人已独立核对' or record.get('originals_modified') is not False):
        raise ValueError('Parent user confirmation is missing or does not preserve original files.')
    files=record.get('files')
    if not isinstance(files,list) or len({x.get('name') for x in files})!=len(files):
        raise ValueError('Parent confirmation file list is missing or duplicated.')
    hashes={x['name']:x['sha256'] for x in files}
    expected={'candidate-inputs.json':sha(parent_source_raw),'proposed-fact-plan.json':sha(parent_plan_raw),
              **{f'reviewer-{i}.json':sha(original_raws[i-1]) for i in (1,2)}}
    if any(hashes.get(name)!=digest for name,digest in expected.items()):
        raise ValueError('Parent confirmation does not bind the reviewed source, plan and original reviews.')
    for original_raw,confirmed_raw in zip(original_raws,confirmed_raws):
        original=json.loads(original_raw);confirmed=json.loads(confirmed_raw)
        a=copy.deepcopy(original);b=copy.deepcopy(confirmed)
        old=a.pop('reviewer_declaration',{});new=b.pop('reviewer_declaration',{})
        if (a!=b or old.get('completed_independently') is not None or new.get('completed_independently') is not True or
                {k:v for k,v in old.items() if k not in ('completed_independently','note')} !=
                {k:v for k,v in new.items() if k not in ('completed_independently','note')} or
                not isinstance(old.get('note'),str) or not isinstance(new.get('note'),str) or
                not new['note'].startswith(old['note'])):
            raise ValueError('Confirmed parent review changes more than the user-confirmed independence declaration.')


def verify_revision_user_confirmation(confirmed_raws, original_raws, confirmation_raw):
    """Bind a v6 user confirmation to its original, AI-assisted returns."""
    record=json.loads(confirmation_raw)
    if (record.get('format')!='ac3-expanded-v6-user-confirmation-v1' or
            record.get('user_response')!='是，v6 两人已独立核对通过' or record.get('originals_modified') is not False):
        raise ValueError('Revision user confirmation is missing or does not preserve originals.')
    files=record.get('files')
    if not isinstance(files,list): raise ValueError('Revision confirmation source list is missing.')
    entries={(row.get('version'),row.get('slot')):row.get('sha256') for row in files}
    if len(entries)!=len(files) or any(entries.get(('v6',i))!=sha(original_raws[i-1]) for i in (1,2)):
        raise ValueError('Revision confirmation does not bind both original returns.')
    for original_raw,confirmed_raw in zip(original_raws,confirmed_raws):
        a=json.loads(original_raw);b=json.loads(confirmed_raw)
        old=a.pop('reviewer_declaration',{});new=b.pop('reviewer_declaration',{})
        if (a!=b or old.get('completed_independently') is not None or new.get('completed_independently') is not True or
                {k:v for k,v in old.items() if k not in ('completed_independently','note')} !=
                {k:v for k,v in new.items() if k not in ('completed_independently','note')} or
                not isinstance(old.get('note'),str) or not isinstance(new.get('note'),str) or
                not new['note'].startswith(old['note'])):
            raise ValueError('Confirmed revision changes more than the user-confirmed independence declaration.')


def merge_revision_reviews(parent_source_raw, parent_plan_raw, revised_source_raw, revised_plan_raw,
                           revision_manifest_raw, parent_review_raws, revision_review_raws,
                           revision_base_source_raw=None, revision_base_plan_raw=None):
    """Use prior review only for byte-equivalent histories and plans.

    Changed histories require complete new item-level review. The number of
    changed histories is derived from the data, not hardcoded. This routine
    does not assert that different rounds had the same human reviewers.
    """
    if (revision_base_source_raw is None) != (revision_base_plan_raw is None):
        raise ValueError('Both exact revision-base source and plan are required together.')
    base_source_raw = revision_base_source_raw if revision_base_source_raw is not None else parent_source_raw
    base_plan_raw = revision_base_plan_raw if revision_base_plan_raw is not None else parent_plan_raw
    parent, base, revised = json.loads(parent_source_raw), json.loads(base_source_raw), json.loads(revised_source_raw)
    prior_plan, base_plan, plan, manifest = (json.loads(parent_plan_raw), json.loads(base_plan_raw),
                                              json.loads(revised_plan_raw), json.loads(revision_manifest_raw))
    if (manifest.get('format') != 'ac3-expanded-repair-manifest-v1' or
            manifest.get('parent_source_sha256') != sha(base_source_raw) or
            manifest.get('parent_fact_plan_sha256') != sha(base_plan_raw) or
            manifest.get('revised_source_sha256') != sha(revised_source_raw) or
            manifest.get('revised_fact_plan_sha256') != sha(revised_plan_raw)):
        raise ValueError('Revision manifest does not bind both exact source and plan versions.')
    before, after = base.get('cases', []), revised.get('cases', [])
    if len(before) != 30 or len(after) != 30 or before[:8] != after[:8]:
        raise ValueError('Revision must preserve the original eight and exactly 30 histories.')
    if [c.get('history_id') for c in before] != [c.get('history_id') for c in after]:
        raise ValueError('Revision changes history identity or ordering.')
    if (set(prior_plan.get('histories', {})) != set(plan.get('histories', {})) or
            set(base_plan.get('histories', {})) != set(plan.get('histories', {}))):
        raise ValueError('Revision changes the set of reviewed fact-plan histories.')
    changed = {new['history_id'] for old,new in zip(before,after) if old != new or
               base_plan['histories'].get(new['history_id']) != plan['histories'].get(new['history_id'])}
    declared = manifest.get('changed_history_ids')
    if (not isinstance(declared, list) or len(set(declared)) != len(declared) or
            set(declared) != changed or not changed or changed & {c['history_id'] for c in before[:8]}):
        raise ValueError('Declared changed histories do not equal the actual changed histories.')
    parent_cases = parent.get('cases', [])
    if len(parent_cases) != 30 or [c.get('history_id') for c in parent_cases] != [c.get('history_id') for c in before]:
        raise ValueError('The actually reviewed parent has a different history set or order.')
    if any((reviewed != original or prior_plan['histories'][original['history_id']] != base_plan['histories'][original['history_id']])
           for reviewed,original in zip(parent_cases,before) if original['history_id'] not in changed):
        raise ValueError('An inherited history differs between the reviewed parent and exact revision base.')
    parents, revisions = [json.loads(x) for x in parent_review_raws], [json.loads(x) for x in revision_review_raws]
    if len(parents) != 2 or len(revisions) != 2:
        raise ValueError('Both parent reviews and both independent revision reviews are required.')
    for group in (parents, revisions):
        names = [_reviewer_label(review, slot) for slot,review in enumerate(group, 1)]
        if names[0] == names[1]: raise ValueError('Each review round requires two distinct reviewer labels.')
    output = []
    parent_sha, base_sha, revised_sha, plan_sha = sha(parent_source_raw), sha(base_source_raw), sha(revised_source_raw), canonical_sha(plan)
    revision_sha = sha(revision_manifest_raw)
    for slot, (original, delta) in enumerate(zip(parents, revisions), 1):
        if (original.get('expanded_source_sha256') != parent_sha or
                original.get('fact_plan_sha256') != canonical_sha(prior_plan) or
                delta.get('expanded_source_sha256') != revised_sha or delta.get('fact_plan_sha256') != plan_sha or
                delta.get('parent_source_sha256') != base_sha or delta.get('revision_manifest_sha256') != revision_sha):
            raise ValueError('Parent or revision review does not bind its exact source and plan.')
        old_cases = original.get('cases'); new_cases = delta.get('cases')
        if not isinstance(old_cases, list) or not isinstance(new_cases, list): raise ValueError('Review case lists are required.')
        old_by_id = {case.get('history_id'):case for case in old_cases}
        new_by_id = {case.get('history_id'):case for case in new_cases}
        expected_new = {case['history_id'] for case in before[8:]}
        if (len(old_cases) != 22 or len(old_by_id) != 22 or set(old_by_id) != expected_new or
                len(new_cases) != len(changed) or len(new_by_id) != len(changed) or set(new_by_id) != changed):
            raise ValueError('Parent or revision reviews omit, duplicate or add history decisions.')
        declaration = {'reviewer_label':f'Composite new-history slot {slot}', 'completed_by_human':True,
            'completed_independently':True,
            'used_ai_assistance':bool(original['reviewer_declaration']['used_ai_assistance'] or
                                      delta['reviewer_declaration']['used_ai_assistance']),
            'note':'Per-item composition of parent and revised reviews. The same reviewer across rounds is not asserted; identity and independence are not authenticated.'}
        output.append({'format':'ac3-expanded-human-grounding-review-v1','reviewer_slot':slot,
                       'expanded_source_sha256':revised_sha,'fact_plan_sha256':plan_sha,
                       'reviewer_declaration':declaration,
                       'cases':[copy.deepcopy(new_by_id[c['history_id']] if c['history_id'] in changed
                                             else old_by_id[c['history_id']]) for c in after[8:]]})
    return output


def convert(old_source_raw, old_plan_raw, prior_manifest, old_ground_raws, old_fact_raws,
            expanded_source_raw, expanded_plan_raw, new_review_raws):
    prior = verify_prior(prior_manifest, old_source_raw, old_ground_raws, old_fact_raws)
    old, source = json.loads(old_source_raw), json.loads(expanded_source_raw)
    old_plan, plan = json.loads(old_plan_raw), json.loads(expanded_plan_raw)
    if prior['source_sha256'] != sha(old_source_raw) or prior['fact_plan_sha256'] != canonical_sha(old_plan):
        raise ValueError('Prior review evidence does not bind the exact old source and fact plan.')
    cases, previous = source.get('cases', []), old.get('cases', [])
    if (source.get('format') != 'ac3-prospective-synthetic-inputs-v1' or len(previous) != 8 or
            len(cases) != 30 or cases[:8] != previous):
        raise ValueError('Expanded source must preserve the eight reviewed histories and add 22.')
    history_ids = [case.get('history_id') for case in cases]
    test_ids = [test.get('test_id') for case in cases for test in case.get('tests', [])]
    if len(set(history_ids)) != 30 or len(test_ids) != 120 or len(set(test_ids)) != 120:
        raise ValueError('Expanded histories and questions must be unique and complete.')
    if set(plan.get('histories', {})) != set(history_ids) or any(
            plan['histories'].get(case['history_id']) != old_plan['histories'].get(case['history_id']) for case in previous):
        raise ValueError('Expanded fact plan must preserve the eight previously reviewed plans.')
    source_sha, plan_sha = sha(expanded_source_raw), canonical_sha(plan)
    if len(new_review_raws) != 2:
        raise ValueError('Two separate new reviews are required.')
    new_reviews = [json.loads(raw) for raw in new_review_raws]
    labels = [_reviewer_label(review, i) for i, review in enumerate(new_reviews, 1)]
    if labels[0] == labels[1]:
        raise ValueError('New reviewer labels must be distinct.')
    new_cases = {case['history_id']: case for case in cases[8:]}
    grounds, facts = [], []
    for slot, review in enumerate(new_reviews, 1):
        if review.get('expanded_source_sha256') != source_sha or review.get('fact_plan_sha256') != plan_sha:
            raise ValueError('New review does not bind the exact expanded source and fact plan.')
        reviewed_cases = review.get('cases')
        if not isinstance(reviewed_cases, list) or len(reviewed_cases) != 22:
            raise ValueError('New review must cover all 22 added histories.')
        by_id = {case.get('history_id'): case for case in reviewed_cases}
        if len(by_id) != 22 or set(by_id) != set(new_cases):
            raise ValueError('New review history identities differ from the new source.')
        old_ground = json.loads(old_ground_raws[slot - 1])
        old_fact = json.loads(old_fact_raws[slot - 1])
        combined_cases = copy.deepcopy(old_ground['cases'])
        for source_case in cases[8:]:
            hid = source_case['history_id']; reviewed = by_id[hid]; section = plan['histories'][hid]
            if reviewed.get('source_messages') != source_case.get('source_messages') or reviewed.get('proposed_facts') != section.get('facts'):
                raise ValueError('New review source or facts differ from the proposed material.')
            questions = reviewed.get('questions')
            if not isinstance(questions, list) or len(questions) != len(source_case['tests']):
                raise ValueError('New review question list is incomplete.')
            reviewed_questions = []
            for q, expected in zip(questions, source_case['tests']):
                if {key:value for key,value in q.items() if key != 'review'} != expected:
                    raise ValueError('New review question or supporting sources changed.')
                decision = q.get('review', {})
                if decision.get('question_validity') != 'valid':
                    raise ValueError('New question invalid, uncertain or unreviewed; retain and resolve before merging.')
                comment = decision.get('comment', '')
                if not isinstance(comment, str): raise ValueError('Question comment must be text.')
                reviewed_questions.append({**copy.deepcopy(expected), 'review': {'question_validity':'valid',
                    'rationale':comment.strip() or 'Reviewer marked this question valid; no separate rationale was supplied.'}})
            fact_review = reviewed.get('fact_review', {})
            if fact_review.get('decision') != 'accept' or reviewed.get('additional_source_facts_missing') != []:
                raise ValueError('New facts were not accepted or potentially missing facts remain.')
            relations = reviewed.get('relationship_checks')
            if not isinstance(relations, list) or len(relations) != len(section['relationships']):
                raise ValueError('New relationship review is incomplete.')
            for edge, expected in zip(relations, section['relationships']):
                if {key:value for key,value in edge.items() if key != 'review'} != expected:
                    raise ValueError('Reviewed relationship differs from the fact plan.')
                if edge.get('review', {}).get('decision') != 'valid':
                    raise ValueError('New relationship invalid, uncertain or unreviewed; retain and resolve before merging.')
            combined_cases.append({'history_id':hid, 'source_messages':copy.deepcopy(source_case['source_messages']),
                                   'questions':reviewed_questions})
        label = f'Composite slot {slot}: previously reviewed histories and new independently reviewed histories'
        note = ('Item-level composition of separately reviewed old and new histories; the two rounds are not '
                'asserted to have the same reviewers. Reviewer identities and independence are user-reported, not authenticated.')
        ai = bool(old_ground['reviewer_declaration']['used_ai_assistance'] or
                  review['reviewer_declaration']['used_ai_assistance'])
        grounds.append({'format':'ac3-prospective-grounding-review-v1', 'reviewer_slot':slot, 'input_sha256':source_sha,
                        'reviewer_declaration':{'reviewer_label':label,'completed_by_human':True,
                            'completed_independently':True,'used_ai_assistance':ai,'note':note}, 'cases':combined_cases})
        facts.append({'reviewer_label':label,'reviewer_slot':slot,'completed_by_human':True,
                      'completed_independently':True,'used_ai_assistance':bool(old_fact.get('used_ai_assistance') or ai),
                      'reviewed_fact_and_relation_semantics':True,'fact_plan_sha256':plan_sha,
                      'new_review_source_sha256':sha(new_review_raws[slot - 1]),'note':note})
    # This is only structural verification of independently declared human
    # review; a projected snapshot is not an actual system database.
    validate_fact_plan(source, plan, facts)
    return grounds, facts


def verify_expanded_manifest(manifest_path, source_raw, ground_raws, fact_raws=None):
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or not manifest_path.is_file(): raise ValueError('Manifest must be a regular file.')
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get('format') in ('ac3-expanded-h19-unresolved-composite-review-v1',
                                   'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1'):
        from scripts.import_ac3_h19_unresolved_reviews import verify_unresolved_manifest
        return verify_unresolved_manifest(manifest_path,source_raw,ground_raws,fact_raws)
    if manifest.get('format') in ('ac3-expanded-restored-composite-review-v1',
                                   'ac3-expanded-restored-user-confirmed-composite-review-v1'):
        from scripts.import_ac3_h19_restoration_reviews import verify_restored_manifest
        return verify_restored_manifest(manifest_path, source_raw, ground_raws, fact_raws)
    entries = manifest.get('inputs')
    expected_inputs = {'ac3-expanded-composite-review-v1':11, 'ac3-expanded-revised-composite-review-v1':16,
                       'ac3-expanded-rebased-composite-review-v1':18,
                       'ac3-expanded-user-confirmed-rebased-composite-review-v1':21,
                       'ac3-expanded-both-rounds-confirmed-composite-review-v1':24}
    if (manifest.get('format') not in expected_inputs or not isinstance(entries, list) or
            len(entries) != expected_inputs[manifest['format']]):
        raise ValueError('Invalid expanded review manifest.')
    paths = [resolve_evidence_path(entry['path']) for entry in entries]
    if any(path.is_symlink() or not path.is_file() for path in paths): raise ValueError('Manifest sources must be regular files.')
    raw = [path.read_bytes() for path in paths]
    if any(sha(data) != entry['sha256'] for data,entry in zip(raw,entries)):
        raise ValueError('Expanded review source changed.')
    if raw[7] != source_raw:
        raise ValueError('Expanded source differs from manifest.')
    new_review_raws = raw[9:11]
    if manifest['format'] in ('ac3-expanded-revised-composite-review-v1','ac3-expanded-rebased-composite-review-v1',
                              'ac3-expanded-user-confirmed-rebased-composite-review-v1',
                              'ac3-expanded-both-rounds-confirmed-composite-review-v1'):
        if manifest['format'] in ('ac3-expanded-user-confirmed-rebased-composite-review-v1',
                                  'ac3-expanded-both-rounds-confirmed-composite-review-v1'):
            verify_parent_user_confirmation(raw[11],raw[12],raw[9:11],raw[19:21],raw[18])
        if manifest['format'] == 'ac3-expanded-both-rounds-confirmed-composite-review-v1':
            verify_revision_user_confirmation(raw[14:16],raw[22:24],raw[21])
        base = raw[16:18] if manifest['format'] != 'ac3-expanded-revised-composite-review-v1' else (None,None)
        merged = merge_revision_reviews(raw[11],raw[12],raw[7],raw[8],raw[13],raw[9:11],raw[14:16],*base)
        new_review_raws = [json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() for row in merged]
    grounds, facts = convert(raw[0],raw[1],paths[2],raw[3:5],raw[5:7],raw[7],raw[8],new_review_raws)
    if [json.loads(x) for x in ground_raws] != grounds or (fact_raws is not None and [json.loads(x) for x in fact_raws] != facts):
        raise ValueError('Composite declarations differ from source-bound review decisions.')
    if any(path.read_bytes() != data for path,data in zip(paths,raw)):
        raise ValueError('Expanded review evidence changed during verification.')
    return {'source_sha256':sha(source_raw), 'fact_plan_sha256':canonical_sha(json.loads(raw[8])),
            'history_count':30,'question_count':120,'identity_authenticated':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('old-source','old-plan','old-manifest','old-ground-1','old-ground-2','old-fact-1','old-fact-2',
                 'expanded-source','expanded-plan','new-review-1','new-review-2','output-dir'):
        p.add_argument('--'+name,required=True,type=Path)
    for name in ('parent-expanded-source','parent-expanded-plan','revision-manifest','revision-review-1','revision-review-2'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--revision-base-source', type=Path)
    p.add_argument('--revision-base-plan', type=Path)
    p.add_argument('--parent-review-confirmation', type=Path)
    p.add_argument('--parent-original-review-1', type=Path)
    p.add_argument('--parent-original-review-2', type=Path)
    p.add_argument('--revision-review-confirmation', type=Path)
    p.add_argument('--revision-original-review-1', type=Path)
    p.add_argument('--revision-original-review-2', type=Path)
    a=p.parse_args()
    paths=[a.old_source,a.old_plan,a.old_manifest,a.old_ground_1,a.old_ground_2,a.old_fact_1,a.old_fact_2,
           a.expanded_source,a.expanded_plan,a.new_review_1,a.new_review_2]
    revision_paths=[a.parent_expanded_source,a.parent_expanded_plan,a.revision_manifest,a.revision_review_1,a.revision_review_2]
    if any(revision_paths) and not all(revision_paths):
        raise ValueError('A revised expansion requires both parent files, revision manifest and both revision reviews.')
    if all(revision_paths): paths.extend(revision_paths)
    base_paths=[a.revision_base_source,a.revision_base_plan]
    if any(base_paths) and (not all(base_paths) or not all(revision_paths)):
        raise ValueError('Both revision-base files require a complete revision evidence set.')
    if all(base_paths): paths.extend(base_paths)
    confirmation_paths=[a.parent_review_confirmation,a.parent_original_review_1,a.parent_original_review_2]
    if any(confirmation_paths) and (not all(confirmation_paths) or not all(base_paths)):
        raise ValueError('Parent confirmation requires both original reviews and both revision-base files.')
    if all(confirmation_paths): paths.extend(confirmation_paths)
    revision_confirmation_paths=[a.revision_review_confirmation,a.revision_original_review_1,a.revision_original_review_2]
    if any(revision_confirmation_paths) and (not all(revision_confirmation_paths) or not all(confirmation_paths)):
        raise ValueError('Revision confirmation requires its original reviews and parent confirmation evidence.')
    if all(revision_confirmation_paths): paths.extend(revision_confirmation_paths)
    if any(x.is_symlink() or not x.is_file() for x in paths): raise ValueError('All sources must be regular files.')
    raw=[x.read_bytes() for x in paths]
    new_review_raws=raw[9:11]
    if all(revision_paths):
        if all(confirmation_paths):
            verify_parent_user_confirmation(raw[11],raw[12],raw[9:11],raw[19:21],raw[18])
        if all(revision_confirmation_paths):
            verify_revision_user_confirmation(raw[14:16],raw[22:24],raw[21])
        base = raw[16:18] if all(base_paths) else (None,None)
        merged=merge_revision_reviews(raw[11],raw[12],raw[7],raw[8],raw[13],raw[9:11],raw[14:16],*base)
        new_review_raws=[json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() for row in merged]
    grounds,facts=convert(raw[0],raw[1],paths[2],raw[3:5],raw[5:7],raw[7],raw[8],new_review_raws)
    if any(path.read_bytes()!=data for path,data in zip(paths,raw)): raise ValueError('Sources changed during conversion.')
    a.output_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
    for prefix,rows in (('grounding-reviewer',grounds),('fact-reviewer',facts)):
        for i,row in enumerate(rows,1):
            fd=os.open(a.output_dir/f'{prefix}-{i}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'w',encoding='utf8') as stream: json.dump(row,stream,ensure_ascii=False,indent=2);stream.write('\n')
    manifest={'format':('ac3-expanded-both-rounds-confirmed-composite-review-v1' if all(revision_confirmation_paths) else
                       ('ac3-expanded-user-confirmed-rebased-composite-review-v1' if all(confirmation_paths) else
                       ('ac3-expanded-rebased-composite-review-v1' if all(base_paths) else
                       ('ac3-expanded-revised-composite-review-v1' if all(revision_paths) else 'ac3-expanded-composite-review-v1')))),
              'inputs':[{'path':str(path.resolve()),'sha256':sha(data)} for path,data in zip(paths,raw)],
              'disclosure':'Per-item original and new review; identity and independence are reported, not authenticated.',
              'protocol_frozen':False,'model_called':False}
    with (a.output_dir/'manifest.json').open('x',encoding='utf8') as stream: json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(a.output_dir),'history_count':30,'question_count':120,'protocol_frozen':False}))


if __name__=='__main__': main()
