"""Offline contracts for the local LongMemEval-compatible runner."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.main import app
from app.schemas.benchmark import LongMemEvalRunRequest
from app.schemas.domain import MemoryStrategy


SAMPLE = Path(__file__).resolve().parents[2] / "datasets" / "benchmarks" / "longmemeval-compatible-v1" / "local_sample.json"
PAYLOAD = json.loads(SAMPLE.read_text())


def test_runner_is_deterministic_isolated_and_maps_dimensions():
    request = LongMemEvalRunRequest(
        payload=PAYLOAD,
        source_authorised=True,
        source_label="synthetic-local-sample",
        memory_strategy=MemoryStrategy.STRONG_RULE_BASED,
    )
    first = LongMemEvalDeterministicRunner().run(request)
    second = LongMemEvalDeterministicRunner().run(request)

    assert first == second
    assert first.metadata.run_id.startswith("LME-RUN-")
    assert first.metadata.execution_mode.startswith("local-in-memory")
    assert "not official LongMemEval scores" in first.metadata.notice
    assert first.tests_total == 2
    assert first.tests_passed == 2
    assert [item.dimension.value for item in first.cases] == ["freshness", "appropriate_use"]
    assert first.cases[0].retrieved_memory_ids
    assert any(item.lifecycle_state == "SUPERSEDED" for item in first.cases[0].retrieval_evidence)
    dimensions = {item.key: item for item in first.dimensions}
    assert dimensions["freshness"].percentage == 100.0
    assert dimensions["conflict_resolution"].percentage is None


def test_weak_policy_reveals_stale_and_contextual_baseline_failures():
    result = LongMemEvalDeterministicRunner().run(LongMemEvalRunRequest(
        payload=PAYLOAD,
        source_authorised=True,
        memory_strategy=MemoryStrategy.WEAK_FIRST_HIT,
    ))
    assert result.tests_passed == 0
    assert result.cases[0].response_text.endswith("I used MySQL before.")
    assert result.cases[1].response_text.endswith("I generally prefer Python.")


def test_temporal_importance_is_deterministic_and_exposes_each_score_component():
    result = LongMemEvalDeterministicRunner().run(LongMemEvalRunRequest(
        payload=PAYLOAD,
        source_authorised=True,
        memory_strategy=MemoryStrategy.TEMPORAL_IMPORTANCE,
    ))

    assert result.metadata.memory_strategy == MemoryStrategy.TEMPORAL_IMPORTANCE
    assert result.cases[0].retrieval_evidence
    assert all(item.chronology_basis == "sequential_message_order" for item in result.cases[0].retrieval_evidence)
    assert all(item.importance_factor is not None for item in result.cases[0].retrieval_evidence)
    assert all(item.temporal_importance_score is not None for item in result.cases[0].retrieval_evidence)
    assert "recency_factor=" in result.cases[0].retrieval_evidence[0].reason


def test_run_endpoint_requires_authorisation_and_keeps_run_payload_ephemeral():
    with TestClient(app) as client:
        denied = client.post("/api/v1/research/benchmarks/longmemeval/run", json={"payload": PAYLOAD})
        assert denied.status_code == 422
        response = client.post("/api/v1/research/benchmarks/longmemeval/run", json={
            "payload": PAYLOAD,
            "source_authorised": True,
            "memory_strategy": "strong_rule_based",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["tests_total"] == 2
    assert body["metadata"]["source_fingerprint_sha256"]
    assert body["categories"][0]["total"] >= 1
