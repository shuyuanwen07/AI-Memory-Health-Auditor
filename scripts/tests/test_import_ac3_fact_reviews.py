"""Uses actual v2 packet layout with only synthetic test declarations."""
import copy
import json
from pathlib import Path
import pytest
from scripts.import_ac3_fact_reviews import convert
from scripts.ac3_reviewed_fact_map import validate_fact_plan

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / 'output/proposal-delivery/ac3-fact-review-draft-2026-10-28-v2'
SOURCE = ROOT / 'output/proposal-delivery/ac3-prospective-inputs-2026-10-28-v3/candidate-inputs.json'

@pytest.fixture
def reviewed():
    suite = SOURCE.read_bytes(); plan = (PACKET / 'proposed-fact-plan.json').read_bytes()
    packets = [json.loads((PACKET / f'reviewer-{i}.json').read_text()) for i in (1, 2)]
    for i, packet in enumerate(packets, 1):
        packet['reviewer_declaration'].update({'reviewer_label': f'synthetic-{i}', 'completed_by_human': True,
            'completed_independently': True, 'used_ai_assistance': False})
        for history in packet['histories']: history['review']['decision'] = 'accept'
    return suite, plan, packets


def encode(packets): return [json.dumps(p, ensure_ascii=False).encode() for p in packets]


def test_complete_v2_layout_converts_to_freeze_declarations(reviewed):
    suite, plan, packets = reviewed
    result = convert(suite, plan, encode(packets))
    assert len(result) == 2 and result[0]['reviewed_fact_and_relation_semantics'] is True
    assert result[0]['reviewer_label'] == 'synthetic-1'
    verified = validate_fact_plan(json.loads(suite), json.loads(plan), result)
    assert verified['history_count'] == 8 and not verified['database_snapshot_checked']


@pytest.mark.parametrize('decision', ['revise', 'uncertain', None])
def test_unaccepted_history_never_converts(reviewed, decision):
    suite, plan, packets = reviewed
    packets[0]['histories'][3]['review']['decision'] = decision
    with pytest.raises(ValueError, match='Every history must be accepted'):
        convert(suite, plan, encode(packets))


@pytest.mark.parametrize('field,value', [('completed_by_human', None), ('completed_independently', False), ('used_ai_assistance', None), ('reviewer_label', '')])
def test_explicit_reviewer_declarations_required(reviewed, field, value):
    suite, plan, packets = reviewed
    packets[0]['reviewer_declaration'][field] = value
    with pytest.raises(ValueError): convert(suite, plan, encode(packets))


def test_duplicate_reviewers_and_changed_presented_material_are_rejected(reviewed):
    suite, plan, packets = reviewed
    changed = copy.deepcopy(packets)
    changed[1]['reviewer_declaration']['reviewer_label'] = ' SYNTHETIC-1 '
    with pytest.raises(ValueError, match='different'): convert(suite, plan, encode(changed))
    changed = copy.deepcopy(packets)
    changed[0]['histories'][0]['proposed_facts'][0]['canonical_value'] = 'tampered'
    with pytest.raises(ValueError, match='different from the exact source'): convert(suite, plan, encode(changed))


def test_blank_original_packets_never_convert():
    suite = SOURCE.read_bytes(); plan = (PACKET / 'proposed-fact-plan.json').read_bytes()
    packets = [(PACKET / f'reviewer-{i}.json').read_bytes() for i in (1, 2)]
    with pytest.raises(ValueError): convert(suite, plan, packets)
