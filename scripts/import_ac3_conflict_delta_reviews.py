"""Bind independently reviewed M4 revisions to the retained original reviews.

No decisions are inferred for changed material. This creates composite review
records, explicitly identifying their two source reviews; it cannot establish
reviewer identity and does not freeze or execute the study.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ac3_evidence_paths import resolve_evidence_path
from scripts.prepare_ac3_conflict_revision import prepare
from scripts.prepare_ac3_conflict_revision_explicit import prepare as prepare_explicit
from scripts.prepare_ac3_fact_review import build, canonical_sha
from scripts.import_ac3_fact_reviews import convert as validate_complete_fact_reviews


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def convert(old_raw, new_raw, old_plan_raw, new_plan_raw, old_ground_raws, old_fact_raws,
            grounding_confirmation_raw, fact_confirmation_raw, delta_raws, delta_template_raws):
    old, new = json.loads(old_raw), json.loads(new_raw)
    expected_new, expected_raw, expected_plan, expected_ground, expected_fact = prepare(old_raw)
    if new_raw != expected_raw:
        expected_new, expected_raw, expected_plan, expected_ground, expected_fact = prepare_explicit(old_raw)
    old_plan = json.loads(old_plan_raw)
    expected_old_plan, _ = build(old, digest(old_raw))
    if new_raw != expected_raw or new != expected_new or old_plan != expected_old_plan or json.loads(new_plan_raw) != expected_plan:
        raise ValueError('Source revision or fact plan differs from the exact supported M4 change')
    if any(len(x) != 2 for x in (old_ground_raws, old_fact_raws, delta_raws, delta_template_raws)):
        raise ValueError('Two reviews and two templates are required for every review stage')
    gc, fc = json.loads(grounding_confirmation_raw), json.loads(fact_confirmation_raw)
    if gc.get('format') != 'ac3-human-grounding-user-confirmation-v1' or not {'这是人工确认过的 忘记修改了 你帮我修改一下 然后继续推进', '是，两人独立完成'}.issubset(set(gc.get('user_statements', []))):
        raise ValueError('Original grounding user confirmation is missing')
    if fc.get('format') != 'ac3-fact-review-user-followup-v1' or fc.get('user_independence_statement') != '是，两人已独立核对' or fc.get('user_ambiguity_direction') != '补充单场地条件并重新审核（推荐）':
        raise ValueError('Original fact review user confirmation is missing')
    if fc.get('original_review_sha256') != [digest(raw) for raw in old_fact_raws]:
        raise ValueError('Original fact reviews differ from user-confirmed records')
    records = {r['slot']: r['confirmed_copy_sha256'] for r in gc.get('records', [])}
    if records != {i: digest(old_ground_raws[i - 1]) for i in (1, 2)}:
        raise ValueError('Original grounding copies differ from confirmed records')
    labels, out_ground, out_fact = set(), [], []
    for slot in (1, 2):
        og, of, delta, template = [json.loads(x[slot - 1]) for x in (old_ground_raws, old_fact_raws, delta_raws, delta_template_raws)]
        declaration = delta.get('reviewer_declaration', {})
        label = declaration.get('reviewer_label')
        if not isinstance(label, str) or not label.strip() or label.strip().casefold() in labels:
            raise ValueError('Revised reviews require two different reviewer labels')
        labels.add(label.strip().casefold())
        if declaration.get('completed_by_human') is not True or declaration.get('completed_independently') is not True or type(declaration.get('used_ai_assistance')) is not bool:
            raise ValueError('Revised reviews require explicit human, independent and AI declarations')
        if delta.get('reviewer_slot') != slot or template.get('reviewer_slot') != slot:
            raise ValueError('Reviewer slots do not match')
        if {k:v for k,v in delta.items() if k not in ('reviewer_declaration','cases')} != {k:v for k,v in template.items() if k not in ('reviewer_declaration','cases')}:
            raise ValueError('Changed-review header does not match the provided blank template')
        if template.get('previous_source_sha256') != digest(old_raw) or template.get('revised_source_sha256') != digest(new_raw) or template.get('fact_plan_sha256') != canonical_sha(expected_plan):
            raise ValueError('Changed-review template does not match the exact source and plan')
        old_decl = og.get('reviewer_declaration', {})
        if og.get('reviewer_slot') != slot or og.get('input_sha256') != digest(old_raw) or old_decl.get('completed_by_human') is not True or old_decl.get('completed_independently') is not True or type(old_decl.get('used_ai_assistance')) is not bool:
            raise ValueError('Original source review declaration invalid')
        fact_decl = of.get('reviewer_declaration', {})
        if of.get('reviewer_slot') != slot or of.get('source_input_sha256') != digest(old_raw) or of.get('fact_plan_sha256') != canonical_sha(old_plan) or fact_decl.get('completed_by_human') is not True or type(fact_decl.get('used_ai_assistance')) is not bool:
            raise ValueError('Original fact review declaration invalid')
        old_cases, fact_cases, revised_cases, templates = og.get('cases', []), of.get('histories', []), delta.get('cases', []), template.get('cases', [])
        if any(len(x) != 8 for x in (old_cases, fact_cases, revised_cases, templates)):
            raise ValueError('Every review must include eight histories')
        new_g, new_f = copy.deepcopy(expected_ground[slot - 1]), copy.deepcopy(expected_fact[slot - 1])
        composite_label = f'Composite slot {slot}: original reviewer and revision reviewer {label.strip()}'
        note = ('Composite per-item review: unchanged material uses the original user-confirmed review; '
                'M4, question 3 and affected fact/relationship use the independently completed revision review. '
                'The original and revision reviewers in this slot are not asserted to be the same person. '
                'Reviewer identities and reported independence are not independently authenticated.')
        ai = bool(old_decl.get('used_ai_assistance') or fact_decl.get('used_ai_assistance') or declaration['used_ai_assistance'])
        for packet in (new_g, new_f):
            packet['reviewer_declaration'] = {'reviewer_label': composite_label, 'completed_by_human': True,
                'completed_independently': True, 'used_ai_assistance': ai, 'note': note}
            packet['status'] = 'COMPOSITE REVIEW; per-item provenance in note and source manifest'
        for index, (source, old_g, old_f, changed, blank) in enumerate(zip(old['cases'], old_cases, fact_cases, revised_cases, templates)):
            hid = source['history_id']; section = old_plan['histories'][hid]
            if any(item.get('history_id') != hid for item in (old_g, old_f, changed, blank)):
                raise ValueError('History order or identifier changed')
            if old_g.get('source_messages') != source['source_messages'] or old_f.get('source_messages') != source['source_messages']:
                raise ValueError('Original reviewer source differs')
            if old_f.get('proposed_facts') != section['facts'] or old_f.get('proposed_relationships') != section['relationships'] or old_f.get('review', {}).get('decision') != 'accept':
                raise ValueError('Original fact review does not accept the exact original plan')
            if old_f.get('questions') != expected_fact[slot - 1]['histories'][index]['questions']:
                raise ValueError('Original fact reviewer saw different questions')
            if {k:v for k,v in changed.items() if k != 'review'} != {k:v for k,v in blank.items() if k != 'review'}:
                raise ValueError('Changed-review content differs from its template')
            revised_section = expected_plan['histories'][hid]
            actual_expected = {'history_id': hid, 'previous_M4': source['source_messages'][3]['text'],
                'revised_M4': new['cases'][index]['source_messages'][3]['text'], 'question': new['cases'][index]['tests'][2],
                'affected_facts': [f for f in revised_section['facts'] if f['source_message_id'] == hid + '-M4'],
                'affected_conflict_relation': [r for r in revised_section['relationships'] if r['relationship_type'] == 'CONFLICT'][0]}
            if {k:v for k,v in blank.items() if k != 'review'} != actual_expected:
                raise ValueError('Changed-review template does not match the exact generated source and plan')
            revised = changed.get('review', {})
            if revised.get('question_validity') != 'valid' or revised.get('fact_and_relation') != 'accept':
                raise ValueError('Every changed question and fact relationship must be accepted')
            for qindex, (question, old_question) in enumerate(zip(source['tests'], old_g.get('questions', []))):
                if {k:v for k,v in old_question.items() if k != 'review'} != question:
                    raise ValueError('Original question differs from source')
                if qindex == 2:
                    comment = revised.get('comment', '')
                    if not isinstance(comment, str): raise ValueError('Changed-review comment must be text')
                    rationale = comment.strip() or f'Reviewer accepted the revised question; recorded source pointer: {hid}-M4. No reviewer rationale was supplied.'
                    new_g['cases'][index]['questions'][qindex]['review'] = {'question_validity': 'valid', 'rationale': rationale}
                else:
                    if old_question.get('review', {}).get('question_validity') != 'valid':
                        raise ValueError('Unchanged question lacks prior valid review')
                    new_g['cases'][index]['questions'][qindex]['review'] = copy.deepcopy(old_question['review'])
            if len(old_g.get('questions', [])) != 4:
                raise ValueError('Original question count differs')
            new_f['histories'][index]['review'] = {'decision': 'accept', 'comment': 'Composite: original review for unchanged facts and revised review for M4 facts/CONFLICT. ' + str(revised.get('comment', ''))}
        out_ground.append(new_g); out_fact.append(new_f)
    validate_complete_fact_reviews(new_raw, new_plan_raw, [json.dumps(x, ensure_ascii=False).encode() for x in out_fact])
    return out_ground, out_fact


def verify_manifest(manifest_path, revised_source_raw, ground_raws, fact_declaration_raws=None):
    """Rebuild composite judgments from bound source evidence, without trusting output labels."""
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('Composite manifest must be a regular file')
    manifest = json.loads(manifest_path.read_bytes())
    entries = manifest.get('inputs')
    if manifest.get('format') != 'ac3-conflict-composite-review-v1' or not isinstance(entries, list) or len(entries) != 14:
        raise ValueError('Invalid composite review manifest')
    paths = [resolve_evidence_path(e['path']) for e in entries]
    if any(not p.is_absolute() or p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('Composite source must be an absolute regular file')
    raw = [p.read_bytes() for p in paths]
    if any(digest(data) != e.get('sha256') for e, data in zip(entries, raw)) or raw[1] != revised_source_raw:
        raise ValueError('Composite source or evidence hash does not match')
    ground, fact = convert(raw[0],raw[1],raw[2],raw[3],raw[4:6],raw[6:8],raw[8],raw[9],raw[10:12],raw[12:14])
    if len(ground_raws) != 2 or any(json.loads(data) != row for data,row in zip(ground_raws,ground)):
        raise ValueError('Composite grounding outputs differ from their underlying reviews')
    if fact_declaration_raws is not None:
        if len(fact_declaration_raws) != 2:
            raise ValueError('Exactly two composite fact declarations are required')
        # Importer hashes the exact full-packet bytes, so preserve the output
        # files' formatting rather than creating replacement packet bytes.
        composite_dir = manifest_path.parent
        packet_paths = [composite_dir / f'fact-reviewer-{i}.json' for i in (1, 2)]
        if any(p.is_symlink() or not p.is_file() for p in packet_paths):
            raise ValueError('Composite fact review packets are missing')
        packet_raws = [p.read_bytes() for p in packet_paths]
        if any(json.loads(data) != row for data,row in zip(packet_raws,fact)):
            raise ValueError('Composite fact packets differ from their underlying reviews')
        declarations = validate_complete_fact_reviews(raw[1],raw[3],packet_raws)
        if any(json.loads(data) != row for data,row in zip(fact_declaration_raws,declarations)):
            raise ValueError('Fact declarations differ from verified composite packets')
    if any(p.read_bytes() != data for p,data in zip(paths,raw)):
        raise ValueError('Composite evidence changed during verification')
    return {'source_sha256': digest(raw[1]), 'fact_plan_sha256': canonical_sha(json.loads(raw[3])),
            'evidence_sha256': [digest(x) for x in raw], 'identity_authenticated': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('old-source','new-source','old-plan','new-plan','old-ground-1','old-ground-2','old-fact-1','old-fact-2','ground-confirmation','fact-confirmation','delta-1','delta-2','template-1','template-2','output-dir'):
        p.add_argument('--' + flag, type=Path, required=True)
    a = p.parse_args()
    paths = [a.old_source,a.new_source,a.old_plan,a.new_plan,a.old_ground_1,a.old_ground_2,a.old_fact_1,a.old_fact_2,a.ground_confirmation,a.fact_confirmation,a.delta_1,a.delta_2,a.template_1,a.template_2]
    if any(not x.is_file() or x.is_symlink() for x in paths): raise ValueError('All inputs must be regular files')
    raw = [x.read_bytes() for x in paths]
    grounds, facts = convert(raw[0],raw[1],raw[2],raw[3],raw[4:6],raw[6:8],raw[8],raw[9],raw[10:12],raw[12:14])
    if any(x.read_bytes() != data for x,data in zip(paths,raw)): raise ValueError('Inputs changed during conversion')
    a.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    for prefix, rows in (('grounding-reviewer',grounds),('fact-reviewer',facts)):
        for i,row in enumerate(rows,1):
            fd=os.open(a.output_dir/f'{prefix}-{i}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'w',encoding='utf8') as f: json.dump(row,f,ensure_ascii=False,indent=2); f.write('\n')
    manifest={'format':'ac3-conflict-composite-review-v1','inputs':[{'path':str(path.resolve()),'sha256':digest(data)} for path,data in zip(paths,raw)],
        'disclosure':'Composite records represent per-item original and revision reviews; neither shared individual identity nor independent authentication is asserted.',
        'protocol_frozen':False,'model_called':False}
    with (a.output_dir/'manifest.json').open('x',encoding='utf8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2); f.write('\n')
    print(json.dumps({'output':str(a.output_dir),'reviewers':2,'composite':True,'protocol_frozen':False}))


if __name__ == '__main__': main()
