"""Hash-bound, non-claiming evidence for post-run UTC pacing anomalies."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ADDENDUM_FORMAT = "proposal-c-four-arm-v7-pacing-addendum-v1"
ADDENDUM_STATUS = "utc_timing_unverifiable"
CAUSE_ASSESSMENT = "unknown"
INTERPRETATION = (
    "The preserved UTC journal contains one or more intervals below the frozen threshold. "
    "The journal does not contain monotonic clock readings, so actual monotonic start spacing "
    "and the cause of the UTC discrepancy cannot be independently determined."
)
DECISION_USE = "descriptive_scores_only_no_winner"


class PacingAddendumError(ValueError):
    """The raw journal or proposed addendum is not safely bound."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise PacingAddendumError(f"{label} must be an ISO timestamp string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PacingAddendumError(f"{label} is not a valid ISO timestamp.") from exc
    if parsed.tzinfo is None:
        raise PacingAddendumError(f"{label} must include a UTC offset.")
    return parsed


def capture_observations(run: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    execution = protocol.get("execution")
    if not isinstance(execution, dict):
        raise PacingAddendumError("Frozen protocol lacks execution pacing thresholds.")
    minimum = execution.get("openrouter_minimum_start_to_start_seconds")
    cooldown = execution.get("initial_cooldown_seconds")
    if (not isinstance(minimum, (int, float)) or not math.isfinite(float(minimum)) or minimum <= 0
            or not isinstance(cooldown, (int, float)) or not math.isfinite(float(cooldown)) or cooldown < 0):
        raise PacingAddendumError("Frozen protocol has invalid pacing thresholds.")

    sessions = run.get("pacing_sessions")
    if not isinstance(sessions, list):
        raise PacingAddendumError("Run journal has no pacing_sessions list.")
    seen_session_ids: set[str] = set()
    raw_sessions = []
    reports = []
    flattened_starts: list[str] = []
    violations = []
    for session in sessions:
        if not isinstance(session, dict):
            raise PacingAddendumError("Run journal contains a malformed pacing session.")
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id or session_id in seen_session_ids:
            raise PacingAddendumError("Pacing session ID is missing or duplicated.")
        seen_session_ids.add(session_id)
        started_raw = session.get("started_at_utc")
        started = _timestamp(started_raw, f"{session_id}.started_at_utc")
        starts = session.get("request_starts_utc")
        if not isinstance(starts, list) or any(not isinstance(value, str) for value in starts):
            raise PacingAddendumError(f"{session_id} request_starts_utc must be a string list.")
        parsed = [_timestamp(value, f"{session_id}.request_starts_utc") for value in starts]
        flattened_starts.extend(starts)
        raw_sessions.append({"session_id": session_id, "started_at_utc": started_raw,
                             "request_starts_utc": list(starts)})
        intervals = []
        if parsed:
            first = (parsed[0] - started).total_seconds()
            if first < float(cooldown) - 0.001:
                violations.append({"kind": "initial_cooldown", "session_id": session_id,
                                   "dispatch_index": 1, "observed_seconds": round(first, 6),
                                   "required_seconds": float(cooldown), "timestamp_utc": starts[0]})
            for index, (left, right) in enumerate(zip(parsed, parsed[1:]), 1):
                observed = (right - left).total_seconds()
                row = {"from_dispatch_index": index, "to_dispatch_index": index + 1,
                       "from_timestamp_utc": starts[index - 1], "to_timestamp_utc": starts[index],
                       "observed_seconds": round(observed, 6)}
                intervals.append(row)
                if observed < float(minimum) - 0.001:
                    violations.append({"kind": "start_to_start_interval", "session_id": session_id,
                                       **row, "required_seconds": float(minimum)})
        reports.append({"session_id": session_id, "request_count": len(starts),
                        "first_dispatch_cooldown_seconds": round((parsed[0] - started).total_seconds(), 6) if parsed else None,
                        "intervals": intervals,
                        "minimum_observed_start_interval_seconds": round(min(
                            (row["observed_seconds"] for row in intervals), default=0.0), 6) if intervals else None})

    provider_starts = run.get("provider_dispatch_starts_utc")
    if not isinstance(provider_starts, list) or provider_starts != flattened_starts:
        raise PacingAddendumError("Pacing session timestamps do not exactly match provider_dispatch_starts_utc.")
    raw_record = {"provider_dispatch_starts_utc": list(provider_starts), "pacing_sessions": raw_sessions}
    return {
        "required_minimum_start_interval_seconds": float(minimum),
        "required_initial_cooldown_seconds": float(cooldown),
        "dispatch_count": len(provider_starts),
        "raw_timestamp_record": raw_record,
        "raw_timestamp_record_sha256": canonical_sha256(raw_record),
        "sessions": reports,
        "violations": violations,
    }


def build_addendum(run: dict[str, Any], protocol: dict[str, Any], source_sha256: dict[str, str],
                   *, created_at_utc: str | None = None, tool_sha256: str | None = None) -> dict[str, Any]:
    if run.get("status") == "running":
        raise PacingAddendumError("Refuse to snapshot pacing while the collection journal is still running.")
    observations = capture_observations(run, protocol)
    if not observations["violations"]:
        raise PacingAddendumError("No UTC pacing anomaly is recorded; use the strict frozen analyzer.")
    required_sources = {"run", "protocol", "subset"}
    if set(source_sha256) != required_sources or any(
            not isinstance(source_sha256[name], str) or len(source_sha256[name]) != 64
            or any(ch not in "0123456789abcdef" for ch in source_sha256[name].casefold())
            for name in required_sources):
        raise PacingAddendumError("Addendum requires SHA-256 bindings for run, protocol, and subset.")
    created_at_utc = created_at_utc or datetime.now(timezone.utc).isoformat(timespec="microseconds")
    _timestamp(created_at_utc, "created_at_utc")
    return {
        "format": ADDENDUM_FORMAT,
        "status": ADDENDUM_STATUS,
        "cause_assessment": CAUSE_ASSESSMENT,
        "compliance_claim": "unverifiable_from_saved_utc_timestamps",
        "winner_recommendation_allowed": False,
        "source_sha256": dict(source_sha256),
        "run_status_at_snapshot": run.get("status"),
        "observations": observations,
        "interpretation": INTERPRETATION,
        "decision_use": DECISION_USE,
        "created_at_utc": created_at_utc,
        "tool_sha256": tool_sha256,
    }


def verify_addendum(addendum: dict[str, Any], run: dict[str, Any], protocol: dict[str, Any],
                    source_sha256: dict[str, str]) -> dict[str, Any]:
    if not isinstance(addendum, dict) or addendum.get("format") != ADDENDUM_FORMAT:
        raise PacingAddendumError("Unsupported pacing addendum format.")
    expected = build_addendum(run, protocol, source_sha256,
                              created_at_utc=addendum.get("created_at_utc"),
                              tool_sha256=addendum.get("tool_sha256"))
    if addendum != expected:
        raise PacingAddendumError("Pacing addendum does not exactly match the saved run timestamps and frozen thresholds.")
    return expected["observations"]
