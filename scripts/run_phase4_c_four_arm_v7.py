"""Run the separate frozen v7 four-strategy exploratory replay.

The runner reuses the exact 30 v6 histories, with four policies for three
repetitions. It journals each provider dispatch and pauses at the frozen USD
0.40 cap. This is not a new independent sample, a full benchmark, or a human
calibration study. Real OpenRouter HTTP POSTs are paced at least four seconds
apart, with a 65-second cooldown at process start.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_PROTOCOL_ID = "phase4-c-openrouter-gpt6-luna-four-arm-20261028-v7"
EXPECTED_CASE_COUNT = 30
EXPECTED_BATCH_SIZE = 15
EXPECTED_STRATEGIES = ["weak_first_hit", "strong_rule_based", "scope_aware", "temporal_importance"]
EXPECTED_ORDER_BY_REPETITION = {
    "1": ["weak_first_hit", "strong_rule_based", "scope_aware", "temporal_importance"],
    "2": ["scope_aware", "temporal_importance", "weak_first_hit", "strong_rule_based"],
    "3": ["temporal_importance", "weak_first_hit", "strong_rule_based", "scope_aware"],
}
MAX_COST_USD = 0.40
MIN_REQUEST_INTERVAL_SECONDS = 4.0
INITIAL_COOLDOWN_SECONDS = 65.0
EXPECTED_REPETITIONS = 3
EXPECTED_MODEL = "openai/gpt-6-luna"
EXPECTED_PROVIDER = "openrouter"
EXPECTED_CATEGORY_COUNTS = {
    "abstention": 4,
    "knowledge-update": 4,
    "multi-session": 5,
    "single-session-assistant": 4,
    "single-session-preference": 4,
    "single-session-user": 4,
    "temporal-reasoning": 5,
}
TARGET_INPUT_USD_PER_TOKEN = 1e-7
TARGET_OUTPUT_USD_PER_TOKEN = 5e-7
GRADER_INPUT_USD_PER_TOKEN = 2.5e-6
GRADER_OUTPUT_USD_PER_TOKEN = 1e-5
MAX_PROVIDER_ATTEMPTS = 3


class FrozenInputError(ValueError):
    """A supplied v7 input differs from its pre-execution binding."""


class ResumeBlockedError(RuntimeError):
    """A previous provider dispatch has an outcome that cannot be replayed safely."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def _safe_root_path(root: Path, relative: str, label: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise FrozenInputError(f"Unsafe {label} path in frozen protocol.")
    unresolved = root / rel
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise FrozenInputError(f"Frozen {label} path contains a symlink: {relative}")
    path = unresolved.resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise FrozenInputError(f"{label} path escapes repository root.") from exc
    if not path.is_file() or path.is_symlink():
        raise FrozenInputError(f"Frozen {label} file is missing or is a symlink: {relative}")
    return path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenInputError(f"Could not read frozen JSON file: {path.name}") from exc


def _case_id(record: dict[str, Any]) -> str:
    value = record.get("question_id", record.get("case_id"))
    if not isinstance(value, str) or not value:
        raise FrozenInputError("A selected case has no stable question ID.")
    return value


def _case_category(record: dict[str, Any]) -> str:
    if str(record.get("question_id", record.get("case_id", ""))).endswith("_abs"):
        return "abstention"
    value = record.get("question_type", record.get("category"))
    if not isinstance(value, str) or not value:
        raise FrozenInputError("A selected case has no category.")
    return value


def _validate_analysis_rule(analysis: dict[str, Any]) -> None:
    primary = str(analysis.get("primary_outcome", "")).casefold()
    rule = str(analysis.get("selection_rule", "")).casefold()
    required_primary_tokens = ("gpt-6 luna", "upstream", "30")
    if not all(token in primary for token in required_primary_tokens):
        raise FrozenInputError("The frozen primary outcome must be the upstream-prompt pass rate on the 30 new cases.")
    if "pooled" not in rule or "2/3" not in rule or "no clear winner" not in rule:
        raise FrozenInputError("The frozen winner rule is missing or differs from the declared v7 rule.")
    if "strong" not in rule or "weak" not in rule:
        raise FrozenInputError("The frozen winner rule must compare Strong with Weak.")


def _validate_target_provider_environment(protocol: dict[str, Any], configured_provider: str) -> None:
    frozen_only = (protocol.get("target", {}).get("provider_options") or {}).get("only")
    if configured_provider and frozen_only != [configured_provider]:
        raise FrozenInputError("OPENROUTER_PROVIDER changes target routing outside the frozen protocol; no model requests were sent.")
    if frozen_only and configured_provider != frozen_only[0]:
        raise FrozenInputError("The frozen upstream-provider route does not match OPENROUTER_PROVIDER; no model requests were sent.")


