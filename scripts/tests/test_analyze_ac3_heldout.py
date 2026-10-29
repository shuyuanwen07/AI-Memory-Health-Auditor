"""Synthetic test inputs only; these are not human labels or empirical results."""
import copy
import hashlib
import json
import pytest
from scripts import analyze_ac3_heldout as tool


def fixture_data(monkeypatch):
    questions = [dict(test_id=f'test-{n}', history_id=f'history-{n}', grounding_review='valid') for n in range(2)]
    monkeypatch.setattr(tool, 'compile_mock', lambda *args: {'items': questions})
    frozen = {'frozen_at_utc': '2026-10-28T00:00:00Z', 'protocol': {'model_configuration': {f'{role}_provider': 'ollama' for role in ('target', 'evaluator', 'pipeline')}, 'budget': {'max_new_estimated_usd': 0}, 'thresholds': {'failure_detection_recall_min': 0.75}}}
    answers = ['fixture answer one', 'fixture answer two']
    responses = [dict(test_id=f'test-{n}', history_id=f'history-{n}', response=text, response_sha256=hashlib.sha256(text.encode()).hexdigest(), automatic={'verdict': 'fail' if n == 0 else 'uncertain', 'failure_dimension': 'accuracy' if n == 0 else None}) for n, text in enumerate(answers)]
    run = {'format': 'ac3-heldout-run-export-v1', 'frozen_sha256': 'f' * 64, 'frozen_path': 'fixture', 'started_at_utc': '2026-10-28T00:01:00Z', 'responses': responses}
    key = {'format': 'ac3-heldout-blind-key-v1', 'frozen_sha256': 'f' * 64, 'run_sha256': 'a' * 64, 'blind_to_test': {'blind-1': 'test-0', 'blind-2': 'test-1'}}
    documents = []
    for slot in (1, 2):
        declaration = {'reviewer_label': f'fixture-{slot}', 'completed_by_human': True, 'completed_independently': True, 'has_seen_automatic_results': False, 'used_ai_assistance': False}
        decisions = [dict(blind_id=f'blind-{n + 1}', response_sha256=r['response_sha256'], verdict='fail' if n == 0 else 'pass', failure_dimension='accuracy' if n == 0 else None, rationale='fixture only') for n, r in enumerate(responses)]
        documents.append({'format': 'ac3-heldout-human-review-v1', 'reviewer_slot': slot, 'run_sha256': 'a' * 64, 'reviewer_declaration': declaration, 'decisions': decisions})
    return frozen, run, key, documents


def test_counts_and_non_acceptance(monkeypatch):
    frozen, run, key, documents = fixture_data(monkeypatch)
    result = tool.analyze(frozen, 'f' * 64, run, key, documents)
    assert result['metrics']['failure_recall_conservative']['value'] == 1
    assert result['metrics']['decided_coverage']['value'] == .5
    assert result['metrics']['false_positive_rate_decided']['value'] is None
    assert result['acceptance'].startswith('not_assessed')


def test_predeclared_sample_minimums_are_not_silently_passed(monkeypatch):
    frozen, run, key, documents = fixture_data(monkeypatch)
    frozen['protocol'].update({'minimum_decided_coverage': .8, 'minimum_human_pass_count': 30,
                               'minimum_human_failure_count': 30, 'minimum_independent_histories': 8})
    result = tool.analyze(frozen, 'f' * 64, run, key, documents)
    assert result['evidence_sufficiency']['status'] == 'insufficient'
    assert result['evidence_sufficiency']['checks']['human_failures']['met'] is False
    assert result['evidence_sufficiency']['checks']['history_coverage']['observed'] == 2


def test_history_coverage_requires_agreed_human_reference(monkeypatch):
    frozen, run, key, documents = fixture_data(monkeypatch)
    frozen['protocol'].update({'minimum_decided_coverage': .1, 'minimum_human_pass_count': 1,
                               'minimum_human_failure_count': 1, 'minimum_independent_histories': 2})
    documents[1]['decisions'][1]['verdict'] = 'uncertain'
    result = tool.analyze(frozen, 'f' * 64, run, key, documents)
    assert result['source_histories_with_valid_tests'] == 2
    assert result['evidence_sufficiency']['checks']['history_coverage']['observed'] == 1
    assert result['evidence_sufficiency']['status'] == 'insufficient'


def test_changed_answer_and_duplicate_review_rejected(monkeypatch):
    frozen, run, key, documents = fixture_data(monkeypatch)
    run['responses'][0]['response'] = 'tampered'
    with pytest.raises(ValueError, match='digest mismatch'): tool.analyze(frozen, 'f' * 64, run, key, documents)
    frozen, run, key, documents = fixture_data(monkeypatch)
    documents[1]['reviewer_declaration']['reviewer_label'] = ' FIXTURE-1 '
    with pytest.raises(ValueError, match='Distinct reviewer'): tool.analyze(frozen, 'f' * 64, run, key, documents)


def test_nonblind_and_prefreeze_run_rejected(monkeypatch):
    frozen, run, key, documents = fixture_data(monkeypatch)
    documents[1]['reviewer_declaration']['has_seen_automatic_results'] = True
    with pytest.raises(ValueError, match='independent blind'): tool.analyze(frozen, 'f' * 64, run, key, documents)
    frozen, run, key, documents = fixture_data(monkeypatch)
    run['started_at_utc'] = '2026-10-27T23:00:00Z'
    with pytest.raises(ValueError, match='after protocol'): tool.analyze(frozen, 'f' * 64, run, key, documents)


def test_evidence_digest_binding(tmp_path):
    path = tmp_path / 'input.json'
    path.write_text(json.dumps({'fixture': True}))
    with pytest.raises(ValueError, match='digest mismatch'): tool._read_bound(path, '0' * 64)
