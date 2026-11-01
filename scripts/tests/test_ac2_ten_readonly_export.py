"""Recovery serialization retains structured traces and rejects unknown types."""
import json
import sys
from pathlib import Path

import pytest

from scripts.inspect_ac2_ten_saved_results_20261101 import model_json_default


def test_saved_target_memory_trace_serializes_as_structured_json_without_db_imports(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'backend'))
    database_modules_before = {name for name in sys.modules if name.startswith('app.database')}
    from app.schemas.domain import TargetMemoryTrace

    trace = TargetMemoryTrace(run_id='saved-run', memory_strategy='relationship_packet',
                              memory_maintenance_policy='update_aware_consolidation')
    exported = json.loads(json.dumps({'trace': trace}, default=model_json_default))
    assert exported['trace']['run_id'] == 'saved-run'
    assert exported['trace']['memory_strategy'] == 'relationship_packet'
    assert exported['trace']['records'] == []
    assert {name for name in sys.modules if name.startswith('app.database')} == database_modules_before


def test_unknown_object_is_rejected_instead_of_silently_stringified():
    class UnrecognisedEvidence:
        def model_dump(self, **_kwargs):
            return {'unverified': 'not a Pydantic model'}

    with pytest.raises(TypeError, match='Unsupported read-only evidence type: UnrecognisedEvidence'):
        json.dumps({'trace': UnrecognisedEvidence()}, default=model_json_default)
