"""Deterministic local execution for LoCoMo/BEAM-compatible sources.

This shares the project's transparent in-memory ingestion, retrieval and
reference-overlap evaluation logic with the LongMemEval compatibility runner.
It intentionally remains a reproducible policy-ablation tool, not an official
implementation or score for either external benchmark.
"""
from __future__ import annotations

from hashlib import sha256

from app.benchmarks.local_compatible import LocalCompatibleAdapter
from app.benchmarks.runner import LongMemEvalDeterministicRunner
from app.schemas.benchmark import (
    LocalCompatibleRunMetadata,
    LocalCompatibleRunRequest,
    LocalCompatibleRunResponse,
)
from app.schemas.domain import Dimension


class LocalCompatibleDeterministicRunner(LongMemEvalDeterministicRunner):
    """Execute caller-owned compatible cases in isolated in-memory stores."""

    EVALUATOR = "deterministic-reference-overlap-v1"

    def __init__(self, family: str, adapter: LocalCompatibleAdapter | None = None):
        self.family = family.strip().lower()
        self.adapter = adapter or LocalCompatibleAdapter(self.family)
        self.VERSION = f"{self.family}-local-runner-v1"

    def run(self, request: LocalCompatibleRunRequest) -> LocalCompatibleRunResponse:
        cases, report = self.adapter.adapt(request.payload)
        fingerprint = self._fingerprint(request.payload)
        run_id = f"{self.family.upper()}-RUN-{sha256(f'{fingerprint}:{request.memory_strategy.value}:{request.random_seed}'.encode()).hexdigest()[:12].upper()}"
        results = [self._run_case(case, request.memory_strategy) for case in cases]
        total = len(results)
        passed = sum(item.passed for item in results)
        return LocalCompatibleRunResponse(
            metadata=LocalCompatibleRunMetadata(
                benchmark_family=self.family, run_id=run_id, runner_version=self.VERSION,
                adapter_version=report.adapter_version, source_fingerprint_sha256=fingerprint,
                source_format=report.source_format, source_label=request.source_label,
                random_seed=request.random_seed, memory_strategy=request.memory_strategy,
                execution_mode="local-in-memory; sequential-message-ingestion; no-network; no-llm",
                evaluator=self.EVALUATOR, case_order=[case.case_id for case in cases],
                notice=(
                    f"Local {self.family.upper()}-compatible execution only. The caller is responsible for "
                    "lawful source access, licence, citation, consent and privacy conditions. These are not "
                    f"official {self.family.upper()} scores; no source records were downloaded, redistributed, "
                    "or retained by this endpoint."
                ),
            ),
            cases=results,
            categories=self._summaries((item.category, item.passed) for item in results),
            dimensions=self._summaries(
                ((item.dimension.value, item.passed) for item in results if item.dimension is not None),
                all_keys=[dimension.value for dimension in Dimension],
            ),
            tests_passed=passed, tests_total=total,
            overall_percentage=round((passed / total) * 100, 2) if total else None,
            mean_token_f1=round(sum(item.token_f1 for item in results) / total, 4) if total else None,
            mean_latency_ms=round(sum(item.latency_ms for item in results) / total, 3) if total else None,
        )


class LoCoMoDeterministicRunner(LocalCompatibleDeterministicRunner):
    def __init__(self):
        super().__init__("locomo")


class BEAMDeterministicRunner(LocalCompatibleDeterministicRunner):
    def __init__(self):
        super().__init__("beam")
