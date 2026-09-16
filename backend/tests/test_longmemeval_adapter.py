"""The LongMemEval-compatible adapter is local and deterministic."""
import json
from pathlib import Path

import pytest

from app.benchmarks.longmemeval import LongMemEvalAdapter


SAMPLE = Path(__file__).resolve().parents[2] / "datasets" / "benchmarks" / "longmemeval-compatible-v1" / "local_sample.json"


def test_local_longmemeval_compatible_sample_adapts_without_network():
    cases, report = LongMemEvalAdapter().adapt(json.loads(SAMPLE.read_text()))
    assert report.adapter_version == "longmemeval-compatible-v1"
    assert report.cases_imported == 2
    assert cases[0].case_id == "LME-SAMPLE-001"
    assert len(cases[0].messages) == 2
    assert cases[1].dimension_hint == "appropriate_use"


def test_adapter_accepts_top_level_array_and_rejects_missing_context():
    cases, _ = LongMemEvalAdapter().adapt([{
        "id": "one", "query": "Where?", "reference_answer": "Sydney",
        "messages": [{"role": "user", "content": "I live in Sydney."}],
    }])
    assert cases[0].messages[0].timestamp.year == 2000
    with pytest.raises(ValueError, match="no usable session"):
        LongMemEvalAdapter().adapt([{"id": "bad", "question": "Q", "answer": "A"}])
