"""End-to-end pilot smoke checks use an isolated database and no cloud calls."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_study_separates_splits_preserves_results_and_exports_review_queue(tmp_path):
    command = [sys.executable, str(ROOT / 'scripts/run_repair_study.py'), '--offline', '--execute',
               '--database-url', f'sqlite:///{tmp_path / "study.db"}', '--output', str(tmp_path / 'output'), '--max-runs', '30']
    held_first = subprocess.run([*command, '--split', 'held_out'], capture_output=True, text=True, timeout=30)
    assert held_first.returncode != 0
    assert 'Finish diagnostic runs' in held_first.stderr
    for split in ('diagnostic', 'held_out'):
        result = subprocess.run([*command, '--split', split], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    output = json.loads((tmp_path / 'output/study-results.json').read_text())
    assert len(output['runs']) == 30
    assert all('result' in run for run in output['runs'])
    assert {run['split'] for run in output['runs']} == {'diagnostic', 'held_out'}
    assert output['human_validation'] == 'pending'
    assert output['before_after_comparisons']
    queue = json.loads((tmp_path / 'output/human-review-queue.json').read_text())
    assert len(queue) == 120
    assert all(item['human_review_status'] == 'pending' for item in queue)
    frozen = (tmp_path / 'output/study-results.json').read_bytes()
    repeated = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert repeated.returncode == 0, repeated.stderr
    assert '"executed_this_call": 0' in repeated.stdout
    assert (tmp_path / 'output/study-results.json').read_bytes() == frozen


def test_changed_frozen_implementation_is_rejected_before_collection(tmp_path):
    study = json.loads((ROOT / 'datasets/studies/independent-repair-v1/study.json').read_text())
    study['expected_implementation_fingerprint_sha256'] = '0' * 64
    source = tmp_path / 'changed-study.json'
    source.write_text(json.dumps(study))
    result = subprocess.run([
        sys.executable, str(ROOT / 'scripts/run_repair_study.py'), '--study', str(source),
        '--offline', '--prepare', '--database-url', f'sqlite:///{tmp_path / "study.db"}',
        '--output', str(tmp_path / 'output'),
    ], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'Frozen implementation changed' in result.stderr
    assert not (tmp_path / 'output').exists()


def test_new_validation_sources_and_generic_control_are_declared():
    study = json.loads((ROOT / 'datasets/studies/independent-repair-v1/study.json').read_text())
    old = json.loads((ROOT / 'datasets/studies/qwen-repair-v4/study.json').read_text())
    previous_messages = {m['content'] for s in old['scenarios'] for m in s['messages']}
    assert study['primary_comparison'] == {'before': 'strong_score_based', 'after': 'scope_aware'}
    assert len(study['scenarios']) == 4
    assert study['repetitions']['held_out'] == 3
    for scenario in study['scenarios']:
        assert scenario['split'] == 'held_out'
        assert not scenario['novelty']['used_for_policy_tuning']
        # Familiar preference vocabulary is permitted; the source histories,
        # project-specific facts, ordering and distractors must be new.
        assert sum(m['content'] not in previous_messages for m in scenario['messages']) >= 8
        assert scenario['messages'] not in [s['messages'] for s in old['scenarios']]
        messages = {m['message_id']: m for m in scenario['messages']}
        for memory in scenario['gold_memories']:
            assert memory['source_message_ids']
            for source in memory['source_message_ids']:
                assert messages[source]['role'] == 'user'
                assert memory['canonical_value'] in messages[source]['content']
        assert {t['dimension'] for t in scenario['gold_tests']} == {'accuracy', 'freshness', 'appropriate_use', 'conflict_resolution'}
