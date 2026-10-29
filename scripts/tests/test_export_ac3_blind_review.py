"""Synthetic materials only; never evidence of a human review."""
import copy
import pytest
from scripts import export_ac3_blind_review as exporter, analyze_ac3_heldout as analyzer
from scripts.tests.test_analyze_ac3_heldout import fixture_data


def fixture(monkeypatch):
    frozen, run, key, reviews = fixture_data(monkeypatch)
    frozen['suite'] = {'cases': [{'history_id': f'history-{n}', 'source_messages': [{'text': f'Source {n}'}]} for n in range(2)]}
    run['frozen_path'] = 'fixture-frozen'
    monkeypatch.setattr(exporter, '_read_bound', lambda p, d: frozen if str(p) == 'fixture-frozen' else run)
    monkeypatch.setattr(exporter, 'compile_mock', lambda *args: {'items': [
        {'test_id': f'test-{n}', 'history_id': f'history-{n}', 'grounding_review': 'valid',
         'question': f'Question {n}', 'expected_behavior': f'Expected {n}'} for n in range(2)]})
    return frozen, run


def test_blind_packet_excludes_automated_verdicts_and_templates_are_blank(monkeypatch):
    fixture(monkeypatch)
    key, packet, first, second = exporter.make_materials('fixture-frozen', 'f' * 64, 'run', 'a' * 64)
    assert set(key['blind_to_test']) == {row['blind_id'] for row in packet['cases']}
    assert all(set(row) == {'blind_id', 'question', 'source_history', 'expected_behavior', 'answer', 'response_sha256'} for row in packet['cases'])
    assert all(row['verdict'] is None for row in first['decisions'] + second['decisions'])
    assert not first['reviewer_declaration']['completed_by_human']
    assert first['reviewer_slot'] == 1 and second['reviewer_slot'] == 2


def test_changed_answer_rejected(monkeypatch):
    _, run = fixture(monkeypatch)
    run['responses'][0]['response'] = 'tampered'
    with pytest.raises(ValueError, match='digest mismatch'):
        exporter.make_materials('fixture-frozen', 'f' * 64, 'run', 'a' * 64)


def test_export_and_calculation_with_synthetic_reviewer_responses(monkeypatch):
    frozen, run = fixture(monkeypatch)
    key, packet, first, second = exporter.make_materials('fixture-frozen', 'f' * 64, 'run', 'a' * 64)
    for slot, review in enumerate((first, second), 1):
        review['reviewer_declaration'] = {'reviewer_label': f'fixture-{slot}', 'completed_by_human': True,
            'completed_independently': True, 'has_seen_automatic_results': False, 'used_ai_assistance': False}
        for row in review['decisions']:
            test = key['blind_to_test'][row['blind_id']]
            row.update(verdict='fail' if test == 'test-0' else 'pass',
                       failure_dimension='accuracy' if test == 'test-0' else None, rationale='synthetic fixture')
    result = analyzer.analyze(frozen, 'f' * 64, run, key, [first, second])
    assert result['automatic']['tp'] == 1
    assert result['automatic']['abstain_reference_pass'] == 1
    assert result['acceptance'].startswith('not_assessed')
