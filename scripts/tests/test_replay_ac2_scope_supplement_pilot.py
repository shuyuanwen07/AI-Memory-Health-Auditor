"""The independent pilot replay must retain provenance and unresolved cases."""
import copy
import json
from pathlib import Path

import pytest

from scripts.replay_ac2_scope_supplement_pilot import replay


def _inputs():
    study = Path('output/proposal-delivery/ac2-source-supplement-paired-20261029-v1')
    returned = Path('output/proposal-delivery/ac2-source-supplement-review-return-20261029-v1/user-confirmed')
    return (json.loads((study/'protocol.json').read_bytes()),
            json.loads((study/'private/material.json').read_bytes()),
            json.loads((study/'private/key.json').read_bytes()),
            [json.loads((returned/f'reviewer-{i}.json').read_bytes()) for i in (1, 2)],
            json.loads((returned/'confirmation.json').read_bytes()))


def test_pilot_reconstructs_every_question_and_preserves_disagreements():
    result = replay(*_inputs())
    assert result['matched'] == 33 and result['unmatched'] == []
    assert sum(row['human_consensus'] == 'unresolved' for row in result['items']) == 5
    assert sum(arm.get('invalid_after_accepted', 0) for arm in result['arms'].values()) == 0
    assert sum(arm.get('valid_after_pending', 0) for arm in result['arms'].values()) == 13
    assert 'did not save' in result['limitations'][0]


def test_refuses_changed_original_question():
    protocol, material, key, reviews, confirmation = _inputs()
    material = copy.deepcopy(material)
    material['questions'][0]['prompt'] += ' Altered.'
    with pytest.raises(ValueError):
        replay(protocol, material, key, reviews, confirmation)
