"""The source hashes bind this snapshot to the user-confirmed copies."""
import json
import shutil
import pytest
from scripts import publish_ac3_grounding_summary as publisher


def test_current_source_snapshot_and_tamper_rejected(tmp_path):
    record = publisher.EVIDENCE / 'confirmation-record.json'
    reviews = [publisher.EVIDENCE / f'grounding-reviewer-{slot}-human-confirmed.json' for slot in (1, 2)]
    checker = publisher.ROOT / 'scripts/check_ac3_prospective_readiness.py'
    result = publisher.build(record, reviews, publisher.CANDIDATE, checker)
    assert result['questions'] == 32
    assert result['agreed_valid'] + result['agreed_invalid'] + result['disagreed'] + result['missing_or_uncertain'] == 32
    assert not result['protocol_frozen'] and not result['held_out_results_available']
    changed = tmp_path / 'changed.json'
    changed.write_text(reviews[0].read_text() + ' ')
    with pytest.raises(ValueError, match='differs'):
        publisher.build(record, [changed, reviews[1]], publisher.CANDIDATE, checker)


def test_revision_bound_to_original_and_review_still_pending(tmp_path):
    record = publisher.EVIDENCE / 'confirmation-record.json'
    reviews = [publisher.EVIDENCE / f'grounding-reviewer-{slot}-human-confirmed.json' for slot in (1, 2)]
    checker = publisher.ROOT / 'scripts/check_ac3_prospective_readiness.py'
    result = publisher.build(record, reviews, publisher.CANDIDATE, checker)
    revision = publisher.bind_revision(result, publisher.REVISION)['revision']
    assert revision['affected_question_contexts'] == 8
    assert revision['review_complete'] is False
    for name in ('manifest.json', 'candidate-inputs.json'):
        (tmp_path / name).write_bytes((publisher.REVISION / name).read_bytes())
    (tmp_path / 'candidate-inputs.json').write_text((tmp_path / 'candidate-inputs.json').read_text() + ' ')
    with pytest.raises(ValueError, match='Revision does not match'):
        publisher.bind_revision(result, tmp_path)


def test_reviewed_revision_requires_user_bound_composite(tmp_path):
    record = publisher.EVIDENCE / 'confirmation-record.json'
    reviews = [publisher.EVIDENCE / f'grounding-reviewer-{slot}-human-confirmed.json' for slot in (1, 2)]
    result = publisher.build(record, reviews, publisher.CANDIDATE, publisher.ROOT / 'scripts/check_ac3_prospective_readiness.py')
    publisher.bind_revision(result, publisher.REVISION)
    summary = publisher.bind_reviewed_revision(result, publisher.REVISION, publisher.REVISION_CONFIRMATION,
                                               publisher.COMPOSITE, publisher.FACT_DECLARATIONS)
    assert summary['revision']['review_complete'] is True
    assert summary['revision']['questions'] == summary['revision']['agreed_valid'] == 32
    assert not summary['protocol_frozen'] and not summary['held_out_results_available']
    (tmp_path / 'confirmation-record.json').write_text('{}')
    with pytest.raises(ValueError, match='confirmation'):
        publisher.bind_reviewed_revision(result, publisher.REVISION, tmp_path, publisher.COMPOSITE, publisher.FACT_DECLARATIONS)


def test_reviewed_revision_rejects_relocated_path_outside_output(tmp_path, monkeypatch):
    composite = tmp_path / 'composite'
    shutil.copytree(publisher.COMPOSITE, composite)
    path = composite / 'manifest.json'
    manifest = json.loads(path.read_text())
    original = manifest['inputs'][10]['path']
    assert '/output/' in original
    monkeypatch.setenv('AC3_HOST_PROJECT_ROOT', original.split('/output/', 1)[0])
    monkeypatch.setenv('AC3_OUTPUT_ROOT', str(publisher.ROOT / 'output'))
    manifest['inputs'][10]['path'] = '/different-project/output/forged.json'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='outside the configured project output'):
        publisher.bind_reviewed_revision({'revision': {}}, publisher.REVISION, publisher.REVISION_CONFIRMATION,
                                         composite, publisher.FACT_DECLARATIONS)


