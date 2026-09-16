"""A conservative LongMemEval-compatible import adapter.

This is not a benchmark runner and does not download LongMemEval.  It accepts
a small documented subset of common question/session JSON layouts and converts
it to the Auditor's portable benchmark contract.  Teams must obtain the
official data and follow its licence separately before using it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.benchmark import BenchmarkMessage, LongMemEvalCase, LongMemEvalImportReport


class LongMemEvalAdapter:
    """Normalise common LongMemEval-style JSON into deterministic local cases."""

    def adapt(self, payload: Any) -> tuple[list[LongMemEvalCase], LongMemEvalImportReport]:
        records = self._records(payload)
        cases = [self._adapt_record(record, index) for index, record in enumerate(records, 1)]
        ids = [case.case_id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("LongMemEval-compatible records must have unique question IDs.")
        dimensions = sorted({case.dimension_hint for case in cases if case.dimension_hint})
        return cases, LongMemEvalImportReport(
            adapter_version="longmemeval-compatible-v1",
            cases_imported=len(cases),
            case_ids=ids,
            dimension_hints=dimensions,
            source_format=self._source_format(payload),
            notice="Validated only; this service does not download, execute, or redistribute LongMemEval.",
        )

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = next((payload[key] for key in ("records", "data", "questions", "examples") if isinstance(payload.get(key), list)), None)
            if records is None:
                raise ValueError("Expected a record list or one of records, data, questions, examples.")
        else:
            raise ValueError("LongMemEval-compatible input must be a JSON object or array.")
        if not records or not all(isinstance(record, dict) for record in records):
            raise ValueError("At least one object record is required.")
        return records

    @staticmethod
    def _source_format(payload: Any) -> str:
        return "array" if isinstance(payload, list) else next((key for key in ("records", "data", "questions", "examples") if isinstance(payload.get(key), list)), "unknown")

    def _adapt_record(self, record: dict[str, Any], index: int) -> LongMemEvalCase:
        case_id = str(record.get("question_id") or record.get("case_id") or record.get("id") or f"LME-{index:03d}")
        question = self._required_text(record, "question", "query", "prompt")
        answer = self._required_text(record, "answer", "expected_answer", "reference_answer")
        sessions = next((record[key] for key in ("haystack_sessions", "sessions", "conversation", "messages") if isinstance(record.get(key), list)), [])
        messages = self._messages(sessions)
        if not messages:
            raise ValueError(f"Record {case_id} has no usable session/message context.")
        return LongMemEvalCase(
            case_id=case_id,
            question=question,
            expected_answer=answer,
            messages=messages,
            category=str(record.get("category") or record.get("question_type") or "unspecified"),
            dimension_hint=record.get("dimension_hint"),
            source_metadata={key: value for key, value in record.items() if key not in {"haystack_sessions", "sessions", "conversation", "messages", "question", "query", "prompt", "answer", "expected_answer", "reference_answer"}},
        )

    @staticmethod
    def _required_text(record: dict[str, Any], *keys: str) -> str:
        value = next((record[key] for key in keys if isinstance(record.get(key), str) and record[key].strip()), None)
        if value is None:
            raise ValueError(f"Record needs one non-empty field: {', '.join(keys)}.")
        return value.strip()

    def _messages(self, sessions: list[Any]) -> list[BenchmarkMessage]:
        flattened: list[dict[str, Any]] = []
        for session in sessions:
            if isinstance(session, dict) and isinstance(session.get("messages"), list):
                flattened.extend(item for item in session["messages"] if isinstance(item, dict))
            elif isinstance(session, dict):
                flattened.append(session)
        result: list[BenchmarkMessage] = []
        for index, message in enumerate(flattened, 1):
            content = message.get("content") or message.get("text")
            if not isinstance(content, str) or not content.strip():
                continue
            timestamp = message.get("timestamp") or message.get("time")
            result.append(BenchmarkMessage(
                message_id=str(message.get("message_id") or message.get("id") or f"MSG-{index:03d}"),
                role=str(message.get("role") or message.get("speaker") or "user"),
                content=content.strip(),
                timestamp=self._timestamp(timestamp),
            ))
        return result

    @staticmethod
    def _timestamp(raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        # Input formats sometimes omit time. Retain deterministic ordering
        # without making claims about an actual source timestamp.
        return datetime(2000, 1, 1, tzinfo=timezone.utc)
