"""Offline contracts for caller-supplied LoCoMo/BEAM-compatible runs."""
from fastapi.testclient import TestClient

from app.benchmarks.local_compatible import BEAMAdapter, LoCoMoAdapter
from app.benchmarks.local_runner import BEAMDeterministicRunner, LoCoMoDeterministicRunner
from app.main import app
from app.schemas.benchmark import LocalCompatibleRunRequest
from app.schemas.domain import MemoryStrategy


PAYLOAD = {
    "cases": [{
        "id": "SYN-001",
        "query": "Which database should the current project use?",
        "expected": "PostgreSQL",
        "task": "knowledge_update",
        "dialogue": [
            {"id": "m1", "speaker": "user", "text": "I used MySQL before.", "time": "2026-01-01T00:00:00Z"},
            {"id": "m2", "speaker": "user", "text": "The project now uses PostgreSQL.", "time": "2026-01-02T00:00:00Z"},
        ],
    }],
}


def test_locomo_and_beam_adapters_normalise_local_common_shapes():
    for adapter, family in ((LoCoMoAdapter(), "locomo"), (BEAMAdapter(), "beam")):
        cases, report = adapter.adapt(PAYLOAD)
        assert report.benchmark_family == family
        assert cases[0].case_id == "SYN-001"
        assert len(cases[0].messages) == 2
        assert "official" in report.notice.lower()


def test_compatible_runners_are_deterministic_and_return_traceable_evidence():
    request = LocalCompatibleRunRequest(
        payload=PAYLOAD, source_authorised=True,
        memory_strategy=MemoryStrategy.STRONG_RULE_BASED,
    )
    for runner, prefix in ((LoCoMoDeterministicRunner(), "LOCOMO-RUN-"), (BEAMDeterministicRunner(), "BEAM-RUN-")):
        first = runner.run(request)
        second = runner.run(request)
        assert first == second
        assert first.metadata.run_id.startswith(prefix)
        assert first.cases[0].retrieval_evidence
        assert first.categories[0].total == 1
        assert "not official" in first.metadata.notice.lower()


def test_compatible_routes_require_authorisation_and_expose_no_persistence_claim():
    with TestClient(app) as client:
        denied = client.post("/api/v1/research/benchmarks/locomo/run", json={"payload": PAYLOAD})
        assert denied.status_code == 422
        validated = client.post("/api/v1/research/benchmarks/beam/validate", json={"payload": PAYLOAD})
        assert validated.status_code == 200
        response = client.post("/api/v1/research/benchmarks/beam/run", json={
            "payload": PAYLOAD, "source_authorised": True, "memory_strategy": "strong_rule_based",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["benchmark_family"] == "beam"
    assert body["cases"][0]["retrieval_evidence"]
