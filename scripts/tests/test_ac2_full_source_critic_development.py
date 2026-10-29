import json
import pytest
from scripts import run_ac2_full_source_critic_development_20261030 as probe


def test_freeze_and_no_repeat_after_unknown_failure(tmp_path, monkeypatch):
    source, out = tmp_path/'source.json', tmp_path/'run'
    items = [{'review_item_id': f'Q{i:02}', 'source_messages': [], 'question': 'Q?', 'reference_answer': 'A'} for i in range(24)]
    source.write_text(json.dumps({'items': items}))
    monkeypatch.setattr(probe, 'SOURCE', source); monkeypatch.setattr(probe, 'OUT', out)
    class FakeClient:
        def __init__(self, *_): self.calls = 0; self.last_execution = None
        def complete_json(self, **kwargs):
            self.calls += 1; self.last_execution = {'status': 'recorded'}
            if self.calls == 2: raise RuntimeError('unknown outcome')
            return {**{k: 'valid' for k in probe.FIELDS}, 'notes': 'Checked.'}
    monkeypatch.setattr(probe, 'PipelineLLMClient', FakeClient)
    probe.freeze(); probe.run()
    rows = json.loads((out/'ledger.json').read_text())['rows']
    assert len(rows) == 24 and rows[1]['state'] == 'failed'
    assert sum(x['state'] == 'returned' for x in rows) == 23
    with pytest.raises(ValueError, match='Ledger exists'):
        probe.run()
