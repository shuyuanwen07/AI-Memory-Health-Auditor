"""Guard the frozen selected A triplets against mismatched reviews and tampering."""
import json
import shutil
from pathlib import Path

import pytest

from scripts import analyze_a_diverse_ai_readiness as analysis


@pytest.fixture
def study(tmp_path, monkeypatch):
    source = analysis.STUDY
    for name in ('private/pairing-selection.json','private/key.json','pairing-addendum.json',
                 'generated-draft.json','independent-ai-selected-ai-review-v5.json',
                 'ai-review/ai-reviewer-2-completed.json','ai-review/ai-reviewer-2.json'):
        dest = tmp_path / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, dest)
    monkeypatch.setattr(analysis, 'STUDY', tmp_path)
    return tmp_path


def test_four_dimension_readiness_requires_all_four(study):
    result=analysis.analyze()
    assert result['selected_triplets']==107
    assert result['retained_triplets']==8
    assert result['retained_histories']==8
    assert result['dimension_distribution']['conflict_resolution']['retained']==8
    assert result['supports_four_dimension_comparison'] is False
    assert result['review_type']=='two AI reviews, not human validation'


def test_frozen_triplet_tampering_is_rejected(study):
    path=study/'private/pairing-selection.json'; data=json.loads(path.read_text())
    data['selected_triplets'][0]['dimension']='accuracy'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='binding mismatch'):
        analysis.analyze()
