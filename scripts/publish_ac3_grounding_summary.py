"""Publish a source-bound, non-result snapshot of AC3 grounding review."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'output/proposal-delivery/ac3-grounding-human-confirmed-2026-10-28'
CANDIDATE = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3/candidate-inputs.json'
THRESHOLD_ACCEPTANCE = ROOT / 'output/proposal-delivery/ac3-threshold-user-acceptance-2026-10-28.json'
PILOT = ROOT / 'output/proposal-delivery/ac3-pilot-threshold-draft-2026-10-28-v2.json'
COVERAGE_DECISION = ROOT / 'output/proposal-delivery/ac3-coverage-user-decision-2026-10-28.json'
THRESHOLD_SELECTION = ROOT / 'output/proposal-delivery/ac3-threshold-selection-user-delegated-2026-10-28.json'
REVISION = ROOT / 'output/proposal-delivery/ac3-conflict-revision-draft-2026-10-28-v3'
REVISION_CONFIRMATION = ROOT / 'output/proposal-delivery/ac3-conflict-v3-user-confirmed-2026-10-28'
COMPOSITE = ROOT / 'output/proposal-delivery/ac3-v3-composite-human-review-2026-10-28'
FACT_DECLARATIONS = ROOT / 'output/proposal-delivery/ac3-v3-composite-fact-declarations-2026-10-28'
# The original candidate draft is byte-identically reconstructed here;
# the shared v5 working files were subsequently changed and are preserved as
# user material.  Do not interpret their declarations as accepted review.
EXPANSION = ROOT / 'output/proposal-delivery/ac3-expanded-v5-original-reconstructed-2026-10-28'
EXPANSION_REPAIR = ROOT / 'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v6'
EXPANSION_V5_CONFIRMED = ROOT / 'output/proposal-delivery/ac3-expanded-v5-confirmed-intake-2026-10-28'
EXPANSION_V6_COMPOSITE = ROOT / 'output/proposal-delivery/ac3-expanded-v6-composite-user-confirmed-2026-10-28'
EXPANSION_V6_CONFIRMED = ROOT / 'output/proposal-delivery/ac3-expanded-v6-user-confirmed-2026-10-28'
EXPANSION_V7 = ROOT / 'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v7'
H19_CONFIRMED = ROOT / 'output/proposal-delivery/ac3-h19-user-confirmed-2026-10-28'
EXPANSION_V7_COMPOSITE = ROOT / 'output/proposal-delivery/ac3-expanded-v7-composite-user-confirmed-2026-10-28'
EXPANSION_V8 = ROOT / 'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v8'
H19_FACT_EDGE_CONFIRMED = ROOT / 'output/proposal-delivery/ac3-h19-fact-edge-user-confirmed-2026-10-28'
EXPANSION_V8_COMPOSITE = ROOT / 'output/proposal-delivery/ac3-expanded-v8-composite-user-confirmed-2026-10-28'
OUTPUT = ROOT / 'frontend/public/reports/ac3-grounding-summary-v1.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(record, reviews, candidate, checker):
    confirmation = json.loads(record.read_text())
    if confirmation.get('format') != 'ac3-human-grounding-user-confirmation-v1' or len(confirmation.get('records', [])) != 2:
        raise ValueError('Missing user confirmation record')
    for slot, path in enumerate(reviews, 1):
        entry = confirmation['records'][slot - 1]
        if entry['slot'] != slot or digest(path) != entry['confirmed_copy_sha256']:
            raise ValueError('Confirmed review copy differs from the confirmation record')
    check = json.loads(subprocess.run([sys.executable, str(checker), '--review-1', str(reviews[0]), '--review-2', str(reviews[1])], check=True, capture_output=True, text=True).stdout)
    if check['input_sha256'] != digest(candidate):
        raise ValueError('Checker used a different source packet')
    labels = []
    for path in reviews:
        review = json.loads(path.read_text())
        labels.append({q['test_id']: q['review']['question_validity'] for case in review['cases'] for q in case['questions']})
    ids = labels[0].keys()
    agreed_invalid = sum(labels[0][i] == labels[1][i] == 'invalid' for i in ids)
    missing = sum(None in (labels[0][i], labels[1][i]) or 'uncertain' in (labels[0][i], labels[1][i]) for i in ids)
    disagreements = sum(labels[0][i] != labels[1][i] and None not in (labels[0][i], labels[1][i]) and 'uncertain' not in (labels[0][i], labels[1][i]) for i in ids)
    if check['both_valid'] + agreed_invalid + missing + disagreements != check['questions']:
        raise ValueError('Review outcomes do not partition the source questions')
    return {'format': 'ac3-grounding-summary-v1', 'snapshot_confirmed_at_utc': confirmation['timestamp_utc'],
            'scope': 'candidate question grounding review; not held-out answers or Auditor accuracy',
            'questions': check['questions'], 'agreed_valid': check['both_valid'],
            'agreed_invalid': agreed_invalid, 'disagreed': disagreements,
            'missing_or_uncertain': missing,
            'review_process': 'User confirmed two different independent human reviewers; both files record AI assistance. Original declarations conflict and are preserved; identities not independently authenticated.',
            'protocol_frozen': False, 'held_out_results_available': False,
            'source_sha256': {'candidate': digest(candidate), 'user_confirmation': digest(record),
                              'review_1': digest(reviews[0]), 'review_2': digest(reviews[1])}}


def bind_revision(result, revision):
    """Distinguish the original reviewed snapshot from the changed, unreviewed source."""
    manifest_path = revision / 'manifest.json'
    source_path = revision / 'candidate-inputs.json'
    manifest = json.loads(manifest_path.read_text())
    source = json.loads(source_path.read_text())
    if (manifest.get('format') != 'ac3-conflict-revision-draft-v1'
            or manifest.get('original_source_sha256') != result['source_sha256']['candidate']
            or manifest.get('revised_source_sha256') != digest(source_path)
            or manifest.get('human_review_complete') is not False
            or manifest.get('protocol_frozen') is not False
            or manifest.get('model_called') is not False):
        raise ValueError('Revision does not match the previous snapshot or draft status')
    original = json.loads(CANDIDATE.read_text())
    sys.path.insert(0, str(ROOT))
    from scripts.prepare_ac3_conflict_revision_explicit import prepare
    _, expected_raw, _, _, _ = prepare(CANDIDATE.read_bytes())
    if source_path.read_bytes() != expected_raw:
        raise ValueError('Revision does not match the explicit conflicting claims')
    before = {item['history_id']: item for item in original['cases']}
    after = {item['history_id']: item for item in source['cases']}
    if len(before) != 8 or len(after) != 8 or set(before) != set(after):
        raise ValueError('Unexpected revision history IDs')
    changed = 0
    for history_id, old in before.items():
        new = after[history_id]
        if old['tests'] != new['tests'] or len(old['source_messages']) != 5 or len(new['source_messages']) != 5:
            raise ValueError('Unexpected question or source-message change')
        for index, (a, b) in enumerate(zip(old['source_messages'], new['source_messages'])):
            if a != b:
                if index != 3:
                    raise ValueError('Unexpected source change outside M4')
                changed += 1
    if changed != 8:
        raise ValueError('Expected one changed source per history')
    result['revision'] = {'histories_changed': changed, 'affected_question_contexts': changed,
                          'review_complete': False, 'source_sha256': digest(source_path),
                          'manifest_sha256': digest(manifest_path)}
    return result


def bind_reviewed_revision(result, revision, confirmation_dir, composite_dir, declarations_dir):
    """Publish only after reconstructing the composite from the original and new reviews."""
    sys.path.insert(0, str(ROOT))
    from scripts.import_ac3_conflict_delta_reviews import verify_manifest
    record_path = confirmation_dir / 'confirmation-record.json'
    confirmation = json.loads(record_path.read_text())
    files = confirmation.get('files', [])
    if (confirmation.get('format') != 'ac3-v3-human-user-confirmation-v1' or len(files) != 2
            or '是，新版 v3 也已独立审核通过' not in confirmation.get('user_statements', [])):
        raise ValueError('Revised-source user confirmation is incomplete')
    returned = []
    for slot, entry in enumerate(files, 1):
        source = confirmation_dir / entry['confirmed_copy']
        if entry['reviewer_slot'] != slot or source.is_symlink() or digest(source) != entry['confirmed_copy_sha256']:
            raise ValueError('Revised review copy differs from user-confirmed evidence')
        returned.append(source)
    manifest_path = composite_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if [str(p.resolve()) for p in returned] != [entry['path'] for entry in manifest['inputs'][10:12]]:
        raise ValueError('Composite refers to different revised review copies')
    source_path = revision / 'candidate-inputs.json'
    ground = [composite_dir / f'grounding-reviewer-{i}.json' for i in (1, 2)]
    declarations = [declarations_dir / f'fact-review-{i}.json' for i in (1, 2)]
    verified = verify_manifest(manifest_path, source_path.read_bytes(), [p.read_bytes() for p in ground],
                               [p.read_bytes() for p in declarations])
    ready = json.loads(subprocess.run([sys.executable, str(ROOT / 'scripts/check_ac3_prospective_readiness.py'),
        '--source', str(source_path), '--review-1', str(ground[0]), '--review-2', str(ground[1]),
        '--composite-manifest', str(manifest_path)], check=True, capture_output=True, text=True).stdout)
    if (verified['source_sha256'] != result['revision']['source_sha256'] or ready['questions'] != 32
            or ready['both_valid'] != 32 or ready['disagreed'] != 0 or ready['missing_or_uncertain'] != 0):
        raise ValueError('Composite revision is not fully reviewed')
    result['revision'].update({'review_complete': True, 'questions': ready['questions'],
        'agreed_valid': ready['both_valid'], 'user_confirmation_sha256': digest(record_path),
        'composite_manifest_sha256': digest(manifest_path),
        'review_note': 'User confirms two different people independently reviewed the changed material. '
                       'The composite retains original review for unchanged material; AI assistance was used. '
                       'Reviewers and independence were not independently authenticated.'})
    return result


def bind_expansion(result, expansion, revision, repair=None):
    """Display the proposed sample size without asserting new human reviews."""
    manifest_path = expansion / 'manifest.json'; source_path = expansion / 'candidate-inputs.json'
    plan_path = expansion / 'proposed-fact-plan.json'
    manifest = json.loads(manifest_path.read_text()); source = json.loads(source_path.read_text())
    original_path = revision / 'candidate-inputs.json'; original = json.loads(original_path.read_text())
    original_plan_path = revision / 'proposed-fact-plan.json'; original_plan = json.loads(original_plan_path.read_text())
    plan = json.loads(plan_path.read_text())
    if (manifest.get('format') != 'ac3-expanded-candidate-manifest-v1'
            or manifest.get('original_source_sha256') != digest(original_path)
            or manifest.get('candidate_sha256') != digest(source_path)
            or manifest.get('fact_plan_sha256') != digest(plan_path)
            or manifest.get('original_fact_plan_sha256') != digest(original_plan_path)
            or manifest.get('new_review_required') is not True
            or manifest.get('frozen') is not False or manifest.get('model_called') is not False
            or source.get('cases', [])[:8] != original.get('cases')
            or len(source.get('cases', [])) != 30
            or {k: plan.get('histories', {}).get(k) for k in original_plan['histories']} != original_plan['histories']
            or set(plan.get('histories', {})) != {c['history_id'] for c in source.get('cases', [])}
            or sum(len(c.get('tests', [])) for c in source['cases']) != 120):
        raise ValueError('Expansion is not bound to the reviewed source and proposed 30-history sample')
    result['expansion'] = {'reviewed_histories': 8, 'new_histories': 22, 'proposed_histories': 30,
        'reviewed_questions': 32, 'new_questions': 88, 'proposed_questions': 120,
        'new_review_complete': False, 'source_sha256': digest(source_path),
        'manifest_sha256': digest(manifest_path), 'fact_plan_sha256': digest(plan_path)}
    if repair is not None:
        sys.path.insert(0,str(ROOT))
        from scripts.prepare_ac3_expansion_repair import build as rebuild_repair, CHANGED
        repaired_source_path = repair / 'candidate-inputs.json'; repaired_plan_path = repair / 'proposed-fact-plan.json'
        repair_manifest_path = repair / 'manifest.json'
        repair_manifest = json.loads(repair_manifest_path.read_text())
        expected_source, expected_plan = rebuild_repair(source_path.read_bytes(), plan_path.read_bytes())
        if (repair_manifest.get('format') != 'ac3-expanded-repair-manifest-v1'
            or repair_manifest.get('parent_source_sha256') != digest(source_path)
            or repair_manifest.get('parent_fact_plan_sha256') != digest(plan_path)
            or repair_manifest.get('revised_source_sha256') != digest(repaired_source_path)
            or repair_manifest.get('revised_fact_plan_sha256') != digest(repaired_plan_path)
            or repair_manifest.get('changed_history_ids') != CHANGED
            or json.loads(repaired_source_path.read_text()) != expected_source
            or json.loads(repaired_plan_path.read_text()) != expected_plan
            or repair_manifest.get('review_required_for_changed_histories') is not True
            or repair_manifest.get('frozen') is not False or repair_manifest.get('model_called') is not False):
            raise ValueError('Repair is not bound to the exact expansion and expected scoped changes')
        result['expansion'].update({'v5_unchanged_new_histories': 12, 'v6_revised_histories': len(CHANGED),
            'source_sha256': digest(repaired_source_path), 'fact_plan_sha256': digest(repaired_plan_path),
            'repair_manifest_sha256': digest(repair_manifest_path), 'parent_source_sha256': digest(source_path)})
    return result


def bind_confirmed_v5_unchanged(result, confirmed, revision, composite, declarations, repair):
    """Count only source-identical v5-reviewed histories toward the v6 draft."""
    from scripts.import_ac3_expanded_reviews import convert
    record_path = confirmed / 'confirmation.json'; record = json.loads(record_path.read_text())
    if record.get('format') != 'ac3-expanded-v5-user-confirmation-v1' or record.get('user_response') != '是，两人已独立核对':
        raise ValueError('Expanded v5 user confirmation is missing')
    entries = record.get('files', [])
    expected = {'candidate-inputs.json', 'proposed-fact-plan.json', 'manifest.json', 'reviewer-1.json', 'reviewer-2.json'}
    if len(entries) != 5 or {entry.get('name') for entry in entries} != expected:
        raise ValueError('Expected exactly the five archived v5 input hashes')
    for entry in entries:
        source = confirmed / ('original-' + entry['name'])
        if source.is_symlink() or not source.is_file() or digest(source) != entry['sha256']:
            raise ValueError('Archived v5 file differs from user-confirmed evidence')
    for i in (1, 2):
        original = json.loads((confirmed / f'original-reviewer-{i}.json').read_text())
        approved = json.loads((confirmed / f'reviewer-{i}-user-confirmed.json').read_text())
        if {k:v for k,v in original.items() if k != 'reviewer_declaration'} != {k:v for k,v in approved.items() if k != 'reviewer_declaration'}:
            raise ValueError('Confirmed v5 copy changes underlying review contents')
    prior_source = (revision / 'candidate-inputs.json').read_bytes()
    prior_plan = (revision / 'proposed-fact-plan.json').read_bytes()
    reviewed_source = (confirmed / 'original-candidate-inputs.json').read_bytes()
    reviewed_plan = (confirmed / 'original-proposed-fact-plan.json').read_bytes()
    ground_raws = [(composite / f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)]
    fact_raws = [(declarations / f'fact-review-{i}.json').read_bytes() for i in (1,2)]
    reviewed_raws = [(confirmed / f'reviewer-{i}-user-confirmed.json').read_bytes() for i in (1,2)]
    convert(prior_source, prior_plan, composite / 'manifest.json', ground_raws, fact_raws,
            reviewed_source, reviewed_plan, reviewed_raws)
    reviewed = json.loads(reviewed_source); reviewed_fact_plan = json.loads(reviewed_plan)
    revised = json.loads((repair / 'candidate-inputs.json').read_text())
    revised_fact_plan = json.loads((repair / 'proposed-fact-plan.json').read_text())
    manifest = json.loads((repair / 'manifest.json').read_text()); changed = set(manifest['changed_history_ids'])
    prior_by_id = {c['history_id']: c for c in reviewed['cases']}; revised_by_id = {c['history_id']: c for c in revised['cases']}
    inherited = [c['history_id'] for c in revised['cases'][8:] if c['history_id'] not in changed]
    if len(inherited) != 12 or any(prior_by_id.get(h) != revised_by_id[h] or reviewed_fact_plan['histories'].get(h) != revised_fact_plan['histories'][h] for h in inherited):
        raise ValueError('The unchanged v6 histories differ from the reviewed v5 material')
    result['expansion'].update({'reviewed_histories': 20, 'pending_histories': 10,
        'reviewed_questions': 80, 'pending_questions': 40, 'v5_reviewed_additional_histories': 22,
        'v5_user_confirmation_sha256': digest(record_path),
        'v5_review_note': 'Two people independently reviewed the v5 return per user confirmation; five edits were accepted separately, without a claimed separate post-edit human review. Only twelve exactly unchanged histories are inherited into v6. Identity is not independently authenticated.'})
    return result


def bind_confirmed_v6(result, confirmed, composite, repair):
    """Record complete human judgments while retaining a semantic qualification."""
    from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
    record_path = confirmed / 'confirmation.json'; record = json.loads(record_path.read_text())
    if record.get('format') != 'ac3-expanded-v6-user-confirmation-v1' or record.get('user_response') != '是，v6 两人已独立核对通过':
        raise ValueError('V6 human confirmation is missing')
    entries = record.get('files', [])
    if len(entries) != 4 or {(x.get('version'), x.get('slot')) for x in entries} != {('v5',1),('v5',2),('v6',1),('v6',2)}:
        raise ValueError('V6 original submissions are incomplete')
    for entry in entries:
        archived = confirmed / f"original-{entry['version']}-reviewer-{entry['slot']}.json"
        if archived.is_symlink() or not archived.is_file() or digest(archived) != entry['sha256']:
            raise ValueError('V6 original submission does not match user-confirmed hash')
    manifest_path = composite / 'manifest.json'; source_path = repair / 'candidate-inputs.json'
    manifest = json.loads(manifest_path.read_text())
    for slot in (1,2):
        confirmed_copy = confirmed / f'v6-reviewer-{slot}-user-confirmed.json'
        original = json.loads((confirmed / f'original-v6-reviewer-{slot}.json').read_text())
        current = json.loads(confirmed_copy.read_text())
        if {k:v for k,v in original.items() if k != 'reviewer_declaration'} != {k:v for k,v in current.items() if k != 'reviewer_declaration'}:
            raise ValueError('V6 confirmation copy changes review judgments')
        if manifest['inputs'][13 + slot]['path'] != str(confirmed_copy.resolve()):
            raise ValueError('Composite does not bind the confirmed v6 copies')
    ground = [(composite / f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)]
    facts = [(composite / f'fact-reviewer-{i}.json').read_bytes() for i in (1,2)]
    verified = verify_expanded_manifest(manifest_path, source_path.read_bytes(), ground, facts)
    if verified.get('history_count') != 30 or verified.get('question_count') != 120 or verified.get('source_sha256') != digest(source_path):
        raise ValueError('V6 composite does not cover the exact expanded source')
    qualification_path = composite / 'semantic-qualification.json'; qualification = json.loads(qualification_path.read_text())
    if (qualification.get('format') != 'ac3-expanded-v6-semantic-qualification-v1'
            or qualification.get('source_sha256') != digest(source_path)
            or qualification.get('composite_manifest_sha256') != digest(manifest_path)
            or qualification.get('affected_test_id') != 'AC3-H19-Q4'):
        raise ValueError('V6 semantic qualification is not bound to the reviewed source')
    result['expansion'].update({'reviewed_histories':30,'pending_histories':0,'reviewed_questions':120,'pending_questions':0,
        'new_review_complete':True,'v6_reviewed_histories':10,'v6_user_confirmation_sha256':digest(record_path),
        'v6_composite_manifest_sha256':digest(manifest_path),'semantic_qualification_sha256':digest(qualification_path),
        'semantic_qualification':'H19-Q4 calls an instruction an obligation although the source says to offer it; the human-reviewed item remains under clarification.',
        'v6_review_note':'The user confirmed two people independently reviewed the ten changed histories; AI assistance and original opinions are retained. Identities and independence are not independently authenticated.'})
    return result


def bind_single_question_revision(result, revision, parent, confirmed_v5):
    """Carry 119 identical question decisions forward; leave the edited question pending."""
    import copy
    source_path = revision / 'candidate-inputs.json'; plan_path = revision / 'proposed-fact-plan.json'
    parent_source_path = parent / 'candidate-inputs.json'; parent_plan_path = parent / 'proposed-fact-plan.json'
    manifest_path = revision / 'manifest.json'; manifest = json.loads(manifest_path.read_text())
    if (manifest.get('format') != 'ac3-h19-restoration-draft-v1'
        or manifest.get('parent_v6_source_sha256') != digest(parent_source_path)
        or manifest.get('parent_v6_plan_sha256') != digest(parent_plan_path)
        or manifest.get('revised_source_sha256') != digest(source_path)
        or manifest.get('test_id') != 'AC3-H19-Q4' or manifest.get('changed_fields') != ['question']
        or manifest.get('protocol_frozen') is not False or manifest.get('model_called') is not False
        or plan_path.read_bytes() != parent_plan_path.read_bytes()):
        raise ValueError('Single-question revision does not bind the reviewed v6 source')
    for entry in manifest.get('evidence', {}).values():
        p = Path(entry.get('path', ''))
        if not p.is_absolute() or p.is_symlink() or not p.is_file() or digest(p) != entry.get('sha256'):
            raise ValueError('Single-question revision evidence changed')
    previous = json.loads(parent_source_path.read_text()); current = json.loads(source_path.read_text())
    approved_v5 = json.loads((confirmed_v5 / 'original-candidate-inputs.json').read_text())
    def target(doc):
        items = [q for c in doc['cases'] if c['history_id'] == 'AC3-H19' for q in c['tests'] if q['test_id'] == 'AC3-H19-Q4']
        if len(items) != 1: raise ValueError('Expected one H19-Q4')
        return items[0]
    expected = copy.deepcopy(previous); target(expected)['question'] = target(approved_v5)['question']
    if current != expected or target(current)['question'] == target(previous)['question']:
        raise ValueError('The v7 source changes more than the reviewed single question')
    result['expansion'].update({'reviewed_histories':29,'pending_histories':1,'reviewed_questions':119,'pending_questions':1,
        'new_review_complete':False,'v7_pending_questions':1,'source_sha256':digest(source_path),
        'fact_plan_sha256':digest(plan_path),'single_question_manifest_sha256':digest(manifest_path),
        'semantic_qualification':'H19-Q4 wording was restored to distinguish an offer from a requirement; this one question needs renewed human review.',
        'v6_review_note':'The user confirmed two reviewers independently reviewed v6 with AI assistance; the single v7 wording change requires renewed review. Identities are not independently authenticated.'})
    return result


def bind_confirmed_v7_question(result, confirmed, composite, revision):
    """Verify 120 human question judgments; a relationship still needs resolution."""
    from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
    record_path = confirmed / 'confirmation.json'; record = json.loads(record_path.read_text())
    if (record.get('format') != 'ac3-h19-user-confirmation-v1'
        or record.get('user_response') != '是，两人独立核对并认可' or len(record.get('files', [])) != 2):
        raise ValueError('H19 user confirmation is missing')
    for entry in record['files']:
        slot = entry['slot']; original = confirmed / f'original-reviewer-{slot}.json'
        human_copy = confirmed / f'reviewer-{slot}-user-confirmed.json'
        if digest(original) != entry['original_sha256'] or digest(human_copy) != entry['confirmed_copy_sha256']:
            raise ValueError('H19 user-confirmed review hashes differ')
    manifest = composite / 'manifest.json'; source = revision / 'candidate-inputs.json'
    ground = [(composite / f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)]
    facts = [(composite / f'fact-reviewer-{i}.json').read_bytes() for i in (1,2)]
    verified = verify_expanded_manifest(manifest, source.read_bytes(), ground, facts)
    if verified.get('history_count') != 30 or verified.get('question_count') != 120 or verified.get('source_sha256') != digest(source):
        raise ValueError('V7 composite does not bind all reviewed questions')
    result['expansion'].update({'reviewed_histories':30,'pending_histories':0,'reviewed_questions':120,'pending_questions':0,
        'v7_pending_questions':0,'v7_question_review_complete':True,'new_review_complete':False,
        'pending_fact_relationship_count':1,'v7_question_confirmation_sha256':digest(record_path),
        'v7_composite_manifest_sha256':digest(manifest),
        'semantic_qualification':'H19-Q4 is human-reviewed, but H19’s scoped fact and contextual-override relationship remain under separate review; an offer does not necessarily replace the general preference.',
        'v7_review_note':'The user confirmed two people independently reviewed the restored question with AI assistance. Their scope qualifications and the separate relationship issue are retained; identity is not independently authenticated.'})
    return result


def bind_v8_pending_fact(result, draft, previous):
    """Keep human question decisions but never carry an altered fact/edge forward as reviewed."""
    import copy
    manifest_path = draft / 'manifest.json'; manifest = json.loads(manifest_path.read_text())
    source = draft / 'candidate-inputs.json'; plan = draft / 'proposed-fact-plan.json'
    old_source = previous / 'candidate-inputs.json'; old_plan = previous / 'proposed-fact-plan.json'
    if (manifest.get('format') != 'ac3-h19-unresolved-revision-v1'
        or manifest.get('source_sha256') != digest(source) or source.read_bytes() != old_source.read_bytes()
        or manifest.get('parent_fact_plan_sha256') != digest(old_plan)
        or manifest.get('revised_fact_plan_sha256') != digest(plan)
        or manifest.get('changed_fact_ids') != ['AC3-H19-F8']
        or manifest.get('review_required') is not True
        or manifest.get('unresolved_edge_status') != 'unresolved_not_written_as_confirmed'
        or manifest.get('protocol_frozen') is not False or manifest.get('model_called') is not False):
        raise ValueError('V8 fact revision is not bound to the reviewed v7 source')
    for entry in manifest.get('evidence', {}).values():
        p = Path(entry.get('path', ''))
        if not p.is_absolute() or p.is_symlink() or not p.is_file() or digest(p) != entry.get('sha256'):
            raise ValueError('V8 fact revision evidence changed')
    expected = copy.deepcopy(json.loads(old_plan.read_text()))
    section = expected['histories']['AC3-H19']; facts = [f for f in section['facts'] if f['memory_id'] == 'AC3-H19-F8']
    if len(facts) != 1: raise ValueError('Expected one H19 fact')
    facts[0]['canonical_value'] = facts[0]['source_span']
    edge = manifest.get('unresolved_edge'); before = section['relationships']
    if before.count(edge) != 1: raise ValueError('Expected one unresolved H19 relationship')
    section['relationships'] = [r for r in before if r != edge]
    if json.loads(plan.read_text()) != expected:
        raise ValueError('V8 changes more than the scoped fact and unresolved edge')
    result['expansion'].update({'source_sha256':digest(source), 'fact_plan_sha256':digest(plan),
        'v8_manifest_sha256':digest(manifest_path), 'v8_fact_review_pending':True,
        'pending_fact_relationship_count':1, 'new_review_complete':False,
        'semantic_qualification':'All 120 questions have human review. H19-F8 and its contextual relationship require separate review: offering digital instructions does not by itself replace printed instructions.',
        'v8_review_note':'The changed H19 fact and proposed edge are pending two human reviews. The earlier edge is retained as unresolved, not recorded as invalid or confirmed.'})
    return result


def bind_confirmed_v8_handling(result, confirmed, composite, draft):
    """Bind accepted fact and unresolved-edge handling without converting the edge to invalid."""
    from scripts.import_ac3_expanded_reviews import verify_expanded_manifest
    record_path = confirmed / 'confirmation.json'; record = json.loads(record_path.read_text())
    if (record.get('format') != 'ac3-h19-fact-edge-user-confirmation-v1'
        or record.get('user_response') != 'H19两位人工均确认`fact_validity=valid`、`edge_handling=accept`'
        or len(record.get('files', [])) != 2):
        raise ValueError('H19 fact and edge user confirmation is missing')
    for entry in record['files']:
        slot = entry['slot']; template = draft / f'reviewer-{slot}.json'; reviewed = confirmed / f'reviewer-{slot}-user-confirmed.json'
        if digest(template) != entry['blank_sha256'] or digest(reviewed) != entry['confirmed_sha256']:
            raise ValueError('H19 fact review copy or original template differs')
    manifest_path = composite / 'manifest.json'; manifest = json.loads(manifest_path.read_text()); source = draft / 'candidate-inputs.json'
    if (manifest.get('format') != 'ac3-expanded-h19-unresolved-user-confirmed-composite-review-v1'
        or manifest['inputs'][12]['path'] != str(record_path.resolve())):
        raise ValueError('V8 composite does not bind the user confirmation')
    for slot in (1,2):
        if manifest['inputs'][9+slot]['path'] != str((confirmed / f'reviewer-{slot}-user-confirmed.json').resolve()):
            raise ValueError('V8 composite refers to other fact reviews')
    ground = [(composite / f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)]
    facts = [(composite / f'fact-reviewer-{i}.json').read_bytes() for i in (1,2)]
    verified = verify_expanded_manifest(manifest_path, source.read_bytes(), ground, facts)
    if verified.get('history_count') != 30 or verified.get('question_count') != 120 or verified.get('source_sha256') != digest(source):
        raise ValueError('V8 composite does not cover the current reviewed source')
    result['expansion'].update({'new_review_complete':True,'v8_fact_review_pending':False,
        'pending_fact_relationship_count':0,'v8_fact_confirmation_sha256':digest(record_path),
        'v8_composite_manifest_sha256':digest(manifest_path),
        'unresolved_edge_status':'unresolved_not_written_as_confirmed',
        'semantic_qualification':'All 120 questions have human review. H19-F8 and the handling of its edge were reviewed; the original contextual-override edge remains unresolved and is not recorded as confirmed or invalid.',
        'v8_review_note':'The user reports two people independently reviewed the corrected H19 fact and accepted leaving the earlier relationship unresolved. AI assistance and original opinions remain recorded; identity and independence are not independently authenticated.'})
    return result


def main():
    record = EVIDENCE / 'confirmation-record.json'
    reviews = [EVIDENCE / f'grounding-reviewer-{slot}-human-confirmed.json' for slot in (1, 2)]
    result = build(record, reviews, CANDIDATE, ROOT / 'scripts/check_ac3_prospective_readiness.py')
    accepted = json.loads(THRESHOLD_ACCEPTANCE.read_text())
    pilot = json.loads(PILOT.read_text())
    if (accepted.get('format') != 'ac3-threshold-user-acceptance-v1'
            or accepted.get('pilot_draft_sha256') != digest(PILOT)
            or accepted.get('accepted_thresholds') != pilot.get('proposed_thresholds')):
        raise ValueError('Accepted thresholds do not match the recorded pilot draft')
    result['thresholds_accepted'] = True
    decision = json.loads(COVERAGE_DECISION.read_text())
    if decision.get('threshold_response') != '先调整阈值':
        raise ValueError('Latest user direction on thresholds is not recorded')
    selection = json.loads(THRESHOLD_SELECTION.read_text())
    if (selection.get('format') != 'ac3-user-selected-thresholds-v1'
            or selection.get('user_response') != '你觉得合适的阈值就行 80%？'
            or selection.get('pilot_draft_sha256') != digest(PILOT)
            or selection.get('thresholds') != {'failure_detection_recall_min': .8, 'failure_classification_accuracy_min': .8,
                                               'test_validity_min': .9, 'false_positive_rate_max': .1}):
        raise ValueError('Updated threshold selection is not bound to the user direction and pilot')
    result['threshold_status'] = 'selected_not_frozen'
    result['source_sha256']['threshold_selection'] = digest(THRESHOLD_SELECTION)
    result['source_sha256']['coverage_user_decision'] = digest(COVERAGE_DECISION)
    result['source_sha256']['threshold_acceptance'] = digest(THRESHOLD_ACCEPTANCE)
    result['source_sha256']['pilot_draft'] = digest(PILOT)
    bind_revision(result, REVISION)
    bind_reviewed_revision(result, REVISION, REVISION_CONFIRMATION, COMPOSITE, FACT_DECLARATIONS)
    bind_expansion(result, EXPANSION, REVISION, EXPANSION_REPAIR)
    bind_confirmed_v5_unchanged(result, EXPANSION_V5_CONFIRMED, REVISION, COMPOSITE, FACT_DECLARATIONS, EXPANSION_REPAIR)
    bind_confirmed_v6(result, EXPANSION_V6_CONFIRMED, EXPANSION_V6_COMPOSITE, EXPANSION_REPAIR)
    bind_single_question_revision(result, EXPANSION_V7, EXPANSION_REPAIR, EXPANSION_V5_CONFIRMED)
    bind_confirmed_v7_question(result, H19_CONFIRMED, EXPANSION_V7_COMPOSITE, EXPANSION_V7)
    bind_v8_pending_fact(result, EXPANSION_V8, EXPANSION_V7)
    bind_confirmed_v8_handling(result, H19_FACT_EDGE_CONFIRMED, EXPANSION_V8_COMPOSITE, EXPANSION_V8)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Published reviewed source snapshot: {OUTPUT}')


if __name__ == '__main__': main()