def validate_frozen_inputs(root: Path, directory: Path) -> dict[str, Any]:
    """Validate v7 freeze, exact v6 lineage, and source hashes before any calls."""
    root = root.resolve()
    if directory.is_symlink():
        raise FrozenInputError("The v7 run directory must not be a symlink.")
    directory = directory.resolve()
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise FrozenInputError("The v7 run directory must be under the repository root.") from exc
    if not directory.is_dir():
        raise FrozenInputError("The v7 run directory is missing.")

    protocol_path = directory / "protocol.json"
    subset_path = directory / "longmemeval-subset.json"
    sidecar_path = directory / "protocol.sha256"
    for path in (protocol_path, subset_path, sidecar_path):
        if path.is_symlink() or not path.is_file():
            raise FrozenInputError("The v7 protocol, sidecar, and local subset must be regular files.")
    if os.name == "posix" and subset_path.stat().st_mode & 0o077:
        raise FrozenInputError("The local benchmark subset must be private (no group/other permissions).")
    protocol_sha = sha256_file(protocol_path)
    if sidecar_path.read_text(encoding="ascii").strip().split()[0] != protocol_sha:
        raise FrozenInputError("The v7 protocol SHA-256 sidecar is missing or inconsistent.")
    protocol = _read_json(protocol_path)
    subset = _read_json(subset_path)
    if not isinstance(protocol, dict) or not isinstance(subset, list):
        raise FrozenInputError("The v7 protocol must be an object and its subset a list.")
    if protocol.get("id") != EXPECTED_PROTOCOL_ID:
        raise FrozenInputError("This runner accepts only the frozen v7 four-strategy protocol ID.")
    if protocol.get("format") != "proposal-c-four-arm-same-history-followup-v1":
        raise FrozenInputError("The v7 protocol format is not the declared exploratory follow-up.")
    selection = protocol.get("selection") or {}
    target = protocol.get("target") or {}
    source = protocol.get("source") or {}
    scorer = protocol.get("scorer") or {}
    budget = protocol.get("budget") or {}
    analysis = protocol.get("analysis") or {}
    execution = protocol.get("execution") or {}
    study = protocol.get("study_scope") or {}
    expected_per_arm = EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS
    expected_requests = expected_per_arm * len(EXPECTED_STRATEGIES)
    if selection.get("case_count") != EXPECTED_CASE_COUNT or len(subset) != EXPECTED_CASE_COUNT:
        raise FrozenInputError("The v7 selection must contain exactly the preserved 30 cases.")
    if selection.get("batch_size") != EXPECTED_BATCH_SIZE or target.get("planned_target_requests") != expected_requests:
        raise FrozenInputError("The frozen v7 batch size or target request count is invalid.")
    if target.get("memory_strategies") != EXPECTED_STRATEGIES or target.get("repetitions_per_strategy") != EXPECTED_REPETITIONS:
        raise FrozenInputError("The v7 protocol must compare the four frozen strategies for three repetitions each.")
    if target.get("run_order_by_repetition") != EXPECTED_ORDER_BY_REPETITION:
        raise FrozenInputError("The four-arm counterbalanced order differs from the frozen design.")
    if (target.get("provider") != EXPECTED_PROVIDER or target.get("model") != EXPECTED_MODEL
            or scorer.get("provider") != EXPECTED_PROVIDER or scorer.get("model") != EXPECTED_MODEL):
        raise FrozenInputError("The v7 target or scorer provider/model differs from OpenRouter GPT-6 Luna.")
    if scorer.get("planned_scorer_requests") != expected_requests:
        raise FrozenInputError("The frozen v7 scorer request count must be 360.")
    if (not isinstance(budget.get("max_estimated_cost_usd"), (int, float))
            or float(budget["max_estimated_cost_usd"]) != MAX_COST_USD
            or budget.get("planned_provider_requests_total") != expected_requests * 2
            or budget.get("stop_and_preserve_partial_evidence_at_ceiling") is not True):
        raise FrozenInputError("The v7 budget must be exactly USD 0.40 and stop with partial evidence preserved.")
    if (execution.get("openrouter_minimum_start_to_start_seconds") != MIN_REQUEST_INTERVAL_SECONDS
            or execution.get("initial_cooldown_seconds") != INITIAL_COOLDOWN_SECONDS
            or execution.get("counterbalanced_strategy_order") != EXPECTED_ORDER_BY_REPETITION):
        raise FrozenInputError("The v7 request pacing or strategy order differs from its frozen protocol.")
    if (target.get("reader_configuration") != "strong" or target.get("temperature") != 0
            or target.get("random_seed") != 42 or target.get("target_memory_capacity") != 50
            or target.get("target_memory_profile") is None):
        raise FrozenInputError("The v7 target configuration differs from the frozen reader condition.")
    provider_options = target.get("provider_options") or {}
    if (provider_options.get("require_parameters") is not True
            or provider_options.get("allow_fallbacks") is not False
            or set(provider_options) - {"require_parameters", "allow_fallbacks", "only"}):
        raise FrozenInputError("The frozen target routing must require supported parameters and disable fallbacks.")
    if not isinstance(analysis.get("selection_rule"), str) or not all(
            phrase in analysis["selection_rule"].casefold()
            for phrase in ("unique highest", "2 of 3", "no clear winner")):
        raise FrozenInputError("The frozen v7 selection rule is incomplete or has changed.")
    if study.get("case_independence_claim") is not False or study.get("prior_v6_outcomes_exposed") is not True:
        raise FrozenInputError("The v7 study scope must disclose same-history and prior-outcome exposure.")

    ids = [_case_id(row) for row in subset if isinstance(row, dict)]
    if len(ids) != EXPECTED_CASE_COUNT or len(set(ids)) != EXPECTED_CASE_COUNT:
        raise FrozenInputError("The v7 subset has missing or duplicate case IDs.")
    if Counter(_case_category(row) for row in subset) != Counter(EXPECTED_CATEGORY_COUNTS):
        raise FrozenInputError("The v7 subset does not preserve the 30-case stratum allocation.")
    if dict(sorted(selection.get("strata", {}).items())) != EXPECTED_CATEGORY_COUNTS:
        raise FrozenInputError("The v7 protocol stratum counts differ from the preserved subset.")
    selected_id_digest = sha256_bytes("\n".join(sorted(ids)).encode("utf-8"))
    if selection.get("selected_question_ids_sha256") != selected_id_digest:
        raise FrozenInputError("The selected question ID set differs from its protocol binding.")
    subset_sha = sha256_file(subset_path)
    if subset_sha != selection.get("subset_sha256") or subset_sha != protocol.get("source_files", {}).get("benchmark_subset_sha256"):
        raise FrozenInputError("The v7 copied subset differs from its frozen byte hash.")
    lineage = selection.get("v6_lineage") or {}
    v6_protocol_path = _safe_root_path(root, lineage.get("protocol_path", ""), "v6 protocol")
    v6_subset_path = _safe_root_path(root, lineage.get("subset_path", ""), "v6 subset")
    v6_run_path = _safe_root_path(root, lineage.get("run_path", ""), "v6 run")
    v6_analysis_path = _safe_root_path(root, lineage.get("analysis_path", ""), "v6 analysis")
    if (sha256_file(v6_protocol_path) != lineage.get("protocol_sha256")
            or sha256_file(v6_subset_path) != lineage.get("subset_sha256")
            or sha256_file(v6_run_path) != lineage.get("run_sha256")
            or sha256_file(v6_analysis_path) != lineage.get("analysis_sha256")
            or v6_subset_path.read_bytes() != subset_path.read_bytes()):
        raise FrozenInputError("The preserved v6 protocol, subset, run, or analysis no longer matches v7 lineage.")
    v6_sidecar = v6_protocol_path.with_name("protocol.sha256")
    if v6_sidecar.is_symlink() or not v6_sidecar.is_file() or v6_sidecar.read_text(encoding="ascii").strip().split()[0] != lineage.get("protocol_sha256"):
        raise FrozenInputError("The preserved v6 protocol SHA-256 sidecar does not match the v7 lineage.")
    v6_protocol = _read_json(v6_protocol_path)
    v6_run = _read_json(v6_run_path)
    v6_analysis = _read_json(v6_analysis_path)
    if (v6_run.get("status") != "complete_automatic_collection"
            or len(v6_run.get("target_receipts", [])) != 180
            or sum(bool(g.get("verdict_usable")) for g in v6_run.get("grades", [])) != 180
            or v6_run.get("protocol_sha256") != lineage.get("protocol_sha256")
            or v6_run.get("subset_sha256") != lineage.get("subset_sha256")
            or v6_analysis.get("protocol_sha256") != lineage.get("protocol_sha256")
            or v6_analysis.get("subset_sha256") != lineage.get("subset_sha256")
            or v6_protocol.get("source_files", {}).get("benchmark_subset_sha256") != lineage.get("subset_sha256")):
        raise FrozenInputError("The v6 source evidence is not a complete and hash-bound 180-pair collection.")

    source_manifest_path = _safe_root_path(root, source.get("source_manifest", ""), "source manifest")
    oracle_path = _safe_root_path(root, source.get("oracle_source", ""), "Oracle source")
    if (sha256_file(source_manifest_path) != source.get("source_manifest_sha256")
            or sha256_file(oracle_path) != source.get("oracle_source_sha256")):
        raise FrozenInputError("The pinned dataset source or manifest changed after the v7 freeze.")
    source_manifest = _read_json(source_manifest_path)
    if source_manifest.get("license") != source.get("license") or "mit" not in str(source.get("license", "")).casefold():
        raise FrozenInputError("The v7 dataset license binding is inconsistent.")
    oracle_records = _read_json(oracle_path)
    if not isinstance(oracle_records, list) or len(oracle_records) != 500:
        raise FrozenInputError("The pinned Oracle file must contain exactly 500 source records.")
    raw_by_id = {_case_id(row): row for row in oracle_records if isinstance(row, dict)}
    if len(raw_by_id) != 500:
        raise FrozenInputError("The pinned Oracle source contains missing or duplicate question IDs.")
    manifest_oracle = next((item for item in source_manifest.get("files", [])
                            if item.get("file") == source.get("oracle_source")), None)
    if (manifest_oracle is None or manifest_oracle.get("sha256") != source.get("oracle_source_sha256")
            or manifest_oracle.get("bytes") != oracle_path.stat().st_size
            or manifest_oracle.get("commit") != source.get("revision")):
        raise FrozenInputError("The pinned Oracle revision or byte count differs from its source manifest.")
    selected = selection.get("selected_cases")
    if not isinstance(selected, list) or len(selected) != EXPECTED_CASE_COUNT:
        raise FrozenInputError("The protocol must bind every selected v6 case to its source record and sessions.")
    selected_by_id = {row.get("question_id"): row for row in selected if isinstance(row, dict)}
    if set(selected_by_id) != set(ids):
        raise FrozenInputError("The selected-case source bindings do not match the copied subset.")
    all_sessions = set()
    for row in subset:
        qid = _case_id(row)
        source_row = raw_by_id.get(qid)
        bound = selected_by_id[qid]
        if (source_row is None or canonical_json_sha256(source_row) != bound.get("record_sha256")
                or canonical_json_sha256(source_row) != canonical_json_sha256(row)
                or bound.get("category") != _case_category(row)):
            raise FrozenInputError(f"Selected case {qid} differs from the pinned Oracle record.")
        sessions = sorted(set(row.get("haystack_session_ids", []) + row.get("answer_session_ids", [])))
        if sessions != bound.get("evidence_session_ids"):
            raise FrozenInputError(f"Selected case {qid} has a different evidence-session binding.")
        if not sessions or all_sessions.intersection(sessions):
            raise FrozenInputError("The v7 subset contains overlapping or empty evidence-session IDs.")
        all_sessions.update(sessions)
    if len(all_sessions) != selection.get("selected_evidence_session_count"):
        raise FrozenInputError("The unique evidence-session count differs from its protocol binding.")

    upstream_dir = directory / "upstream"
    if not upstream_dir.is_dir() or upstream_dir.is_symlink():
        raise FrozenInputError("The v7 pinned upstream scorer snapshot is missing.")
    for name in ("source-binding.json", "evaluate_qa.py", "LICENSE"):
        path = upstream_dir / name
        if path.is_symlink() or not path.is_file():
            raise FrozenInputError(f"The v7 pinned scorer file is missing or unsafe: {name}")
    binding = _read_json(upstream_dir / "source-binding.json")
    if (binding != protocol.get("upstream_scorer_binding")
            or sha256_file(upstream_dir / "evaluate_qa.py") != binding.get("source_sha256")
            or sha256_file(upstream_dir / "evaluate_qa.py") != protocol.get("upstream_scorer_source_sha256")
            or sha256_file(upstream_dir / "LICENSE") != protocol.get("upstream_scorer_license_sha256")):
        raise FrozenInputError("The copied v7 upstream scorer does not match its pinned source binding.")

    bound_files = protocol.get("app_source")
    if not isinstance(bound_files, dict) or not bound_files:
        raise FrozenInputError("The v7 protocol lacks application and runner source hashes.")
    required = {
        "scripts/run_phase4_c_four_arm_v7.py": protocol.get("runner_sha256"),
        "scripts/analyze_phase4_c_four_arm_v7.py": protocol.get("analyzer_sha256"),
        "scripts/prepare_phase4_c_four_arm_v7.py": protocol.get("preparer_sha256"),
        "scripts/longmemeval_grading.py": protocol.get("grader_helper_sha256"),
    }
    if any(bound_files.get(path) != digest for path, digest in required.items()):
        raise FrozenInputError("The v7 code hash bindings are incomplete or inconsistent.")
    for relative, expected in bound_files.items():
        path = _safe_root_path(root, relative, "application source")
        if sha256_file(path) != expected:
            raise FrozenInputError(f"Frozen application source has changed: {relative}")
    return {
        "root": root, "directory": directory, "protocol": protocol,
        "protocol_sha256": protocol_sha, "subset": subset, "subset_sha256": subset_sha,
        "source_manifest": source_manifest, "upstream_binding": binding, "ordered_case_ids": ids,
    }