def test_expansion_preserves_reviewed_prefix_and_does_not_claim_new_review(tmp_path):
    summary = publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION)
    assert summary['expansion']['reviewed_questions'] == 32
    assert summary['expansion']['new_questions'] == 88
    assert summary['expansion']['proposed_questions'] == 120
    assert summary['expansion']['new_review_complete'] is False
    for name in ('manifest.json', 'candidate-inputs.json', 'proposed-fact-plan.json'):
        shutil.copyfile(publisher.EXPANSION / name, tmp_path / name)
    (tmp_path / 'candidate-inputs.json').write_text((tmp_path / 'candidate-inputs.json').read_text() + ' ')
    with pytest.raises(ValueError, match='Expansion is not bound'):
        publisher.bind_expansion({}, tmp_path, publisher.REVISION)


def test_scoped_repair_is_bound_and_does_not_claim_its_review(tmp_path):
    summary = publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION, publisher.EXPANSION_REPAIR)
    assert summary['expansion']['v5_unchanged_new_histories'] == 12
    assert summary['expansion']['v6_revised_histories'] == 10
    assert summary['expansion']['new_review_complete'] is False
    for name in ('manifest.json', 'candidate-inputs.json', 'proposed-fact-plan.json'):
        shutil.copyfile(publisher.EXPANSION_REPAIR / name, tmp_path / name)
    (tmp_path / 'candidate-inputs.json').write_text((tmp_path / 'candidate-inputs.json').read_text() + ' ')
    with pytest.raises(ValueError, match='Repair is not bound'):
        publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION, tmp_path)


def test_confirmed_v5_reviews_count_only_unchanged_v6_material(tmp_path):
    result = publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v5_unchanged(result, publisher.EXPANSION_V5_CONFIRMED, publisher.REVISION,
        publisher.COMPOSITE, publisher.FACT_DECLARATIONS, publisher.EXPANSION_REPAIR)
    assert result['expansion']['reviewed_histories'] == 20
    assert result['expansion']['reviewed_questions'] == 80
    assert result['expansion']['pending_histories'] == 10
    assert result['expansion']['pending_questions'] == 40
    assert result['expansion']['new_review_complete'] is False
    shutil.copytree(publisher.EXPANSION_V5_CONFIRMED, tmp_path / 'approved')
    altered = tmp_path / 'approved' / 'original-reviewer-1.json'
    altered.write_text(altered.read_text() + ' ')
    with pytest.raises(ValueError, match='differs from user-confirmed'):
        publisher.bind_confirmed_v5_unchanged(result, tmp_path / 'approved', publisher.REVISION,
            publisher.COMPOSITE, publisher.FACT_DECLARATIONS, publisher.EXPANSION_REPAIR)


def test_v7_retains_119_unchanged_questions_and_rejects_tampering(tmp_path):
    result = publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v5_unchanged(result, publisher.EXPANSION_V5_CONFIRMED, publisher.REVISION,
        publisher.COMPOSITE, publisher.FACT_DECLARATIONS, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v6(result, publisher.EXPANSION_V6_CONFIRMED, publisher.EXPANSION_V6_COMPOSITE, publisher.EXPANSION_REPAIR)
    assert result['expansion']['reviewed_questions'] == 120
    publisher.bind_single_question_revision(result, publisher.EXPANSION_V7, publisher.EXPANSION_REPAIR, publisher.EXPANSION_V5_CONFIRMED)
    assert result['expansion']['reviewed_questions'] == 119
    assert result['expansion']['pending_questions'] == 1
    assert result['expansion']['new_review_complete'] is False
    for name in ('manifest.json', 'candidate-inputs.json', 'proposed-fact-plan.json'):
        shutil.copyfile(publisher.EXPANSION_V7 / name, tmp_path / name)
    (tmp_path / 'candidate-inputs.json').write_text((tmp_path / 'candidate-inputs.json').read_text() + ' ')
    with pytest.raises(ValueError, match='does not bind'):
        publisher.bind_single_question_revision(result, tmp_path, publisher.EXPANSION_REPAIR, publisher.EXPANSION_V5_CONFIRMED)


def test_v6_composite_rejects_reference_outside_output(tmp_path, monkeypatch):
    composite = tmp_path / 'composite-v6'
    shutil.copytree(publisher.EXPANSION_V6_COMPOSITE, composite)
    path = composite / 'manifest.json'
    manifest = json.loads(path.read_text())
    original = manifest['inputs'][14]['path']
    monkeypatch.setenv('AC3_HOST_PROJECT_ROOT', original.split('/output/', 1)[0])
    monkeypatch.setenv('AC3_OUTPUT_ROOT', str(publisher.ROOT / 'output'))
    manifest['inputs'][14]['path'] = '/different-project/output/forged.json'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='outside the configured project output'):
        publisher.bind_confirmed_v6({}, publisher.EXPANSION_V6_CONFIRMED, composite, publisher.EXPANSION_REPAIR)


