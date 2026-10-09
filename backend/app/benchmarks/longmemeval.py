"""A conservative LongMemEval-compatible import adapter.

This is not a benchmark runner and does not download LongMemEval.  It accepts
a small documented subset of common question/session JSON layouts and converts
it to the Auditor's portable benchmark contract.  Teams must obtain the
official data and follow its licence separately before using it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
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
            adapter_version="longmemeval-compatible-v3",
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
        answer = self._reference_answer(record)
        sessions = next((record[key] for key in ("haystack_sessions", "sessions", "conversation", "messages") if isinstance(record.get(key), list)), [])
        messages = self._messages(sessions, record.get("haystack_dates"), record.get("haystack_session_ids"))
        if not messages:
            raise ValueError(f"Record {case_id} has no usable session/message context.")
        return LongMemEvalCase(
            case_id=case_id,
            question=question,
            expected_answer=answer,
            messages=messages,
            category=str(record.get("category") or record.get("question_type") or "unspecified"),
            question_timestamp=self._timestamp(record["question_date"], strict=True) if record.get("question_date") else None,
            dimension_hint=record.get("dimension_hint"),
            source_metadata={key: value for key, value in record.items() if key not in {"haystack_sessions", "sessions", "conversation", "messages", "question", "query", "prompt", "answer", "expected_answer", "reference_answer"}},
        )

    @staticmethod
    def _reference_answer(record: dict[str, Any]) -> str:
        for key in ("answer", "expected_answer", "reference_answer"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            # Official temporal/count answers include JSON integers (including
            # zero). Do not turn booleans or structured objects into answers.
            if type(value) is int or (type(value) is float and math.isfinite(value)):
                return str(value)
        raise ValueError("Record needs a non-empty text or finite numeric reference answer.")

    @staticmethod
    def _required_text(record: dict[str, Any], *keys: str) -> str:
        value = next((record[key] for key in keys if isinstance(record.get(key), str) and record[key].strip()), None)
        if value is None:
            raise ValueError(f"Record needs one non-empty field: {', '.join(keys)}.")
        return value.strip()

    def _messages(self, sessions: list[Any], dates: Any = None, session_ids: Any = None) -> list[BenchmarkMessage]:
        for label, values in (("haystack_dates", dates), ("haystack_session_ids", session_ids)):
            if values is not None and (not isinstance(values, list) or len(values) != len(sessions)):
                friendly = "History session dates" if label == "haystack_dates" else "History session names"
                raise ValueError(f"{friendly} must align one-to-one with history sessions.")
        flattened: list[dict[str, Any]] = []
        for position, session in enumerate(sessions):
            if isinstance(session, list):
                turns = session
            elif isinstance(session, dict) and isinstance(session.get("messages"), list):
                turns = session["messages"]
            elif isinstance(session, dict):
                turns = [session]
            else:
                raise ValueError("Each history session must be a turn list or message object.")
            for turn in turns:
                if not isinstance(turn, dict):
                    raise ValueError("Every history turn must be a message object.")
                # Only text, role and chronology cross the target boundary.
                # has_answer and other benchmark annotations are never copied.
                flattened.append({**turn, "_session_date": dates[position] if dates else None,
                    "_session_id": str(session_ids[position]) if session_ids else None})
        result: list[BenchmarkMessage] = []
        for index, message in enumerate(flattened, 1):
            content = message.get("content") or message.get("text")
            if not isinstance(content, str) or not content.strip():
                continue
            timestamp = message.get("timestamp") or message.get("time") or message.get("_session_date")
            explicit = timestamp is not None
            result.append(BenchmarkMessage(
                message_id=str(message.get("message_id") or message.get("id") or f"MSG-{index:03d}"),
                role=str(message.get("role") or message.get("speaker") or "user"),
                content=content.strip(),
                timestamp=self._timestamp(timestamp, strict=explicit),
                source_session_id=message["_session_id"],
                timestamp_basis="message" if message.get("timestamp") or message.get("time") else "session" if message.get("_session_date") else "deterministic_fallback",
            ))
        if len({item.message_id for item in result}) != len(result):
            raise ValueError("History message IDs must be unique within a benchmark case.")
        return result

    @staticmethod
    def _timestamp(raw: Any, *, strict: bool = False) -> datetime:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                for pattern in ("%Y/%m/%d (%a) %H:%M", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
                    try:
                        return datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
        if strict:
            raise ValueError("Unrecognised history date; use ISO 8601 or YYYY/MM/DD (weekday) HH:MM.")
        # Input formats sometimes omit time. Retain deterministic ordering
        # without making claims about an actual source timestamp.
        return datetime(2000, 1, 1, tzinfo=timezone.utc)