def _iter_batches(records: list[dict[str, Any]], batch_size: int) -> list[tuple[int, list[dict[str, Any]]]]:
    return [(index, records[start:start + batch_size]) for index, start in enumerate(range(0, len(records), batch_size))]


def _cost_bound_target(payload: dict[str, Any], output_limit: int) -> float:
    chars = sum(len(str(message.get("content", ""))) for message in payload.get("messages", []))
    estimated_input_tokens = math.ceil(chars / 3)
    return estimated_input_tokens * TARGET_INPUT_USD_PER_TOKEN + output_limit * TARGET_OUTPUT_USD_PER_TOKEN


def _cost_bound_grader(prompt: str) -> float:
    return math.ceil(len(prompt) / 3) * GRADER_INPUT_USD_PER_TOKEN + 128 * GRADER_OUTPUT_USD_PER_TOKEN


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _paced_post(httpx_module, report: dict[str, Any], save):
    """Wrap every HTTP POST in this process with frozen start spacing and audit timestamps."""
    original = httpx_module.post
    lock = threading.Lock()
    process_started = time.monotonic()
    last_start: float | None = None
    session = {
        "session_id": f"{os.getpid()}-{time.time_ns()}",
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "request_starts_utc": [],
    }
    report.setdefault("pacing_sessions", []).append(session)
    save()

    def post(*args, **kwargs):
        nonlocal last_start
        with lock:
            now = time.monotonic()
            wait_for = INITIAL_COOLDOWN_SECONDS - (now - process_started) if last_start is None else \
                MIN_REQUEST_INTERVAL_SECONDS - (now - last_start)
            if wait_for > 0:
                time.sleep(wait_for)
            session["request_starts_utc"].append(datetime.now(timezone.utc).isoformat(timespec="microseconds"))
            report.setdefault("provider_dispatch_starts_utc", []).append(session["request_starts_utc"][-1])
            # The request intent is already durable; this timestamp is durable before dispatch too.
            save()
            last_start = time.monotonic()
            return original(*args, **kwargs)

    return original, post


