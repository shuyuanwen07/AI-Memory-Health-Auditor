"""Check the actual frozen semantic study has no reviewer labels or arm in model inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'output/ac3-generated/semantic-scope-pilot-20261029-v1'


def test_frozen_inputs_exclude_review_labels_and_arm():
    raw = (STUDY / 'inputs.json').read_bytes()
    protocol = json.loads((STUDY / 'protocol.json').read_bytes())
    assert hashlib.sha256(raw).hexdigest() == protocol['inputs_sha256']
    inputs = json.loads(raw)
    assert len(inputs) == 33 and len({x['blind_id'] for x in inputs}) == 33
    for row in inputs:
        assert set(row['input']) == {'source_messages', 'question', 'expected_behavior'}
        assert not ({'human_consensus', 'reviewer_declaration', 'arm', 'gate_status', 'decision'} & set(row['input']))
        assert all(set(m) <= {'message_id', 'role', 'content', 'timestamp'} for m in row['input']['source_messages'])


def test_all_dispatches_have_exactly_one_preserved_response():
    inputs = json.loads((STUDY / 'inputs.json').read_bytes())
    ids = {row['blind_id'] for row in inputs}
    assert {p.stem for p in (STUDY / 'requests').glob('*.json')} == ids
    assert {p.stem for p in (STUDY / 'responses').glob('*.json')} == ids
    for bid in ids:
        x = json.loads((STUDY / 'responses' / (bid + '.json')).read_bytes())
        assert x['blind_id'] == bid
        assert x['verdict'] in {'valid', 'invalid', 'uncertain'}
        if x['status'] != 'settled':
            assert x['verdict'] == 'uncertain'
