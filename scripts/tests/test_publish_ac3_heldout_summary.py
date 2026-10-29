"""Synthetic data only; publication must bind all evidence and omit private text."""
import hashlib
import json
import pytest
from scripts import analyze_ac3_heldout as analysis
from scripts.publish_ac3_heldout_summary import build_summary


def test_publication_requires_blind_matching_evidence_and_omits_answers(tmp_path, monkeypatch):
    encode = lambda x: json.dumps(x, sort_keys=True).encode()
    write = lambda name, obj: (tmp_path / name).write_bytes(encode(obj))
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    thresholds = {'failure_detection_recall_min': .75, 'failure_classification_accuracy_min': .8,
                  'test_validity_min': .9, 'false_positive_rate_max': .1}
    frozen = {'frozen_at_utc': '2026-10-28T00:00:00Z', 'protocol': {
        'model_configuration': {f'{role}_provider': 'ollama' for role in ('target', 'evaluator', 'pipeline')},
        'budget': {'max_new_estimated_usd': 0}, 'thresholds': thresholds}}
    write('frozen.json', frozen)
    fd = digest(tmp_path / 'frozen.json')
    answer = 'private fixture answer'
    row = {'test_id': 't1', 'history_id': 'h1', 'response': answer,
           'response_sha256': hashlib.sha256(answer.encode()).hexdigest(),
           'automatic': {'verdict': 'fail', 'failure_dimension': 'accuracy'}}
    run = {'format': 'ac3-heldout-run-export-v1', 'frozen_sha256': fd,
           'frozen_path': str(tmp_path / 'frozen.json'), 'started_at_utc': '2026-10-28T00:01:00Z', 'responses': [row]}
    write('run.json', run); rd = digest(tmp_path / 'run.json')
    write('blind_key.json', {'format': 'ac3-heldout-blind-key-v1', 'frozen_sha256': fd,
                             'run_sha256': rd, 'blind_to_test': {'blind': 't1'}})
    for slot in (1, 2):
        write(f'review_{slot}.json', {'format': 'ac3-heldout-human-review-v1', 'reviewer_slot': slot,
          'run_sha256': rd, 'reviewer_declaration': {'reviewer_label': f'person-{slot}',
          'completed_by_human': True, 'completed_independently': True, 'has_seen_automatic_results': False,
          'used_ai_assistance': False}, 'decisions': [{'blind_id': 'blind', 'response_sha256': row['response_sha256'],
          'verdict': 'fail', 'failure_dimension': 'accuracy', 'rationale': 'private review note'}]})
    monkeypatch.setattr(analysis, 'compile_mock', lambda *args: {'items': [
        {'test_id': 't1', 'history_id': 'h1', 'grounding_review': 'valid'}]})
    names = ('frozen', 'run', 'blind_key', 'review_1', 'review_2')
    paths = {name: tmp_path / f'{name}.json' for name in names}
    digests = {name: digest(path) for name, path in paths.items()}
    result = build_summary(paths, digests)
    assert result['cases'] == 1 and result['acceptance'].startswith('not_assessed')
    assert answer not in json.dumps(result) and 'private review note' not in json.dumps(result)
    paths['review_1'].write_text('{}')
    with pytest.raises(ValueError, match='digest mismatch'):
        build_summary(paths, digests)