@contextmanager
def _exclusive_run_lock(directory: Path):
    lock_path = directory / ".phase4-c-four-arm-v7.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another v7 collector already holds the run lock.") from exc
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()}\n")
        lock.flush()
        os.fsync(lock.fileno())
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _empty_report(inputs: dict[str, Any], max_cost_usd: float) -> dict[str, Any]:
    protocol = inputs["protocol"]
    return {
        "format": "proposal-c-four-arm-live-run-v1",
        "scope": "exploratory_four_strategy_replay_on_same_v6_histories_not_official_full_benchmark",
        "protocol_id": protocol["id"],
        "protocol_sha256": inputs["protocol_sha256"],
        "subset_sha256": inputs["subset_sha256"],
        "source_manifest_sha256": protocol["source"]["source_manifest_sha256"],
        "oracle_source_sha256": protocol["source"]["oracle_source_sha256"],
        "source_revision": protocol["source"]["revision"],
        "upstream_binding": inputs["upstream_binding"],
        "target_configuration": {
            "provider": EXPECTED_PROVIDER,
            "model": EXPECTED_MODEL,
            "strategies": EXPECTED_STRATEGIES,
            "repetitions": EXPECTED_REPETITIONS,
            "case_count": EXPECTED_CASE_COUNT,
            "planned_target_answers": 360,
            "planned_grader_answers": 360,
            "batch_size": EXPECTED_BATCH_SIZE,
        },
        "reader_runs": [],
        "target_call_intents": [],
        "target_receipts": [],
        "grades": [],
        "status": "running",
        "estimated_cost_usd": 0.0,
        "usage_based_cost_estimate_usd": 0.0,
        "cost_rate_assumptions_usd_per_token": {
            "target_input": TARGET_INPUT_USD_PER_TOKEN,
            "target_output": TARGET_OUTPUT_USD_PER_TOKEN,
            "grader_input": GRADER_INPUT_USD_PER_TOKEN,
            "grader_output": GRADER_OUTPUT_USD_PER_TOKEN,
        },
        "max_cost_usd": max_cost_usd,
        "provider_dispatch_starts_utc": [],
        "billing_uncertain": False,
        "compatibility_limitations": [
            "This reuses the existing v6 30 cases; it is a local exploratory four-arm replay, not a fresh sample or the complete official benchmark.",
            "New question IDs and frozen evidence-session identifiers do not guarantee statistical independence; shared filler sessions or scenario themes may remain correlated.",
            "The controlled-memory reader and app adapter are not the official LongMemEval execution stack.",
            "The upstream prompt is paired with an OpenRouter GPT-6 Luna judge; this is not the benchmark's official metric model or independent human calibration.",
            "Provider seed is recorded but not enforced; scores are automatic and do not establish Auditor validity or generalisation.",
            "The historic v5 run used a different collection period/source-code snapshot; any 44-case combined summary is secondary and is never pooled into the v7 winner rule.",
        ],
    }


