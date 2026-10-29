"""Synthetic fixture: these test reviews are not human evidence."""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from scripts import freeze_ac3_prospective_suite as freeze
from scripts.ac3_fixed_suite_adapter import sha
from scripts.ac3_rehearsal_workflow import Rehearsal

@pytest.fixture
def frozen(tmp_path):
    reviews = []
    for slot in (1, 2):
        data = json.loads((freeze.PACKET / f'grounding-reviewer-{slot}.json').read_text())
        data['reviewer_declaration'] = {'reviewer_label': f'fixture-{slot}', 'completed_by_human': True, 'completed_independently': True, 'used_ai_assistance': False, 'note': 'synthetic test fixture, not human review'}
        for case in data['cases']:
            for question in case['questions']:
                question['review'] = {'question_validity': 'valid', 'rationale': 'synthetic test fixture'}
        p = tmp_path / f'reviewer-{slot}.json'
        p.write_text(json.dumps(data)); reviews.append(p)
    cfg = json.loads((freeze.PACKET / 'protocol-config-template.json').read_text())
    cfg['human_attestations'] = {'pilot_provenance_reviewed': True, 'pilot_thresholds_accepted': True, 'held_out_outputs_not_generated_or_inspected': True, 'exclusions_and_abstention_policy_frozen': True, 'responsible_reviewer': 'fixture only', 'provenance_note': 'fixture only'}
    cfg['model_configuration'] = {'target_provider': 'ollama', 'target_model': 'fixture', 'evaluator_provider': 'ollama', 'evaluator_model': 'fixture', 'pipeline_provider': 'ollama', 'pipeline_model': 'fixture', 'pipeline_version': 'fixture', 'evaluator_implementation_version': 'fixture-evaluator', 'pipeline_implementation_version': 'fixture-pipeline', 'target_strategy': 'fixture'}
    cfg['budget']['max_new_estimated_usd'] = 0
    cfg.update({'minimum_decided_coverage': 0.8, 'minimum_human_failure_count': 8, 'minimum_human_pass_count': 8, 'minimum_independent_histories': 8, 'abstention_policy': 'fixture', 'exclusion_policy': 'fixture', 'budget_enforcement_plan': 'fixture', 'reference_blinding_plan': 'fixture'})
    config = tmp_path / 'config.json'; config.write_text(json.dumps(cfg))
    output = tmp_path / 'frozen.json'
    proc = subprocess.run([sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'), '--review-1', str(reviews[0]), '--review-2', str(reviews[1]), '--config', str(config), '--output', str(output)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return output, sha(output.read_bytes()), reviews


def test_full_rehearsal_has_blinding_and_distinct_reviewers(frozen):
    path, digest, _ = frozen
    run = Rehearsal(path, digest)
    with pytest.raises(ValueError): run.summary()
    with pytest.raises(ValueError): run.record_fixtures({})
    run.record_fixtures({test: 'Synthetic response' for test in run.items})
    packet = run.review_packet()
    assert len(packet['answers']) == 32
    assert not any('test_id' in answer or 'reviewer' in answer for answer in packet['answers'])
    decisions = {a['blind_id']: 'pass' for a in packet['answers']}
    run.submit_fixture_review('One', decisions)
    with pytest.raises(ValueError): run.submit_fixture_review(' one ', decisions)
    changed = dict(decisions); changed[next(iter(changed))] = 'uncertain'
    run.submit_fixture_review('Two', changed)
    summary = run.summary()
    assert summary['agreement_count'] == 31 and summary['disagreement_count'] == 1
    assert summary['pass'] == 31 and summary['model_called'] is False
    with pytest.raises(ValueError): run.record_fixtures({})


def test_changed_review_source_blocks_every_transition(frozen):
    path, digest, reviews = frozen
    run = Rehearsal(path, digest)
    reviews[0].write_text('{}')
    with pytest.raises(ValueError, match='source file changed'):
        run.record_fixtures({test: 'Synthetic response' for test in run.items})


def test_changed_response_blocks_review(frozen):
    path, digest, _ = frozen
    run = Rehearsal(path, digest)
    run.record_fixtures({test: 'Synthetic response' for test in run.items})
    run.responses[next(iter(run.responses))] = 'tampered'
    with pytest.raises(ValueError, match='responses changed'):
        run.review_packet()


def test_checkpoint_restarts_blind_review_and_refuses_overwrite(frozen, tmp_path):
    path, digest, _ = frozen
    run = Rehearsal(path, digest)
    run.record_fixtures({test: 'Synthetic response' for test in run.items})
    packet_path = tmp_path / 'blind.json'
    run.export_review_packet(packet_path)
    packet = json.loads(packet_path.read_text())
    decisions = {answer['blind_id']: 'pass' for answer in packet['answers']}
    run.submit_fixture_review('One', decisions)
    checkpoint = tmp_path / 'checkpoint.json'
    checkpoint_sha = run.save_checkpoint(checkpoint)
    with pytest.raises(FileExistsError):
        run.save_checkpoint(checkpoint)
    with pytest.raises(FileExistsError):
        run.export_review_packet(packet_path)
    restored = Rehearsal.restore_checkpoint(checkpoint, checkpoint_sha, path, digest)
    assert restored.review_packet() == packet
    restored.submit_fixture_review('Two', decisions)
    assert restored.summary()['pass'] == 32
    complete = tmp_path / 'complete.json'
    complete_sha = restored.save_checkpoint(complete)
    assert Rehearsal.restore_checkpoint(complete, complete_sha, path, digest).summary() == restored.summary()


def test_checkpoint_digest_and_sources_cannot_be_tampered(frozen, tmp_path):
    path, digest, reviews = frozen
    run = Rehearsal(path, digest)
    run.record_fixtures({test: 'Synthetic response' for test in run.items})
    checkpoint = tmp_path / 'checkpoint.json'
    checkpoint_sha = run.save_checkpoint(checkpoint)
    with pytest.raises(ValueError, match='digest mismatch'):
        Rehearsal.restore_checkpoint(checkpoint, '0' * 64, path, digest)
    value = json.loads(checkpoint.read_text())
    value['responses'][next(iter(value['responses']))] = 'altered'
    checkpoint.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='digest mismatch'):
        Rehearsal.restore_checkpoint(checkpoint, checkpoint_sha, path, digest)
    second = tmp_path / 'second.json'
    second_sha = run.save_checkpoint(second)
    reviews[0].write_text('{}')
    with pytest.raises(ValueError, match='source file changed'):
        Rehearsal.restore_checkpoint(second, second_sha, path, digest)
