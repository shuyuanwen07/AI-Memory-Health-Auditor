"""Freeze a four-strategy C follow-up on the exact v6 30-case subset.

This preparer is offline and never edits or reuses the v6 result directory.
The v7 study is an exploratory same-history policy comparison, not a new
independent sample or a full LongMemEval evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V6_DIR = Path("artifacts/local/phase4-c-openrouter-20261028-v6")
DEFAULT_OUTPUT = Path("artifacts/local/phase4-c-openrouter-20261028-v7-four-arm")
RELEASE = Path("output/longmemeval-official-v1")
UPSTREAM = Path("experiments/longmemeval-expanded-20261019/upstream-evaluator")
V7_ID = "phase4-c-openrouter-gpt6-luna-four-arm-20261028-v7"
MODEL = "openai/gpt-6-luna"
STRATEGIES = ["weak_first_hit", "strong_rule_based", "scope_aware", "temporal_importance"]
ORDER_BY_REPETITION = {
    "1": ["weak_first_hit", "strong_rule_based", "scope_aware", "temporal_importance"],
    "2": ["scope_aware", "temporal_importance", "weak_first_hit", "strong_rule_based"],
    "3": ["temporal_importance", "weak_first_hit", "strong_rule_based", "scope_aware"],
}
CATEGORY_COUNTS = {
    "abstention": 4,
    "knowledge-update": 4,
    "multi-session": 5,
    "single-session-assistant": 4,
    "single-session-preference": 4,
    "single-session-user": 4,
    "temporal-reasoning": 5,
}
CASE_COUNT = 30
REPETITIONS = 3
BATCH_SIZE = 15
MAX_COST_USD = 0.40
MIN_REQUEST_INTERVAL_SECONDS = 4.0
RATE_LIMIT_COOLDOWN_SECONDS = 65.0


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _canonical_sha(value: Any) -> str:
    return _sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8"))


def _write_json(path: Path, value: Any, mode: int = stat.S_IRUSR | stat.S_IWUSR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(mode)


def _safe(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("A frozen lineage path is unsafe.")
    result = root / path
    if result.is_symlink() or not result.is_file():
        raise ValueError(f"A required frozen lineage file is missing or unsafe: {relative}")
    return result.resolve()


def _validate_v6(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    v6 = root / V6_DIR
    protocol_path = v6 / "protocol.json"
    sidecar_path = v6 / "protocol.sha256"
    subset_path = v6 / "longmemeval-subset.json"
    run_path = v6 / "C-live.json"
    analysis_path = v6 / "analysis.json"
    for path in (protocol_path, sidecar_path, subset_path, run_path, analysis_path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("The complete frozen v6 protocol, subset, run, and analysis must exist.")
    protocol = _read(protocol_path)
    sidecar = sidecar_path.read_text(encoding="utf-8").strip().split()
    if not sidecar or sidecar[0] != _sha(protocol_path):
        raise ValueError("The v6 protocol SHA-256 sidecar is missing or inconsistent.")
    if protocol.get("id") != "phase4-c-openrouter-gpt6-luna-expansion-20261028-v6":
        raise ValueError("The preserved source run is not the expected v6 expansion.")
    subset_bytes = subset_path.read_bytes()
    subset_sha = _sha_bytes(subset_bytes)
    if subset_sha != protocol.get("source_files", {}).get("benchmark_subset_sha256"):
        raise ValueError("The v6 subset differs from its frozen protocol.")
    subset = json.loads(subset_bytes)
    if not isinstance(subset, list) or len(subset) != CASE_COUNT:
        raise ValueError("The v6 selection must contain exactly 30 cases.")
    if os.name == "posix" and subset_path.stat().st_mode & 0o077:
        raise ValueError("The v6 subset is not private on disk.")

    run = _read(run_path)
    run_sha = _sha(run_path)
    analysis = _read(analysis_path)
    if analysis.get("protocol_sha256") != _sha(protocol_path):
        raise ValueError("The v6 analysis does not bind the preserved protocol.")
    if analysis.get("subset_sha256") != subset_sha:
        raise ValueError("The v6 analysis does not bind the preserved subset.")
    if run.get("status") != "complete_automatic_collection":
        raise ValueError("The v6 evidence must be complete before it can seed a v7 policy comparison.")
    if run.get("protocol_sha256") != _sha(protocol_path) or run.get("subset_sha256") != subset_sha:
        raise ValueError("The v6 run does not bind its saved protocol and subset.")
    if len(run.get("target_receipts", [])) != CASE_COUNT * 2 * REPETITIONS:
        raise ValueError("The v6 source run does not contain its complete 180-answer pair.")
    if len(run.get("grades", [])) != CASE_COUNT * 2 * REPETITIONS or not all(
            bool(item.get("verdict_usable")) for item in run.get("grades", [])):
        raise ValueError("The v6 source run does not contain all 180 usable automatic grades.")
    if run.get("target_configuration", {}).get("strategies") != ["weak_first_hit", "strong_rule_based"]:
        raise ValueError("The source v6 run does not contain exactly its frozen two strategies.")
    v6_lineage = {
        "protocol_id": protocol["id"],
        "protocol_path": str((V6_DIR / "protocol.json").as_posix()),
        "protocol_sha256": _sha(protocol_path),
        "subset_path": str((V6_DIR / "longmemeval-subset.json").as_posix()),
        "subset_sha256": subset_sha,
        "run_path": str((V6_DIR / "C-live.json").as_posix()),
        "run_sha256": run_sha,
        "analysis_path": str((V6_DIR / "analysis.json").as_posix()),
        "analysis_sha256": _sha(analysis_path),
        "case_count": CASE_COUNT,
        "repetitions": REPETITIONS,
        "target_receipt_count": len(run["target_receipts"]),
        "usable_grade_count": sum(bool(item.get("verdict_usable")) for item in run["grades"]),
        "v6_outcomes_already_observed": True,
    }
    return protocol, subset, v6_lineage


def prepare(root: Path = ROOT, output: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    destination = (output or root / DEFAULT_OUTPUT).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("The v7 result directory must be inside the project root.") from exc
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing to overwrite a non-empty v7 directory: {destination}")

    v6_protocol, subset, v6_lineage = _validate_v6(root)
    release_root = root / RELEASE
    source_manifest_path = release_root / "source-manifest.json"
    source_manifest = _read(source_manifest_path)
    if "mit" not in str(source_manifest.get("license", "")).casefold():
        raise ValueError("The pinned LongMemEval source manifest must declare its MIT license basis.")
    oracle_entry = next((item for item in source_manifest.get("files", [])
                         if item.get("file", "").endswith("/source/longmemeval_oracle.json")), None)
    if oracle_entry is None:
        raise ValueError("The pinned source manifest does not bind the Oracle file.")
    oracle_path = _safe(root, oracle_entry["file"])
    if _sha(oracle_path) != oracle_entry.get("sha256") or oracle_path.stat().st_size != oracle_entry.get("bytes"):
        raise ValueError("The pinned 500-record Oracle file differs from its source manifest.")
    oracle_records = _read(oracle_path)
    if not isinstance(oracle_records, list) or len(oracle_records) != 500:
        raise ValueError("The frozen LongMemEval Oracle source must contain exactly 500 records.")
    raw_by_id = {row.get("question_id"): row for row in oracle_records if isinstance(row, dict)}
    if len(raw_by_id) != 500:
        raise ValueError("The source Oracle records have missing or duplicate question IDs.")

    selected_ids: set[str] = set()
    seen_sessions: set[str] = set()
    strata: dict[str, int] = {}
    bound_cases = []
    for case in subset:
        qid = case.get("question_id")
        if not isinstance(qid, str) or qid in selected_ids or qid not in raw_by_id:
            raise ValueError("The copied v6 subset has a missing, duplicate, or unknown question ID.")
        source_record = raw_by_id[qid]
        if _canonical_sha(source_record) != _canonical_sha(case):
            raise ValueError(f"The v6 case {qid} differs from the pinned LongMemEval source.")
        category = "abstention" if qid.endswith("_abs") else source_record.get("question_type")
        sessions = sorted(set(source_record.get("haystack_session_ids", [])
                              + source_record.get("answer_session_ids", [])))
        if case.get("question_type") != source_record.get("question_type"):
            raise ValueError(f"The v6 category metadata is inconsistent for {qid}.")
        if not sessions or seen_sessions.intersection(sessions):
            raise ValueError("The copied v6 subset has empty or overlapping evidence-session IDs.")
        selected_ids.add(qid)
        seen_sessions.update(sessions)
        strata[category] = strata.get(category, 0) + 1
        bound_cases.append({
            "question_id": qid,
            "category": category,
            "record_sha256": _canonical_sha(source_record),
            "evidence_session_ids": sessions,
        })
    if len(selected_ids) != CASE_COUNT or strata != CATEGORY_COUNTS:
        raise ValueError("The exact v6 subset does not match the frozen 30-case seven-stratum allocation.")

    upstream_src = root / UPSTREAM
    upstream_source = _safe(root, str((upstream_src / "evaluate_qa.py").relative_to(root)))
    upstream_binding_path = _safe(root, str((upstream_src / "source-binding.json").relative_to(root)))
    upstream_license = _safe(root, str((upstream_src / "LICENSE").relative_to(root)))
    upstream_binding = _read(upstream_binding_path)
    if _sha(upstream_source) != upstream_binding.get("source_sha256"):
        raise ValueError("The pinned upstream prompt source differs from its source binding.")

    v6_directory = root / V6_DIR
    scorer_snapshot = v6_directory / "upstream"
    if not scorer_snapshot.is_dir():
        raise ValueError("The v6 frozen upstream scorer snapshot is missing.")
    if _sha(scorer_snapshot / "evaluate_qa.py") != _sha(upstream_source):
        raise ValueError("The v6 scorer snapshot does not match the pinned Oracle source revision.")

    runner_path = root / "scripts/run_phase4_c_four_arm_v7.py"
    analyzer_path = root / "scripts/analyze_phase4_c_four_arm_v7.py"
    preparer_path = root / "scripts/prepare_phase4_c_four_arm_v7.py"
    grading_path = root / "scripts/longmemeval_grading.py"
    required = (runner_path, analyzer_path, preparer_path, grading_path)
    if any(not path.is_file() for path in required):
        raise FileNotFoundError("The v7 freeze requires final runner, analyzer, preparer, and grader-helper files.")
    app_files = sorted((root / "backend/app").rglob("*.py"))
    app_source = {str(path.relative_to(root)): _sha(path)
                  for path in [*app_files, *required]}

    destination.mkdir(parents=True, exist_ok=True)
    v6_subset_path = v6_directory / "longmemeval-subset.json"
    subset_path = destination / "longmemeval-subset.json"
    shutil.copyfile(v6_subset_path, subset_path)
    subset_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    upstream_out = destination / "upstream"
    upstream_out.mkdir()
    for src in (upstream_source, upstream_binding_path, upstream_license):
        out = upstream_out / src.name
        shutil.copyfile(src, out)
        out.chmod(stat.S_IRUSR | stat.S_IWUSR)

    subset_sha = _sha(subset_path)
    manifest_path = release_root / "prepared-release.json"
    execution_path = release_root / "execution-manifest.json"
    oracle_manifest_entry = next(item for item in source_manifest["files"]
                                 if item.get("file") == str(oracle_path.relative_to(root)))
    expected_per_arm = CASE_COUNT * REPETITIONS
    planned_requests = expected_per_arm * len(STRATEGIES)
    protocol = {
        "format": "proposal-c-four-arm-same-history-followup-v1",
        "id": V7_ID,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "frozen_before_v7_execution; exploratory_same_v6_histories",
        "study_scope": {
            "label": "Exploratory four-strategy replay on the existing v6 histories",
            "case_independence_claim": False,
            "prior_v6_outcomes_exposed": True,
            "does_not_add_new_histories": True,
            "does_not_replace_or_modify_v6": True,
        },
        "source": {
            "dataset": "LongMemEval cleaned Oracle",
            "license": source_manifest["license"],
            "revision": oracle_manifest_entry.get("commit"),
            "source_manifest": str(source_manifest_path.relative_to(root)),
            "source_manifest_sha256": _sha(source_manifest_path),
            "oracle_source": str(oracle_path.relative_to(root)),
            "oracle_source_sha256": _sha(oracle_path),
            "oracle_record_count": 500,
        },
        "selection": {
            "split": "same-v6-30-case-exploratory-four-arm-replay",
            "case_count": CASE_COUNT,
            "batch_size": BATCH_SIZE,
            "strata": dict(sorted(strata.items())),
            "selection_rule": "Exact byte-for-byte reuse of the frozen v6 30-case subset; no new sample was drawn and no cases were substituted.",
            "selected_cases": bound_cases,
            "selected_question_ids_sha256": _sha_bytes("\n".join(sorted(selected_ids)).encode("utf-8")),
            "selected_evidence_session_count": len(seen_sessions),
            "source_manifest": str(manifest_path.relative_to(root)),
            "source_manifest_sha256": _sha(manifest_path),
            "execution_manifest": str(execution_path.relative_to(root)),
            "execution_manifest_sha256": _sha(execution_path),
            "subset_sha256": subset_sha,
            "v6_lineage": v6_lineage,
        },
        "target": {
            "provider": "openrouter",
            "model": MODEL,
            "provider_options": {"require_parameters": True, "allow_fallbacks": False},
            "temperature": 0,
            "random_seed": 42,
            "reader_configuration": "strong",
            "memory_strategies": STRATEGIES,
            "repetitions_per_strategy": REPETITIONS,
            "run_order_by_repetition": ORDER_BY_REPETITION,
            "target_memory_capacity": 50,
            "target_memory_profile": v6_protocol["target"]["target_memory_profile"],
            "planned_target_requests": planned_requests,
        },
        "scorer": {
            "provider": "openrouter",
            "model": MODEL,
            "prompt_source": "Pinned LongMemEval get_anscheck_prompt from the bound upstream revision.",
            "transport": "OpenRouter chat completions, default provider routing, temperature 0, reasoning_effort none, max_tokens 128, at most three normal attempts.",
            "planned_scorer_requests": planned_requests,
            "deviation": "GPT-6 Luna is both target and grader, so grades are model-assisted compatibility evidence and not independent human labels or the official LongMemEval metric.",
        },
        "analysis": {
            "unit": "30 shared histories, with 3 repeated calls per strategy and history; repetitions are correlated",
            "primary_outcome": "Pinned-upstream GPT-6 Luna yes/no strict pass rate per strategy over the exact 30 v6 histories, paired by question ID within each repetition.",
            "selection_rule": "Recommend one strategy only when the collection is complete, that strategy has the unique highest pooled strict pass rate, and it beats each of the other three strategies in at least 2 of 3 repetition-level comparisons; otherwise report no clear winner.",
            "pairwise_reporting": "Report all six pairwise comparisons with denominators and unresolved pairs; no significance or generalisation claims.",
            "do_not_treat_repetitions_as_independent_histories": True,
            "do_not_add_v6_answers_as_new_v7_histories": True,
        },
        "execution": {
            "batch_size": BATCH_SIZE,
            "batch_count": 2,
            "batch_case_counts": [15, 15],
            "preserve_partial_results": True,
            "openrouter_minimum_start_to_start_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "initial_cooldown_seconds": RATE_LIMIT_COOLDOWN_SECONDS,
            "pacing_scope": "every OpenRouter chat-completions POST from both the target connector and grader in this local v7 runner process",
            "counterbalanced_strategy_order": ORDER_BY_REPETITION,
        },
        "budget": {
            "max_estimated_cost_usd": MAX_COST_USD,
            "projected_cost_usd": 0.36,
            "projection_basis": "Approximate two times the observed v6 total cost estimate of USD 0.1783034; retries, usage variability, and provider billing can differ. The runner reserves conservatively and stops before any request whose reserved estimate would exceed the USD 0.40 ceiling.",
            "planned_target_requests": planned_requests,
            "planned_scorer_requests": planned_requests,
            "planned_provider_requests_total": planned_requests * 2,
            "rate_assumptions_usd_per_token": {
                "target_input": 1e-7,
                "target_output": 5e-7,
                "grader_input": 2.5e-6,
                "grader_output": 1e-5,
            },
            "stop_and_preserve_partial_evidence_at_ceiling": True,
        },
        "human_review": {
            "status": "pending; automatic model grades do not count as human labels",
            "independent_reviewers_required": 2,
        },
        "limitations": [
            "This is an exploratory four-strategy replay on the already-exposed v6 30 histories; it adds no independent histories.",
            "The 360 target answers and 360 grader calls are repeated measurements over 30 cases, not 720 independent samples.",
            "The controlled-memory adapter is not the official LongMemEval execution stack or complete 500-case benchmark.",
            "GPT-6 Luna grades its own target model outputs; independent human labels and grader calibration remain pending.",
            "OpenRouter provider routing and model sampling may vary; the 4-second dispatch pacing addresses the reported 20 RPM limit but does not ensure deterministic output.",
            "The existing v6 protocol, subset, and result remain unchanged and are linked by hashes.",
        ],
        "app_source": app_source,
        "runner_sha256": _sha(runner_path),
        "analyzer_sha256": _sha(analyzer_path),
        "preparer_sha256": _sha(preparer_path),
        "grader_helper_sha256": _sha(grading_path),
        "source_files": {"benchmark_subset_sha256": subset_sha},
        "upstream_scorer_binding": upstream_binding,
        "upstream_scorer_source_sha256": _sha(upstream_source),
        "upstream_scorer_license_sha256": _sha(upstream_license),
    }
    _write_json(destination / "protocol.json", protocol)
    digest = _sha(destination / "protocol.json")
    sidecar = destination / "protocol.sha256"
    sidecar.write_text(digest + "  protocol.json\n", encoding="ascii")
    sidecar.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        "output": str(destination),
        "protocol_id": V7_ID,
        "protocol_sha256": digest,
        "subset_sha256": subset_sha,
        "case_count": CASE_COUNT,
        "strategies": STRATEGIES,
        "repetitions_per_strategy": REPETITIONS,
        "planned_target_requests": planned_requests,
        "planned_grader_requests": planned_requests,
        "planned_provider_requests_total": planned_requests * 2,
        "max_estimated_cost_usd": MAX_COST_USD,
        "model_calls_made": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = prepare(args.root, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
