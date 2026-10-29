"""Apply one tightly scoped, documented OpenRouter 429 recovery to v6.

This tool preserves the original v6 protocol and payloads. It verifies a separate
execution addendum, paces every OpenRouter POST, and allows one additional grader
attempt only for the exact frozen payload named in that addendum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_PROTOCOL_ID = "phase4-c-openrouter-gpt6-luna-expansion-20261028-v6"
EXPECTED_MIN_INTERVAL_SECONDS = 4.0
EXPECTED_RECOVERY_ATTEMPTS = 1


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _grade_identity(grade: dict[str, Any]) -> tuple[int, str, str]:
    return int(grade["repetition"]), str(grade["strategy"]), str(grade["question_id"])


def validate_addendum(root: Path, directory: Path, addendum_path: Path,
                      wrapper_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    protocol_path = directory / "protocol.json"
    run_path = directory / "C-live.json"
    protocol = load_json(protocol_path)
    run = load_json(run_path)
    addendum = load_json(addendum_path)
    if protocol.get("id") != EXPECTED_PROTOCOL_ID:
        raise ValueError("The recovery addendum does not apply to the frozen v6 protocol.")
    if addendum.get("protocol_sha256") != sha256_file(protocol_path):
        raise ValueError("The recovery addendum is not bound to protocol.json.")
    pre_run_sha = addendum.get("pre_recovery_run_sha256")
    bound_entry = {
        "file": addendum_path.name,
        "sha256": sha256_file(addendum_path),
        "wrapper_file": wrapper_path.name,
        "wrapper_sha256": sha256_file(wrapper_path),
        "pre_recovery_run_sha256": pre_run_sha,
        "recorded_before_resume": True,
    }
    recorded_entries = run.get("execution_addenda", [])
    if sha256_file(run_path) != pre_run_sha and bound_entry not in recorded_entries:
        raise ValueError("The partial run changed without its pre-dispatch addendum receipt.")
    if addendum.get("wrapper_sha256") != sha256_file(wrapper_path):
        raise ValueError("The recovery wrapper differs from the one bound by the addendum.")
    if addendum.get("min_seconds_between_http_starts") != EXPECTED_MIN_INTERVAL_SECONDS:
        raise ValueError("The recovery addendum does not require the frozen four-second pacing interval.")
    if addendum.get("additional_grader_attempts_allowed") != EXPECTED_RECOVERY_ATTEMPTS:
        raise ValueError("The recovery addendum must allow exactly one additional attempt.")
    if addendum.get("global_estimated_cost_ceiling_usd") != 1.0:
        raise ValueError("The recovery addendum changed the global estimated cost ceiling.")
    if run.get("protocol_sha256") != addendum.get("protocol_sha256"):
        raise ValueError("The partial run is bound to a different protocol hash.")
    if run.get("estimated_cost_usd", 0) >= addendum.get("resume_run_ceiling_usd", 0):
        raise ValueError("The remaining estimated cost ceiling is exhausted.")

    identity = tuple(addendum.get("recovery_grade_identity", []))
    payload_sha = addendum.get("recovery_payload_sha256")
    grades = [g for g in run.get("grades", []) if _grade_identity(g) == identity]
    if len(grades) != 1:
        raise ValueError("The addendum must identify exactly one existing grader record.")
    grade = grades[0]
    if grade.get("request_payload_sha256") != payload_sha:
        raise ValueError("The recovery payload no longer matches its frozen grader request.")
    attempts = grade.get("attempts", [])
    if len(attempts) not in {3, 4} or any(a.get("http_status") != 429 for a in attempts[:3]):
        raise ValueError("The recovery is allowed only after exactly three explicit HTTP 429 responses.")
    if len(attempts) == 4 and attempts[3].get("status") in {"pending", "unknown"}:
        raise ValueError("The one permitted recovery has an unknown outcome; do not resend it.")
    expected_429_hashes = (addendum.get("observed_failure") or {}).get("rate_limit_response_sha256")
    if [sha256_file_bytes(str(a.get("response_body", "")).encode("utf-8")) for a in attempts[:3]] != expected_429_hashes:
        raise ValueError("A saved 429 response differs from the addendum's bound response hashes.")
    if any(a.get("request_payload_sha256") not in (None, payload_sha) for a in attempts):
        raise ValueError("The failed grader attempts are not tied to one identical request payload.")
    if grade.get("verdict_usable"):
        raise ValueError("The named grader record already has a usable result; no recovery is permitted.")
    if addendum.get("recovery_payload_sha256") != grade.get("request_payload_sha256"):
        raise ValueError("The recovery request is not the exact saved grader payload.")
    return protocol, run, grade


def sha256_file_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(root: Path, directory: Path, addendum_path: Path, max_cost_usd: float,
        *, validate_only: bool = False) -> dict[str, Any] | None:
    root, directory, addendum_path = root.resolve(), directory.resolve(), addendum_path.resolve()
    wrapper_path = Path(__file__).resolve()
    protocol, before, recovery_grade = validate_addendum(root, directory, addendum_path, wrapper_path)
    addendum = load_json(addendum_path)
    if validate_only:
        print(json.dumps({
            "validated": True,
            "model_calls_made": 0,
            "recovery_payload_sha256": recovery_grade["request_payload_sha256"],
            "targets_saved": len(before.get("target_receipts", [])),
            "usable_grades_saved": sum(bool(g.get("verdict_usable")) for g in before.get("grades", [])),
        }))
        return None
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        raise RuntimeError("OPENROUTER_API_KEY is missing; no model calls were sent.")
    if max_cost_usd <= 0 or max_cost_usd > float(addendum["resume_run_ceiling_usd"]) + 1e-12:
        raise ValueError("The resumed run cost ceiling cannot exceed the frozen addendum ceiling.")

    run_path = directory / "C-live.json"
    addendum_sha = sha256_file(addendum_path)
    report = load_json(run_path)
    addenda = report.setdefault("execution_addenda", [])
    entry = {
        "file": addendum_path.name,
        "sha256": addendum_sha,
        "wrapper_file": wrapper_path.name,
        "wrapper_sha256": sha256_file(wrapper_path),
        "pre_recovery_run_sha256": addendum["pre_recovery_run_sha256"],
        "recorded_before_resume": True,
    }
    if entry not in addenda:
        addenda.append(entry)
        import run_phase4_c_expansion as runner_module
        runner_module._atomic_write_json(run_path, report)
        run_path.chmod(0o600)

    not_before = datetime.fromisoformat(addendum["cooldown_not_before_utc"].replace("Z", "+00:00"))
    remaining = (not_before - datetime.now(timezone.utc)).total_seconds()
    if remaining > 0:
        print(f"waiting_for_provider_cooldown_seconds={int(remaining)}", flush=True)
        time.sleep(remaining)

    scripts_path = str(root / "scripts")
    backend_path = str(root / "backend")
    for item in (backend_path, scripts_path):
        if item not in sys.path:
            sys.path.insert(0, item)
    import httpx
    import run_phase4_c_expansion as runner

    target_identity = tuple(addendum["recovery_grade_identity"])
    target_payload_sha = addendum["recovery_payload_sha256"]
    original_attempt_limit = runner.MAX_PROVIDER_ATTEMPTS
    original_grader_function = runner._run_grader_attempts
    original_post = httpx.post
    last_start = 0.0
    post_count = 0

    def paced_post(*args, **kwargs):
        nonlocal last_start, post_count
        delay = EXPECTED_MIN_INTERVAL_SECONDS - (time.monotonic() - last_start)
        if last_start and delay > 0:
            time.sleep(delay)
        last_start = time.monotonic()
        post_count += 1
        return original_post(*args, **kwargs)

    def one_keyed_recovery_only(grade, report, save, client, frozen_ceiling):
        nonlocal post_count
        identity = _grade_identity(grade)
        original_count = len(grade.get("attempts", []))
        if identity == target_identity and grade.get("request_payload_sha256") == target_payload_sha:
            if original_count not in {3, 4}:
                raise ValueError("The single recovery is already used or the failed-attempt count changed.")
            runner.MAX_PROVIDER_ATTEMPTS = 4
            try:
                result = original_grader_function(grade, report, save, client, frozen_ceiling)
            finally:
                runner.MAX_PROVIDER_ATTEMPTS = original_attempt_limit
            if len(grade.get("attempts", [])) > 4:
                raise ValueError("The keyed recovery exceeded its one permitted additional attempt.")
            return result
        runner.MAX_PROVIDER_ATTEMPTS = original_attempt_limit
        return original_grader_function(grade, report, save, client, frozen_ceiling)

    httpx.post = paced_post
    runner._run_grader_attempts = one_keyed_recovery_only
    try:
        with runner._exclusive_run_lock(directory):
            result = runner.run_expansion(root, directory, max_cost_usd=max_cost_usd)
    finally:
        httpx.post = original_post
        runner._run_grader_attempts = original_grader_function
        runner.MAX_PROVIDER_ATTEMPTS = original_attempt_limit

    print(json.dumps({
        "status": result.get("status"),
        "target_receipts": len(result.get("target_receipts", [])),
        "usable_grades": sum(bool(g.get("verdict_usable")) for g in result.get("grades", [])),
        "estimated_cost_usd": result.get("estimated_cost_usd"),
        "global_estimated_ceiling_usd": result.get("max_cost_usd"),
        "rate_limited_http_posts": post_count,
        "minimum_start_interval_seconds": EXPECTED_MIN_INTERVAL_SECONDS,
    }, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--addendum", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    directory = args.directory if args.directory.is_absolute() else args.root / args.directory
    addendum = args.addendum if args.addendum.is_absolute() else args.root / args.addendum
    run(args.root, directory, addendum, args.max_cost_usd, validate_only=args.validate_only)


if __name__ == "__main__":
    main()
