"""Small local compatibility adapters for LoCoMo- and BEAM-style JSON.

The project does not distribute either upstream dataset.  These adapters accept
only caller-supplied, authorised JSON and normalise a documented common subset
to the same portable case contract used by the LongMemEval local runner.
They are not official loaders, scorers, or leaderboard integrations.
"""
from __future__ import annotations

from typing import Any

from app.benchmarks.longmemeval import LongMemEvalAdapter
from app.schemas.benchmark import LocalCompatibleImportReport, LongMemEvalCase


class LocalCompatibleAdapter(LongMemEvalAdapter):
    """Normalise practical multi-session QA layouts without source retention."""

    def __init__(self, family: str):
        normalised = family.strip().lower()
        if normalised not in {"locomo", "beam"}:
            raise ValueError("Benchmark family must be locomo or beam.")
        self.family = normalised

    def adapt(self, payload: Any) -> tuple[list[LongMemEvalCase], LocalCompatibleImportReport]:
        records = self._records(payload)
        cases = [self._adapt_record(record, index) for index, record in enumerate(records, 1)]
        ids = [case.case_id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.family.upper()}-compatible records must have unique case IDs.")
        return cases, LocalCompatibleImportReport(
            benchmark_family=self.family,
            adapter_version=f"{self.family}-compatible-v1",
            cases_imported=len(cases), case_ids=ids,
            dimension_hints=sorted({case.dimension_hint for case in cases if case.dimension_hint}),
            source_format=self._source_format(payload),
            notice=(
                f"Validated only as a local {self.family.upper()}-compatible shape. This service does not "
                f"download, execute, redistribute, or claim official {self.family.upper()} data or scores."
            ),
        )

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = next((payload[key] for key in (
                "records", "data", "examples", "questions", "cases", "items",
            ) if isinstance(payload.get(key), list)), None)
            if records is None:
                # A single case object is a useful local hand-off shape.
                records = [payload] if any(key in payload for key in ("question", "query", "prompt")) else None
        else:
            records = None
        if not records or not all(isinstance(record, dict) for record in records):
            raise ValueError("Expected at least one object case or a records/data/examples/questions/cases/items array.")
        return records

    @staticmethod
    def _source_format(payload: Any) -> str:
        if isinstance(payload, list):
            return "array"
        if not isinstance(payload, dict):
            return "unknown"
        return next((key for key in ("records", "data", "examples", "questions", "cases", "items") if isinstance(payload.get(key), list)), "single-case")

    def _adapt_record(self, record: dict[str, Any], index: int) -> LongMemEvalCase:
        # Reuse base field validation/message parsing while accepting common
        # alternate containers seen in locally prepared benchmark subsets.
        transformed = dict(record)
        if "messages" not in transformed:
            for key in ("conversation", "dialogue", "turns", "history", "sessions", "haystack_sessions"):
                if isinstance(transformed.get(key), list):
                    transformed["messages"] = transformed[key]
                    break
        if "answer" not in transformed:
            for key in ("expected", "reference", "gold_answer", "gold", "response"):
                if isinstance(transformed.get(key), str):
                    transformed["answer"] = transformed[key]
                    break
        if "question" not in transformed:
            for key in ("query", "prompt", "question_text"):
                if isinstance(transformed.get(key), str):
                    transformed["question"] = transformed[key]
                    break
        if "category" not in transformed:
            transformed["category"] = transformed.get("task") or transformed.get("question_type") or "unspecified"
        return super()._adapt_record(transformed, index)


class LoCoMoAdapter(LocalCompatibleAdapter):
    def __init__(self):
        super().__init__("locomo")


class BEAMAdapter(LocalCompatibleAdapter):
    def __init__(self):
        super().__init__("beam")