def _find_record(records: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    return next((record for record in records if predicate(record)), None)


def _validate_resume_state(report: dict[str, Any], inputs: dict[str, Any], max_cost_usd: float) -> None:
    if report.get("protocol_sha256") != inputs["protocol_sha256"] or report.get("subset_sha256") != inputs["subset_sha256"]:
        raise FrozenInputError("The existing run receipt is bound to a different protocol or subset.")
    if report.get("protocol_id") != EXPECTED_PROTOCOL_ID:
        raise FrozenInputError("The existing run receipt is not the v7 four-arm experiment.")
    try:
        old_cap = float(report.get("max_cost_usd", max_cost_usd))
        estimated_cost = float(report.get("estimated_cost_usd", 0.0))
        usage_estimate = float(report.get("usage_based_cost_estimate_usd", 0.0))
    except (TypeError, ValueError) as exc:
        raise FrozenInputError("The existing run receipt has malformed cost totals.") from exc
    if (not math.isfinite(old_cap) or old_cap <= 0 or old_cap > MAX_COST_USD + 1e-12
            or not math.isfinite(estimated_cost) or estimated_cost < 0
            or not math.isfinite(usage_estimate) or usage_estimate < 0):
        raise FrozenInputError("The existing run receipt has an invalid or over-limit USD cost budget.")
    if estimated_cost > old_cap + 1e-12:
        raise ResumeBlockedError("The saved estimated spend is already at or above the cap; preserve the evidence and do not dispatch more requests.")
    if report.get("format") != "proposal-c-four-arm-live-run-v1":
        raise FrozenInputError("The existing run receipt has an unexpected v7 format.")
    target_config = report.get("target_configuration", {})
    if (target_config.get("provider") != EXPECTED_PROVIDER or target_config.get("model") != EXPECTED_MODEL
            or target_config.get("strategies") != EXPECTED_STRATEGIES
            or target_config.get("repetitions") != EXPECTED_REPETITIONS
            or target_config.get("case_count") != EXPECTED_CASE_COUNT):
        raise FrozenInputError("The existing run receipt target matrix differs from the frozen v7 protocol.")
    if max_cost_usd > old_cap + 1e-12:
        raise FrozenInputError("A resumed run cannot raise its previously recorded USD cost ceiling.")
    if report.get("status") in {"complete_automatic_collection", "partial_grader_uncertainty"}:
        raise RuntimeError("The v7 collection is already complete or explicitly finalized; do not repeat provider calls.")
    receipts = {(r.get("repetition"), r.get("strategy"), r.get("question_id")) for r in report.get("target_receipts", [])}
    if len(receipts) != len(report.get("target_receipts", [])):
        raise FrozenInputError("The existing target receipt file contains duplicate response identities.")
    grade_keys = [(g.get("repetition"), g.get("strategy"), g.get("question_id")) for g in report.get("grades", [])]
    if len(set(grade_keys)) != len(grade_keys):
        raise FrozenInputError("The existing grader receipt file contains duplicate response identities.")
    if len(receipts) > EXPECTED_CASE_COUNT * len(EXPECTED_STRATEGIES) * EXPECTED_REPETITIONS or len(grade_keys) > EXPECTED_CASE_COUNT * len(EXPECTED_STRATEGIES) * EXPECTED_REPETITIONS:
        raise FrozenInputError("The existing v7 run contains records outside the frozen 360-answer matrix.")
    for intent in report.get("target_call_intents", []):
        key = (intent.get("repetition"), intent.get("strategy"), intent.get("question_id"))
        if intent.get("status") in {"dispatching", "pending", "unknown", "failed"} and key not in receipts:
            if not intent.get("attempts") and intent.get("status") in {"dispatching", "failed"}:
                # The connector journals before-send before httpx.post. No attempts means no HTTP dispatch occurred.
                intent["status"] = "not_dispatched_resumable"
            else:
                raise ResumeBlockedError(
                    "A prior target request has an attempted or uncertain provider outcome without a saved answer; automatic resume is blocked to prevent duplicate spend."
                )
        if intent.get("status") == "completed" and key not in receipts:
            raise FrozenInputError("A completed target-call intent has no saved target response.")
    for grade in report.get("grades", []):
        if grade.get("request_payload_sha256") != canonical_json_sha256(grade.get("request_payload")):
            raise FrozenInputError("A saved grader request differs from its frozen request hash.")
        if grade.get("status") in {"pending_provider_result", "unknown"}:
            raise ResumeBlockedError("A prior grader request has an unknown provider outcome; automatic resume is blocked.")
        for attempt in grade.get("attempts", []):
            if attempt.get("status") in {"pending", "unknown"}:
                raise ResumeBlockedError(
                    "A prior grader request is pending without a saved response; automatic resume is blocked to prevent a duplicate call."
                )


def _score_from_raw(raw: str, finish_reason: str | None) -> tuple[bool | None, bool]:
    verdict_usable = bool(re.fullmatch(r"(?:yes|no)[.!]?", raw.strip(), re.I)) and finish_reason == "stop"
    if not verdict_usable:
        return None, False
    return raw.strip().casefold().startswith("yes"), True


def _execution_attempt_observer(report: dict[str, Any], intent: dict[str, Any], save, reserve_cost: float):
    def observer(receipt: dict[str, Any]) -> None:
        phase = receipt.get("phase")
        attempt_index = receipt.get("attempt_index")
        attempts = intent.setdefault("attempts", [])
        attempt = _find_record(attempts, lambda item: item.get("attempt_index") == attempt_index)
        if phase == "before_send":
            if attempt is not None:
                raise ResumeBlockedError("The target connector tried to reuse a provider attempt index.")
            actual_digest = (receipt.get("request_contract") or {}).get("payload_sha256")
            if actual_digest != intent.get("request_payload_sha256"):
                raise FrozenInputError("The actual pre-send target payload differs from the frozen intent; request was blocked before dispatch.")
            _ensure_cost(report, reserve_cost, "target", save)
            attempt = {
                "attempt_index": attempt_index,
                "status": "pending",
                "request_contract_sha256": receipt.get("request_contract_sha256"),
                "request_contract": receipt.get("request_contract"),
                "reserved_estimated_cost_usd": reserve_cost,
            }
            attempts.append(attempt)
            report["estimated_cost_usd"] = round(report["estimated_cost_usd"] + reserve_cost, 10)
            save()
        elif phase == "after_send":
            if attempt is None:
                raise FrozenInputError("The target connector returned an attempt without a before-send receipt.")
            attempt.update({
                "status": receipt.get("status", "unknown"),
                "http_status": receipt.get("http_status"),
                "error_type": receipt.get("error_type"),
            })
            http_status = receipt.get("http_status")
            if receipt.get("status") in {"transport_error", "response"} and isinstance(http_status, int) and http_status >= 500:
                report["billing_uncertain"] = True
            save()
        else:
            raise FrozenInputError("Unexpected target request receipt phase.")
    return observer


def _ensure_cost(report: dict[str, Any], reserve: float, role: str, save=None) -> None:
    cap = float(report["max_cost_usd"])
    current = float(report["estimated_cost_usd"])
    if not math.isfinite(cap) or not math.isfinite(current) or not math.isfinite(reserve) or cap > MAX_COST_USD + 1e-12:
        raise FrozenInputError("The v7 USD cost ledger is malformed or exceeds the hard ceiling.")
    if current + reserve > cap + 1e-12:
        report["status"] = "paused_cost_ceiling"
        if save is not None:
            save()
        raise RuntimeError(f"The frozen USD {cap:.2f} cost ceiling was reached before the next {role} request.")


def _update_actual_cost(report: dict[str, Any], attempts: list[dict[str, Any]], final_usage: dict[str, Any] | None,
                        input_rate: float, output_rate: float) -> None:
    if not final_usage:
        return
    input_tokens = final_usage.get("input_tokens", final_usage.get("prompt_tokens"))
    output_tokens = final_usage.get("output_tokens", final_usage.get("completion_tokens"))
    if not isinstance(input_tokens, (int, float)) or not isinstance(output_tokens, (int, float)):
        return
    actual = float(input_tokens) * input_rate + float(output_tokens) * output_rate
    report["usage_based_cost_estimate_usd"] = round(report["usage_based_cost_estimate_usd"] + actual, 10)
    if attempts:
        reserve = float(attempts[-1].get("reserved_estimated_cost_usd", 0.0))
        report["estimated_cost_usd"] = round(max(0.0, report["estimated_cost_usd"] - reserve + actual), 10)
    if report["estimated_cost_usd"] > float(report["max_cost_usd"]) + 1e-12:
        report["status"] = "paused_cost_ceiling"


def run_four_arm(root: Path, directory: Path, max_cost_usd: float | None = None,
                  dependencies: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute/resume the frozen v7 matrix. Dependencies are injectable for offline tests."""
    inputs = validate_frozen_inputs(root, directory)
    protocol = inputs["protocol"]
    frozen_cap = float(protocol["budget"]["max_estimated_cost_usd"])
    effective_cap = frozen_cap if max_cost_usd is None else min(frozen_cap, float(max_cost_usd))
    if effective_cap <= 0:
        raise ValueError("--max-cost-usd must be positive.")
    configured_provider = os.getenv("OPENROUTER_PROVIDER", "").strip()
    _validate_target_provider_environment(protocol, configured_provider)

    real_execution = not dependencies
    dependencies = dependencies or {}
    if not dependencies:
        # Delay product imports until after every frozen input and checksum is validated.
        backend = str(inputs["root"] / "backend")
        scripts = str(inputs["root"] / "scripts")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from app.benchmarks.live import LiveBenchmarkRunner
        from app.schemas import TargetResponse
        from app.schemas.benchmark import LiveBenchmarkRequest, LiveBenchmarkResponse
        from app.target_ai.openrouter import build_openrouter_target_payload
        from app.target_ai.providers import HttpTargetAIConnector
        from app.target_ai.request_contracts import observe_request_contracts, request_contract_sha256
        from app.target_ai.rule_based import private_context_instruction, target_question_input
        from longmemeval_grading import build_openrouter_grader_payload, load_upstream_prompt
        import httpx
        dependencies = {
            "LiveBenchmarkRunner": LiveBenchmarkRunner,
            "LiveBenchmarkRequest": LiveBenchmarkRequest,
            "LiveBenchmarkResponse": LiveBenchmarkResponse,
            "TargetResponse": TargetResponse,
            "HttpTargetAIConnector": HttpTargetAIConnector,
            "build_openrouter_target_payload": build_openrouter_target_payload,
            "request_contract_sha256": request_contract_sha256,
            "private_context_instruction": private_context_instruction,
            "target_question_input": target_question_input,
            "observe_request_contracts": observe_request_contracts,
            "build_openrouter_grader_payload": build_openrouter_grader_payload,
            "load_upstream_prompt": load_upstream_prompt,
            "httpx": httpx,
        }

    if real_execution and os.getenv("OPENROUTER_API_KEY", "").strip() == "":
        raise RuntimeError("OPENROUTER_API_KEY is not configured; no model requests were sent.")

    request_factory = dependencies["LiveBenchmarkRequest"]
    response_model = dependencies["LiveBenchmarkResponse"]
    target_response_model = dependencies["TargetResponse"]
    connector_type = dependencies["HttpTargetAIConnector"]
    build_target_payload = dependencies["build_openrouter_target_payload"]
    request_hash = dependencies["request_contract_sha256"]
    make_instructions = dependencies["private_context_instruction"]
    question_input = dependencies["target_question_input"]
    observe_contracts = dependencies["observe_request_contracts"]
    build_grader_payload = dependencies["build_openrouter_grader_payload"]
    load_prompt = dependencies["load_upstream_prompt"]
    httpx = dependencies["httpx"]
    runner = dependencies.get("runner") or dependencies["LiveBenchmarkRunner"]()
    prompt_function, upstream_binding = load_prompt(inputs["directory"] / "upstream")
    if upstream_binding != inputs["upstream_binding"]:
        raise FrozenInputError("The loaded upstream prompt binding changed after freeze.")

    run_path = inputs["directory"] / "C-live.json"
    if run_path.exists():
        report = _read_json(run_path)
        _validate_resume_state(report, inputs, effective_cap)
        report["max_cost_usd"] = effective_cap
        report["status"] = "running"
    else:
        report = _empty_report(inputs, effective_cap)

    def save() -> None:
        _atomic_write_json(run_path, report)

    original_execute = connector_type.execute
    original_http_post = None
    if real_execution:
        original_http_post, httpx.post = _paced_post(httpx, report, lambda: _atomic_write_json(run_path, report))
    current: dict[str, Any] = {}

    def capture(connector, test, audit):
        case_id = current["case_ids"][current["case_index"]]
        current["case_index"] += 1
        intent_key = f"{current['repetition']}:{current['strategy']}:{case_id}"
        saved_receipt = _find_record(report["target_receipts"], lambda row: (
            row.get("repetition"), row.get("strategy"), row.get("question_id")
        ) == (current["repetition"], current["strategy"], case_id))
        if saved_receipt is not None:
            old_payload = saved_receipt["verified_request_payload"]
            candidate = build_target_payload(
                model=audit.model,
                instructions=make_instructions(test, audit.target_configuration),
                prompt=question_input(test.prompt),
                temperature=audit.temperature,
                max_output_tokens=audit.target_memory_profile.output_token_limit,
                provider_options=old_payload["provider"],
            )
            if candidate != old_payload:
                raise FrozenInputError("A saved target answer does not match the exact frozen OpenRouter request; refusing replay.")
            return target_response_model.model_validate(saved_receipt["response"]).model_copy(
                deep=True, update={"test_id": test.test_id, "run_id": audit.run_id}
            )

        existing_intent = _find_record(report["target_call_intents"], lambda row: row.get("intent_key") == intent_key)

        prior_target = report["target_receipts"]
        provider_options = (
            prior_target[-1]["verified_request_payload"]["provider"] if prior_target else
            protocol.get("target", {}).get("provider_options", {"require_parameters": True, "allow_fallbacks": False})
        )
        candidate = build_target_payload(
            model=audit.model,
            instructions=make_instructions(test, audit.target_configuration),
            prompt=question_input(test.prompt),
            temperature=audit.temperature,
            max_output_tokens=audit.target_memory_profile.output_token_limit,
            provider_options=provider_options,
        )
        candidate_hash = request_hash(candidate)
        reserve = _cost_bound_target(candidate, int(audit.target_memory_profile.output_token_limit or 2048))
        _ensure_cost(report, reserve, "target", save)
        if existing_intent is not None:
            if (existing_intent.get("request_payload_sha256") != candidate_hash
                    or existing_intent.get("attempts")
                    or existing_intent.get("status") not in {"not_dispatched_resumable", "not_dispatched_cost_ceiling", "not_dispatched_preflight_failure"}):
                raise ResumeBlockedError("A target-call intent already has a possible provider outcome; refusing duplicate dispatch.")
            intent = existing_intent
            intent.update(status="dispatching", error_type=None, status_code=None)
        else:
            intent = {
                "intent_key": intent_key,
                "repetition": current["repetition"],
                "strategy": current["strategy"],
                "question_id": case_id,
                "request_payload_sha256": candidate_hash,
                "status": "dispatching",
                "attempts": [],
            }
            report["target_call_intents"].append(intent)
        save()
        observer = _execution_attempt_observer(report, intent, save, reserve)
        try:
            with observe_contracts(observer):
                response = original_execute(connector, test, audit)
        except BaseException as exc:
            if report.get("status") == "paused_cost_ceiling" and not intent["attempts"]:
                intent["status"] = "not_dispatched_cost_ceiling"
                save()
                raise
            if not intent["attempts"]:
                intent["status"] = "not_dispatched_preflight_failure"
                intent["error_type"] = type(exc).__name__
                report["status"] = "failed_before_target_dispatch"
                save()
                raise
            intent["status"] = "failed"
            intent["error_type"] = type(exc).__name__
            status_code = getattr(exc, "status_code", None)
            if status_code is not None:
                intent["status_code"] = status_code
            if any(attempt.get("status") == "pending" for attempt in intent["attempts"]):
                intent["status"] = "unknown"
            report["billing_uncertain"] = True
            if report.get("status") != "paused_cost_ceiling":
                report["status"] = "failed_target_request"
            save()
            raise

        meta = response.execution_metadata.model_dump(mode="json")
        contract = meta.get("request_contract") or {}
        actual_payload = build_target_payload(
            model=audit.model,
            instructions=make_instructions(test, audit.target_configuration),
            prompt=question_input(test.prompt),
            temperature=audit.temperature,
            max_output_tokens=audit.target_memory_profile.output_token_limit,
            provider_options=(contract.get("provider") or {}).get("value", provider_options),
        )
        if request_hash(actual_payload) != (contract.get("payload_sha256") or intent["request_payload_sha256"]):
            intent["status"] = "unknown"
            report["billing_uncertain"] = True
            report["status"] = "failed_request_binding"
            save()
            raise FrozenInputError("The actual target request differs from the frozen request contract.")
        receipt = {
            "repetition": current["repetition"],
            "strategy": current["strategy"],
            "question_id": case_id,
            "response": response.model_dump(mode="json"),
            "response_sha256": sha256_bytes(response.response_text.encode("utf-8")),
            "verified_request_payload": actual_payload,
            "request_payload_sha256": request_hash(actual_payload),
            "request_contract_attempts": meta.get("request_contract_attempts", []),
            "provider_attempt_count": meta.get("request_attempts", 1),
            "input_tokens": meta.get("input_tokens"),
            "output_tokens": meta.get("output_tokens"),
            "reported_model": meta.get("reported_model"),
        }
        report["target_receipts"].append(receipt)
        intent["status"] = "completed"
        intent["response_sha256"] = sha256_bytes(response.response_text.encode("utf-8"))
        _update_actual_cost(report, intent["attempts"], {
            "input_tokens": meta.get("input_tokens"), "output_tokens": meta.get("output_tokens")
        }, TARGET_INPUT_USD_PER_TOKEN, TARGET_OUTPUT_USD_PER_TOKEN)
        save()
        print(f"saved_target_receipt={len(report['target_receipts'])}", flush=True)
        return response

    connector_type.execute = capture
    try:
        save()
        case_batches = _iter_batches(inputs["subset"], EXPECTED_BATCH_SIZE)
        for repetition in range(1, EXPECTED_REPETITIONS + 1):
            for strategy in EXPECTED_ORDER_BY_REPETITION[str(repetition)]:
                for batch_index, batch_records in case_batches:
                    case_ids = [_case_id(record) for record in batch_records]
                    saved_run = _find_record(report["reader_runs"], lambda row: (
                        row.get("repetition"), row.get("strategy"), row.get("batch_index")
                    ) == (repetition, strategy, batch_index))
                    if saved_run is None:
                        payload = batch_records
                        request = request_factory(
                            payload=payload,
                            source_authorised=True,
                            source_label="Exploratory replay of the exact pre-existing v6 LongMemEval histories",
                            dataset_provenance={
                                "dataset_version": protocol["source"]["revision"],
                                "license": protocol["source"]["license"],
                                "citation": "Wu et al., LongMemEval, ICLR 2025; https://github.com/xiaowu0162/LongMemEval",
                            },
                            provider=EXPECTED_PROVIDER,
                            model=EXPECTED_MODEL,
                            strategies=[strategy],
                            max_cases=len(batch_records),
                            target_memory_capacity=int(protocol["target"]["target_memory_capacity"]),
                            target_memory_profile=protocol["target"].get("target_memory_profile", protocol["target"].get("profile")),
                            temperature=float(protocol["target"]["temperature"]),
                            random_seed=int(protocol["target"]["random_seed"]),
                        )
                        current.update(repetition=repetition, strategy=strategy, batch_index=batch_index,
                                       case_ids=case_ids, case_index=0)
                        response = runner.run(request)
                        response_dict = response.model_dump(mode="json")
                        if len(response_dict.get("conditions", [])) != 1:
                            raise FrozenInputError("The reader returned an unexpected number of conditions.")
                        returned_cases = response_dict["conditions"][0].get("cases", [])
                        if [_case_id({"case_id": item.get("case_id")}) for item in returned_cases] != case_ids:
                            raise FrozenInputError("The reader returned cases outside the exact frozen batch order.")
                        saved_run = {
                            "repetition": repetition,
                            "strategy": strategy,
                            "batch_index": batch_index,
                            "question_ids": case_ids,
                            "result": response_dict,
                        }
                        report["reader_runs"].append(saved_run)
                        save()
                    else:
                        if saved_run.get("question_ids") != case_ids:
                            raise FrozenInputError("A saved reader batch does not match its frozen case IDs.")
                        response_dict = saved_run.get("result", {})

                    condition = response_dict.get("conditions", [{}])[0]
                    cases_by_id = {item.get("case_id"): item for item in condition.get("cases", [])}
                    if set(cases_by_id) != set(case_ids):
                        raise FrozenInputError("A saved reader run has missing or extra case results.")
                    for case_record in batch_records:
                        qid = _case_id(case_record)
                        if _find_record(report["grades"], lambda row: (
                            row.get("repetition"), row.get("strategy"), row.get("question_id")
                        ) == (repetition, strategy, qid) and row.get("verdict_usable")):
                            continue
                        case_result = cases_by_id[qid]
                        prompt = prompt_function(
                            case_result.get("category", case_record.get("question_type", case_record.get("category"))),
                            case_record["question"], case_record["answer"], case_result["response_text"],
                            abstention="_abs" in qid,
                        )
                        payload = build_grader_payload(protocol["scorer"]["model"], prompt)
                        payload_hash = canonical_json_sha256(payload)
                        grade = _find_record(report["grades"], lambda row: (
                            row.get("repetition"), row.get("strategy"), row.get("question_id")
                        ) == (repetition, strategy, qid))
                        if grade is None:
                            grade = {
                                "repetition": repetition,
                                "strategy": strategy,
                                "question_id": qid,
                                "question_type": case_result.get("category", case_record.get("question_type", case_record.get("category"))),
                                "stratum": _case_category(case_record),
                                "target_response_sha256": sha256_bytes(case_result["response_text"].encode("utf-8")),
                                "upstream_prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                                "request_payload": payload,
                                "request_payload_sha256": payload_hash,
                                "attempts": [],
                                "status": "pending",
                            }
                            report["grades"].append(grade)
                            save()
                        elif grade.get("request_payload_sha256") != payload_hash or grade.get("request_payload") != payload:
                            raise FrozenInputError("A saved grader request does not match the frozen prompt and response.")
                        elif grade.get("target_response_sha256") != sha256_bytes(case_result["response_text"].encode("utf-8")):
                            raise FrozenInputError("A saved grader receipt is bound to a different target answer.")
                        _run_grader_attempts(grade, report, save, httpx, float(protocol["budget"]["max_estimated_cost_usd"]))
                        print(f"saved_grade={sum(bool(g.get('verdict_usable')) for g in report['grades'])}", flush=True)

        expected = EXPECTED_CASE_COUNT * len(EXPECTED_STRATEGIES) * EXPECTED_REPETITIONS
        unique_target = {(r["repetition"], r["strategy"], r["question_id"]) for r in report["target_receipts"]}
        unique_grades = {(r["repetition"], r["strategy"], r["question_id"]) for r in report["grades"]}
        if len(unique_target) != len(report["target_receipts"]) or len(unique_grades) != len(report["grades"]):
            raise FrozenInputError("The collected v7 records contain duplicate provider-response identities.")
        all_usable = len(unique_target) == expected and len(unique_grades) == expected and all(g.get("verdict_usable") for g in report["grades"])
        if report.get("status") != "paused_cost_ceiling":
            report["status"] = "complete_automatic_collection" if all_usable else "partial_grader_uncertainty"
        report["completed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save()
        return report
    except BaseException:
        if report.get("status") == "running":
            report["status"] = "failed_with_receipts"
            save()
        raise
    finally:
        connector_type.execute = original_execute
        if original_http_post is not None:
            httpx.post = original_http_post


def _run_grader_attempts(grade: dict[str, Any], report: dict[str, Any], save, httpx, frozen_ceiling: float) -> None:
    if grade.get("verdict_usable"):
        return
    if os.getenv("OPENROUTER_API_KEY", "").strip() == "":
        raise RuntimeError("OPENROUTER_API_KEY is not configured; no grader request was sent.")
    if grade.get("status") in {"pending_provider_result", "unknown"}:
        raise ResumeBlockedError("A prior grader provider response is uncertain; refusing a duplicate grader request.")
    # A response body saved before parsing can be completed locally after a restart.
    for attempt in grade.get("attempts", []):
        if attempt.get("status") == "response_saved" and attempt.get("response_body"):
            _parse_grader_response(grade, attempt)
            save()
            if grade.get("verdict_usable"):
                return

    prompt_payload = grade["request_payload"]
    attempts = grade.setdefault("attempts", [])
    consumed_indices = {a.get("attempt") for a in attempts}
    next_attempt = max([int(v) for v in consumed_indices if isinstance(v, int)] or [0]) + 1
    for attempt_index in range(next_attempt, MAX_PROVIDER_ATTEMPTS + 1):
        bound = _cost_bound_grader(prompt_payload["messages"][0]["content"])
        cap = min(float(report["max_cost_usd"]), float(frozen_ceiling))
        if report["estimated_cost_usd"] + bound > cap + 1e-12:
            report["status"] = "paused_cost_ceiling"
            save()
            raise RuntimeError(f"The frozen USD {cap:.2f} cost ceiling was reached before the grader request.")
        intent = {
            "attempt": attempt_index,
            "status": "pending",
            "request_payload_sha256": grade["request_payload_sha256"],
            "reserved_estimated_cost_usd": bound,
        }
        attempts.append(intent)
        report["estimated_cost_usd"] = round(report["estimated_cost_usd"] + bound, 10)
        save()
        response = None
        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                json=prompt_payload,
                timeout=60,
            )
        except BaseException as exc:
            intent.update(status="unknown", error_type=type(exc).__name__)
            grade["status"] = "unknown"
            report["billing_uncertain"] = True
            report["status"] = "failed_grader_transport"
            save()
            raise
        # Journal the complete HTTP response before parsing any grade.
        intent.update(status="response_saved", http_status=response.status_code,
                      request_id=response.headers.get("x-request-id"), response_body=response.text)
        save()
        if response.status_code in {408, 429, 500, 502, 503, 504}:
            report["billing_uncertain"] = True
            if attempt_index < MAX_PROVIDER_ATTEMPTS:
                intent["status"] = "retryable_response_saved"
                save()
                time.sleep(1)
                continue
        if response.status_code >= 400:
            intent["status"] = "provider_error_saved"
            grade["status"] = "failed_provider_response"
            report["billing_uncertain"] = True
            report["status"] = "failed_grader_http"
            save()
            response.raise_for_status()
        _update_actual_cost(report, [intent], response.json().get("usage", {}),
                            GRADER_INPUT_USD_PER_TOKEN, GRADER_OUTPUT_USD_PER_TOKEN)
        intent["status"] = "response_saved"
        _parse_grader_response(grade, intent)
        save()
        if grade.get("verdict_usable"):
            return
    grade["status"] = "unusable_response_saved"
    save()


def _parse_grader_response(grade: dict[str, Any], attempt: dict[str, Any]) -> None:
    try:
        body = json.loads(attempt["response_body"])
    except (KeyError, json.JSONDecodeError):
        grade["status"] = "unusable_response_saved"
        return
    usage = body.get("usage", {})
    grade["reported_model"] = body.get("model")
    grade["usage"] = usage
    choice = ((body.get("choices") or [{}])[0])
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        raw = content.strip()
    elif isinstance(content, list):
        raw = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    else:
        raw = ""
    label, usable = _score_from_raw(raw, choice.get("finish_reason"))
    grade["raw_verdict"] = raw
    grade["finish_reason"] = choice.get("finish_reason")
    grade["autoeval_label"] = ("yes" in raw.casefold())
    grade["verdict_usable"] = usable
    grade["correct"] = label if usable else None
    grade["status"] = "complete" if usable else "unusable_response_saved"
    if not usable:
        grade["unusable_reason"] = "The upstream yes/no convention did not return strict yes/no text with a stop finish reason."


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("MHA_PROJECT_ROOT", Path(__file__).resolve().parents[1])))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--max-cost-usd", type=float, default=None,
                        help="Lower the frozen v7 USD ceiling; a resumed run cannot raise its existing cap.")
    args = parser.parse_args()
    root = args.root.resolve()
    directory = args.directory if args.directory.is_absolute() else root / args.directory
    with _exclusive_run_lock(directory.resolve()):
        report = run_four_arm(root, directory, args.max_cost_usd)
    print(json.dumps({
        "status": report["status"],
        "target_receipts": len(report["target_receipts"]),
        "usable_grades": sum(bool(grade.get("verdict_usable")) for grade in report["grades"]),
        "estimated_cost_usd": report["estimated_cost_usd"],
        "usage_based_cost_estimate_usd": report["usage_based_cost_estimate_usd"],
        "billing_uncertain": report["billing_uncertain"],
        "run_file": str((directory / "C-live.json")),
    }, ensure_ascii=False))


if __name__ == "__main__":
    _main()
