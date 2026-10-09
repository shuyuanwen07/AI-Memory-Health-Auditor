"""Synthetic contract fixtures only; no human annotation evidence is created."""
from copy import deepcopy
import json
import pytest
from scripts.build_reliability_review_pack import build
from scripts.assemble_reliability_pilot import assemble


@pytest.fixture
def packet(tmp_path):
    source = {
        'human_labels': 0,
        'sources': {'C1': {
            'messages': [{'id': 'MSG1', 'role': 'user', 'content': 'I prefer Python.', 'timestamp': '2026-10-09T00:00:00Z'}],
            'candidates': [{'id': 'M1', 'canonical_value': 'I prefer Python', 'source_message_ids': ['MSG1']},
                           {'id': 'M2', 'canonical_value': 'Java required for assignment', 'source_message_ids': ['MSG1']}],
            'relationships': [{'memory_id': 'M2', 'target_memory_id': 'M1', 'relationship_type': 'CONTEXTUAL_OVERRIDE'}],
        }},
        'runs': [{'audit': {'id': 'PRIVATE-RUN', 'conversation_id': 'C1', 'model': 'PRIVATE-MODEL'},
                  'tests': [{'id': 'T1', 'prompt': 'What do I prefer?', 'expected_behavior': 'Python', 'supporting_memory_ids': ['M1']}],
                  'responses': [{'id': 'R1', 'test_id': 'T1', 'response_text': 'Python'}],
                  'evaluations': [{'test_id': 'T1', 'passed': True, 'reason': 'PRIVATE-REASON'}]}],
    }
    manifest = build(source, tmp_path)
    original = json.loads((tmp_path / 'reviewer-A.json').read_text())
    text = (tmp_path / 'reviewer-A.json').read_text()
    assert not any(secret in text for secret in ['PRIVATE-RUN', 'PRIVATE-MODEL', 'PRIVATE-REASON'])
    assert manifest['human_labels'] == 0 and not manifest['held_out']
    assert all(item['label'] is None for item in original['items'])
    return original


def human_contract_fixture(packet):
    returned = deepcopy(packet)
    returned['reviewer'] = 'synthetic-test-person-a'
    returned['completed_independently_by_human'] = True
    return returned


def test_blank_ai_draft_cannot_be_assembled_as_human_labels(packet):
    with pytest.raises(ValueError, match='human completion'):
        assemble(packet, packet)


@pytest.mark.parametrize('change', ['source', 'question', 'duplicated_item', 'different_version'])
def test_changed_evidence_is_rejected_before_labels_can_be_used(packet, change):
    returned = human_contract_fixture(packet)
    if change == 'source':
        returned['contexts']['Scenario 1']['messages'][0]['text'] = 'Changed'
    elif change == 'question':
        item = next(item for item in returned['items'] if item['task'] == 'test_validity')
        item['evidence']['question'] = 'Changed'
    elif change == 'duplicated_item':
        returned['items'][-1] = deepcopy(returned['items'][0])
    else:
        returned['dataset_version'] = 'different'
    with pytest.raises(ValueError):
        assemble(packet, returned)


def test_partial_labels_stay_partial_and_require_source_notes(packet):
    returned = human_contract_fixture(packet)
    item = returned['items'][0]
    item['label'] = 'include'
    with pytest.raises(ValueError, match='decision note'):
        assemble(packet, returned)
    item['decision_note'] = 'Synthetic contract fixture: source message 1.'
    result = assemble(packet, returned)
    assert len(result['labels']) == 1
    assert len(returned['items']) > 1
    assert packet['items'][0]['label'] is None
    item['label'] = 'pass'
    with pytest.raises(ValueError, match='Invalid label'):
        assemble(packet, returned)