def test_v8_retains_question_reviews_but_keeps_fact_and_edge_pending(tmp_path):
    result = publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v5_unchanged(result, publisher.EXPANSION_V5_CONFIRMED, publisher.REVISION,
        publisher.COMPOSITE, publisher.FACT_DECLARATIONS, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v6(result, publisher.EXPANSION_V6_CONFIRMED, publisher.EXPANSION_V6_COMPOSITE, publisher.EXPANSION_REPAIR)
    publisher.bind_single_question_revision(result, publisher.EXPANSION_V7, publisher.EXPANSION_REPAIR, publisher.EXPANSION_V5_CONFIRMED)
    publisher.bind_confirmed_v7_question(result, publisher.H19_CONFIRMED, publisher.EXPANSION_V7_COMPOSITE, publisher.EXPANSION_V7)
    publisher.bind_v8_pending_fact(result, publisher.EXPANSION_V8, publisher.EXPANSION_V7)
    assert result['expansion']['reviewed_questions'] == 120
    assert result['expansion']['v8_fact_review_pending'] is True
    assert result['expansion']['pending_fact_relationship_count'] == 1
    assert result['expansion']['new_review_complete'] is False
    for name in ('manifest.json', 'candidate-inputs.json', 'proposed-fact-plan.json'):
        shutil.copyfile(publisher.EXPANSION_V8 / name, tmp_path / name)
    with (tmp_path / 'proposed-fact-plan.json').open('a') as stream: stream.write(' ')
    with pytest.raises(ValueError, match='V8 fact revision'):
        publisher.bind_v8_pending_fact(result, tmp_path, publisher.EXPANSION_V7)


def test_v8_user_confirmed_edge_handling_keeps_original_edge_unresolved(tmp_path):
    result = publisher.bind_expansion({}, publisher.EXPANSION, publisher.REVISION, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v5_unchanged(result, publisher.EXPANSION_V5_CONFIRMED, publisher.REVISION,
        publisher.COMPOSITE, publisher.FACT_DECLARATIONS, publisher.EXPANSION_REPAIR)
    publisher.bind_confirmed_v6(result, publisher.EXPANSION_V6_CONFIRMED, publisher.EXPANSION_V6_COMPOSITE, publisher.EXPANSION_REPAIR)
    publisher.bind_single_question_revision(result, publisher.EXPANSION_V7, publisher.EXPANSION_REPAIR, publisher.EXPANSION_V5_CONFIRMED)
    publisher.bind_confirmed_v7_question(result, publisher.H19_CONFIRMED, publisher.EXPANSION_V7_COMPOSITE, publisher.EXPANSION_V7)
    publisher.bind_v8_pending_fact(result, publisher.EXPANSION_V8, publisher.EXPANSION_V7)
    publisher.bind_confirmed_v8_handling(result, publisher.H19_FACT_EDGE_CONFIRMED, publisher.EXPANSION_V8_COMPOSITE, publisher.EXPANSION_V8)
    assert result['expansion']['reviewed_questions'] == 120
    assert result['expansion']['v8_fact_review_pending'] is False
    assert result['expansion']['unresolved_edge_status'] == 'unresolved_not_written_as_confirmed'
    shutil.copytree(publisher.H19_FACT_EDGE_CONFIRMED, tmp_path / 'confirmed')
    (tmp_path / 'confirmed' / 'reviewer-1-user-confirmed.json').write_text('{}')
    with pytest.raises(ValueError, match='differs'):
        publisher.bind_confirmed_v8_handling(result, tmp_path / 'confirmed', publisher.EXPANSION_V8_COMPOSITE, publisher.EXPANSION_V8)
