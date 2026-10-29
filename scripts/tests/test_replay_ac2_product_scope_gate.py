"""Exercise the observed-study replay without writing an output or calling a model."""
import copy
import json
from pathlib import Path

import pytest

from scripts.replay_ac2_product_scope_gate import FILES, ROOT, apply_gate, replay


def materials():
    return {name: json.loads((ROOT / path).read_bytes()) for name, path in FILES.items()}


def test_route_semantics_keep_rejected_and_require_review_when_warned():
    assert apply_gate('accepted', 'warning') == 'pending'
    assert apply_gate('accepted', None) == 'accepted'
    assert apply_gate('pending', None) == 'pending'
    assert apply_gate('rejected', 'warning') == 'rejected'
    with pytest.raises(ValueError):
        apply_gate('unknown', None)


def test_full_source_bound_replay_reconciles_and_does_not_modify_inputs():
    source = materials()
    before = copy.deepcopy(source)
    result = replay(source)
    assert source == before
    assert result['matched'] == 228
    assert result['unmatched'] == []
    for arm in ('baseline', 'candidate'):
        c = result['arms'][arm]
        assert c['matched'] == c['human_valid'] + c['human_invalid'] + c.get('human_uncertain', 0)
        for status in ('valid', 'invalid'):
            assert sum(c.get(f'{status}_after_{s}', 0) for s in ('accepted', 'pending', 'rejected')) == c[f'human_{status}']


def test_changed_blind_packet_is_refused():
    source = materials()
    source['packet']['cases'][0]['prompt'] += ' added text'
    with pytest.raises(ValueError, match='frozen allocation'):
        replay(source)


def test_mismatch_of_raw_original_test_is_explicitly_unmatched():
    source = materials()
    case = source['packet']['cases'][0]
    meta = source['allocation']['items'][case['blind_id']]
    rows = source['raw_output']['conditions'][meta['condition']]
    history = next(r for r in rows if r['history_id'] == meta['history_id'])
    history['tests'][meta['row_index']]['test']['expected_behavior'] = 'changed'
    result = replay(source)
    assert result['matched'] == 227
    assert result['unmatched'] == [{'blind_id': case['blind_id'], 'reason': 'Prompt or expected behavior differs from frozen raw output'}]
