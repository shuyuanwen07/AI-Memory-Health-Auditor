"""Deterministic, local execution for LongMemEval-compatible records.

This runner deliberately remains a provider-agnostic research baseline.  It
does not fetch or package external data, call an LLM, or write to the audit
database.  For each uploaded case it constructs an isolated in-memory target
memory store, ingests messages in chronological order, retrieves records using
one of the project's controlled policies, produces an answer using only that
retrieved context, and applies a transparent lexical reference-answer matcher.

It is useful for repeatable integration checks and policy ablations.  It is not
the official LongMemEval evaluator and must not be reported as one.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.schemas.benchmark import (
    BenchmarkMemoryEvidence,
    BenchmarkScoreSummary,
    LongMemEvalCase,
    LongMemEvalCaseRunResult,
    LongMemEvalRunMetadata,
    LongMemEvalRunRequest,
    LongMemEvalRunResponse,
)
from app.schemas.domain import Dimension, MemoryStrategy


_TERMS = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]*")
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "because", "but", "by",
    "for", "from", "has", "have", "i", "in", "is", "it", "my", "of", "on",
    "or", "our", "should", "that", "the", "their", "this", "to", "was", "we",
    "with", "you", "your", "which", "what", "would", "current", "general",
    "record", "memory", "remembered", "assignment", "requirement",
})
_UPDATE = (" now", "currently", "migrat", "switch", "changed", "replaced", "instead of", "latest")
_CONTEXTUAL_REQUIREMENT = (
    "current ", "this assignment", "this project", "for this task", "for this assignment",
    "required", "must", "mandatory", "need to",
)


@dataclass
class _StoredMemory:
    memory_id: str
    canonical_value: str
    write_order: int
    lifecycle_state: str = "ACTIVE"
    policy_score: float = 10.0
    update_of: str | None = None


class LongMemEvalDeterministicRunner:
    """Run local compatible cases in isolated in-memory stores."""

    VERSION = "longmemeval-local-runner-v1"
    EVALUATOR = "deterministic-reference-overlap-v1"

    def __init__(self, adapter: LongMemEvalAdapter | None = None):
        self.adapter = adapter or LongMemEvalAdapter()

    def run(self, request: LongMemEvalRunRequest) -> LongMemEvalRunResponse:
        cases, report = self.adapter.adapt(request.payload)
        fingerprint = self._fingerprint(request.payload)
        run_id = f"LME-RUN-{sha256(f'{fingerprint}:{request.memory_strategy.value}:{request.random_seed}'.encode()).hexdigest()[:12].upper()}"
        results = [self._run_case(case, request.memory_strategy) for case in cases]
        total = len(results)
        passed = sum(item.passed for item in results)
        category_summaries = self._summaries(
            ((item.category, item.passed) for item in results),
        )
        dimension_summaries = self._summaries(
            ((item.dimension.value, item.passed) for item in results if item.dimension is not None),
            all_keys=[dimension.value for dimension in Dimension],
        )
        return LongMemEvalRunResponse(
            metadata=LongMemEvalRunMetadata(
                run_id=run_id,
                runner_version=self.VERSION,
                adapter_version=report.adapter_version,
                source_fingerprint_sha256=fingerprint,
                source_format=report.source_format,
                source_label=request.source_label,
                random_seed=request.random_seed,
                memory_strategy=request.memory_strategy,
                execution_mode="local-in-memory; sequential-message-ingestion; no-network; no-llm",
                evaluator=self.EVALUATOR,
                case_order=[case.case_id for case in cases],
                notice=(
                    "Local compatibility execution only. The caller is responsible for obtaining "
                    "the source data lawfully and complying with its licence, citation, consent, "
                    "and privacy conditions. These are not official LongMemEval scores; no source "
                    "records were downloaded, redistributed, or retained by this endpoint."
                ),
            ),
            cases=results,
            categories=category_summaries,
            dimensions=dimension_summaries,
            tests_passed=passed,
            tests_total=total,
            overall_percentage=round((passed / total) * 100, 2) if total else None,
        )

    def _run_case(self, case: LongMemEvalCase, strategy: MemoryStrategy) -> LongMemEvalCaseRunResult:
        store = self._ingest(case)
        selected, evidence = self._retrieve(case.question, store, strategy)
        response = self._answer(selected, strategy)
        matched, reason = self._evaluate(case.expected_answer, response)
        return LongMemEvalCaseRunResult(
            case_id=case.case_id,
            category=case.category,
            dimension=self._dimension(case),
            question=case.question,
            expected_answer=case.expected_answer,
            response_text=response,
            passed=matched,
            evaluation_reason=reason,
            ingested_memory_count=len(store),
            retrieved_memory_ids=[memory.memory_id for memory in selected],
            retrieval_evidence=evidence,
        )

    def _ingest(self, case: LongMemEvalCase) -> list[_StoredMemory]:
        """Write each usable user message in chronological order to a fresh store."""
        ordered = sorted(enumerate(case.messages), key=lambda item: (item[1].timestamp, item[0]))
        store: list[_StoredMemory] = []
        for _, message in ordered:
            # The target agent only learns user-authored factual context.  This
            # matches the main controlled-agent ingestion boundary and avoids
            # treating assistant statements as user ground truth.
            if message.role.strip().lower() != "user" or not message.content.strip():
                continue
            record = _StoredMemory(
                memory_id=f"{case.case_id}-MEM-{len(store) + 1:03d}",
                canonical_value=message.content.strip(),
                write_order=len(store) + 1,
            )
            self._apply_lifecycle(record, store)
            store.append(record)
        return store

    def _apply_lifecycle(self, record: _StoredMemory, existing: list[_StoredMemory]) -> None:
        text = record.canonical_value.lower()
        related = [item for item in existing if self._category(item.canonical_value) == self._category(record.canonical_value) and self._category(text)]
        if any(token in text for token in _UPDATE) and related:
            previous = related[-1]
            previous.lifecycle_state = "SUPERSEDED"
            previous.policy_score = -50.0
            record.policy_score = 40.0
            record.update_of = previous.memory_id
        if all(token in text for token in ("current", "required")) or (
            any(token in text for token in _CONTEXTUAL_REQUIREMENT[:4])
            and any(token in text for token in _CONTEXTUAL_REQUIREMENT[4:])
        ):
            record.policy_score = max(record.policy_score, 60.0)

    def _retrieve(
        self, question: str, store: list[_StoredMemory], strategy: MemoryStrategy,
    ) -> tuple[list[_StoredMemory], list[BenchmarkMemoryEvidence]]:
        candidates: list[tuple[_StoredMemory, float, str]] = []
        question_terms = self._tokens(question)
        question_category = self._category(question)
        for memory in store:
            overlap = len(question_terms & self._tokens(memory.canonical_value))
            category_match = int(question_category is not None and question_category == self._category(memory.canonical_value))
            relevance = float(overlap + (3 * category_match))
            if relevance:
                why = f"lexical_overlap={overlap}" + ("; topic_category_match" if category_match else "")
                candidates.append((memory, relevance, why))
        if strategy == MemoryStrategy.WEAK_FIRST_HIT:
            selected = [min(candidates, key=lambda item: item[0].write_order)[0]] if candidates else []
        elif strategy == MemoryStrategy.STRONG_RULE_BASED:
            selected = [item[0] for item in sorted(candidates, key=lambda item: (item[0].policy_score, item[0].write_order))]
        else:
            selected = [item[0] for item in sorted(candidates, key=lambda item: (item[1] * 10 + item[0].policy_score, item[0].write_order))]
        selected_ids = {item.memory_id for item in selected}
        evidence = [
            BenchmarkMemoryEvidence(
                memory_id=memory.memory_id,
                canonical_value=memory.canonical_value,
                write_order=memory.write_order,
                lifecycle_state=memory.lifecycle_state,
                relevance_score=relevance,
                policy_score=memory.policy_score,
                selected=memory.memory_id in selected_ids,
                reason=reason + (f"; supersedes={memory.update_of}" if memory.update_of else ""),
            )
            for memory, relevance, reason in candidates
        ]
        return selected, evidence

    @staticmethod
    def _answer(selected: list[_StoredMemory], strategy: MemoryStrategy) -> str:
        if not selected:
            return "I do not have a relevant stored memory, so I cannot answer reliably."
        if strategy == MemoryStrategy.WEAK_FIRST_HIT:
            return f"Based on the first relevant stored memory: {selected[0].canonical_value}"
        return f"Based on the highest-priority retrieved memory: {selected[-1].canonical_value}"

    def _evaluate(self, expected: str, response: str) -> tuple[bool, str]:
        expected_terms = self._reference_terms(expected)
        response_terms = self._tokens(response)
        matched = sorted(expected_terms & response_terms)
        coverage = len(matched) / len(expected_terms) if expected_terms else 0.0
        # A reference answer may contain explanation beyond the core value.
        # At least half its meaningful terms, including one match, is an
        # explicit, deterministic local success criterion.
        passed = bool(matched) and coverage >= 0.5
        return passed, (
            f"{self.EVALUATOR}: matched {len(matched)}/{len(expected_terms)} meaningful "
            f"reference term(s) ({', '.join(matched) if matched else 'none'}); "
            f"coverage={coverage:.2f}; threshold=0.50."
        )

    @staticmethod
    def _dimension(case: LongMemEvalCase) -> Dimension | None:
        if case.dimension_hint:
            normalised = case.dimension_hint.strip().lower().replace("-", "_").replace(" ", "_")
            try:
                return Dimension(normalised)
            except ValueError:
                pass
        category = case.category.strip().lower().replace("-", "_").replace(" ", "_")
        if category in {"knowledge_update", "temporal_reasoning", "temporal"}:
            return Dimension.FRESHNESS
        if category in {"information_extraction", "multi_session_reasoning", "multi_session"}:
            return Dimension.ACCURACY
        if category in {"conflict", "conflict_resolution", "contradiction"}:
            return Dimension.CONFLICT_RESOLUTION
        if category in {"appropriate_use", "contextual_override", "contextual_reasoning"}:
            return Dimension.APPROPRIATE_USE
        return None

    @staticmethod
    def _summaries(items, all_keys: list[str] | None = None) -> list[BenchmarkScoreSummary]:
        buckets: dict[str, list[bool]] = {key: [] for key in (all_keys or [])}
        for key, passed in items:
            buckets.setdefault(key, []).append(passed)
        return [
            BenchmarkScoreSummary(
                key=key,
                passed=sum(outcomes),
                total=len(outcomes),
                percentage=round((sum(outcomes) / len(outcomes)) * 100, 2) if outcomes else None,
            )
            for key, outcomes in sorted(buckets.items())
        ]

    @staticmethod
    def _fingerprint(payload: dict | list) -> str:
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {term.lower() for term in _TERMS.findall(value) if term.lower() not in _STOP}

    @staticmethod
    def _reference_terms(value: str) -> set[str]:
        # Reference answers often begin with the answer and then justify it,
        # e.g. ``Java, because ... Python preference``.  Treating every term
        # in that justification as required would incorrectly reward a stale
        # answer that merely repeats the old alternative.  The first clause is
        # the transparent answer anchor for this compact local matcher.
        anchor = re.split(r"\b(?:because|but|although|however|while|rather than|instead of)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
        return LongMemEvalDeterministicRunner._tokens(anchor) or LongMemEvalDeterministicRunner._tokens(value)

    @staticmethod
    def _category(value: str) -> str | None:
        text = value.lower()
        if re.search(r"\b(?:mysql|postgres(?:ql)?|mongodb|sqlite|database|sql)\b", text):
            return "database"
        if re.search(r"\b(?:python|java|rust|javascript|typescript|programming|language)\b", text):
            return "programming-language"
        if re.search(r"\b(?:sydney|melbourne|london|based in|located in|live in|relocat)\b", text):
            return "location"
        if re.search(r"\b(?:remote|from home|office|hybrid)\b", text):
            return "working-arrangement"
        return None
