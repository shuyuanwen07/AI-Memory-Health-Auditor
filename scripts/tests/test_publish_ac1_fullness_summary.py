import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from scripts import publish_ac1_fullness_summary as publish


def test_aggregates_omit_private_judgments_and_reject_changed_source(tmp_path, monkeypatch):
    summary = publish.build()
    assert summary['complete_29_histories']['full'] == 210
    assert summary['complete_29_histories']['unresolved'] == 1
    assert 'items' not in summary
    source = publish.BASE
    for name in ('confirmation.json', 'ac1-fullness-reviewer-1.json', 'ac1-fullness-reviewer-2.json'):
        shutil.copy2(source / name, tmp_path / name)
    review_path = tmp_path / 'ac1-fullness-reviewer-1.json'
    review = json.loads(review_path.read_bytes())
    review['histories'][0]['source_messages'][0]['text'] += ' altered'
    review_path.write_text(json.dumps(review, ensure_ascii=False))
    confirmation_path = tmp_path / 'confirmation.json'
    confirmation = json.loads(confirmation_path.read_bytes())
    item = next(x for x in confirmation['items'] if x['kind'] == 'ac1-fullness' and x['slot'] == 1)
    item['confirmed_sha256'] = hashlib.sha256(review_path.read_bytes()).hexdigest()
    confirmation_path.write_text(json.dumps(confirmation, ensure_ascii=False))
    monkeypatch.setattr(publish, 'BASE', tmp_path)
    with pytest.raises(subprocess.CalledProcessError):
        publish.build()
