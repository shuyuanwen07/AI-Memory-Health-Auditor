"""Freeze a new 30-case LongMemEval C expansion without making model calls.

Selection uses only category, question IDs, and official evidence-session IDs.
Full question/answer records are written only to the private subset file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE = Path("output/longmemeval-official-v1")
UPSTREAM = Path("experiments/longmemeval-expanded-20261019/upstream-evaluator")
PRIOR_V5 = Path("artifacts/local/phase4-c-openrouter-20261027-v5")
DEFAULT_OUTPUT = Path("artifacts/local/phase4-c-openrouter-20261028-v6")
PROTOCOL_ID = "phase4-c-openrouter-gpt6-luna-expansion-20261028-v6"
MODEL = "openai/gpt-6-luna"
STRATEGIES = ["weak_first_hit", "strong_rule_based"]
SELECTION_SEED = "mha-lmeval-expand-v1"
CATEGORY_TARGETS = {
    "abstention": 4,
    "knowledge-update": 4,
    "multi-session": 5,
    "single-session-assistant": 4,
    "single-session-preference": 4,
    "single-session-user": 4,
    "temporal-reasoning": 5,
}
CATEGORIES = set(CATEGORY_TARGETS)
REPETITIONS = 3
BATCH_SIZE = 15
MAX_ESTIMATED_COST_USD = 1.00


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _write_json(path: Path, data: Any, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    if mode is not None:
        path.chmod(mode)


def _canonical_record_sha256(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return _sha_bytes(encoded)


def _category(record: dict[str, Any]) -> str:
    question_id = record.get("question_id")
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("Every Oracle record must have a non-empty question_id.")
    category = ("abstention" if question_id.endswith("_abs")
                else record.get("question_type"))
    if category not in CATEGORIES:
        raise ValueError("An Oracle record has a category outside the frozen seven strata.")
    return category


def _evidence_sessions(record: dict[str, Any]) -> set[str]:
    sessions: set[str] = set()
    for key in ("haystack_session_ids", "answer_session_ids"):
        value = record.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"Oracle record {key} must be a list of non-empty session IDs.")
        sessions.update(value)
    if not sessions:
        raise ValueError("Every selected record must identify at least one evidence session.")
    return sessions


def _load_pinned_source(root: Path) -> tuple[dict[str, Any], Path, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    manifest_path = root / RELEASE / "source-manifest.json"
    manifest = _read_json(manifest_path)
    if "MIT" not in str(manifest.get("license", "")):
        raise ValueError("The pinned dataset manifest does not record its MIT license.")
    entry = next((item for item in manifest.get("files", [])
                  if item.get("file", "").endswith("/source/longmemeval_oracle.json")), None)
    if entry is None:
        raise ValueError("The source manifest does not bind the LongMemEval Oracle file.")
    oracle_path = root / entry["file"]
    if (not oracle_path.is_file() or oracle_path.stat().st_size != entry.get("bytes")
            or _sha(oracle_path) != entry.get("sha256")):
        raise ValueError("The pinned Oracle source does not match its byte count and SHA-256.")
    records = _read_json(oracle_path)
    if not isinstance(records, list) or len(records) != 500:
        raise ValueError("The frozen source must contain exactly 500 Oracle records.")
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Every source record must be a JSON object.")
        question_id = record.get("question_id")
        if not isinstance(question_id, str) or not question_id or question_id in by_id:
            raise ValueError("The Oracle source has a missing or duplicate question_id.")
        _category(record)
        by_id[question_id] = record
    return manifest, oracle_path, records, by_id


def _load_prior_release(root: Path, source_by_id: dict[str, dict[str, Any]]) -> tuple[
        dict[str, Any], set[str], set[str], dict[str, Any]]:
    prepared_path = root / RELEASE / "prepared-release.json"
    execution_path = root / RELEASE / "execution-manifest.json"
    prepared = _read_json(prepared_path)
    if "no answer or target output used" not in str(prepared.get("selection", "")).casefold():
        raise ValueError("The prior release does not document outcome-independent selection.")
    rows = prepared.get("records")
    if not isinstance(rows, list) or len(rows) != 28:
        raise ValueError("The existing release must contain 28 frozen development/held-out records.")
    row_ids: set[str] = set()
    reserved_sessions: set[str] = set()
    session_owners: dict[str, str] = {}
    by_split_category: Counter[tuple[str, str]] = Counter()
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("Every prepared-release entry must be an object.")
        split = item.get("split")
        if split not in {"development", "candidate-held-out"}:
            raise ValueError("Prepared release contains an unexpected split.")
        question_id = item.get("question_id")
        if not isinstance(question_id, str) or question_id not in source_by_id or question_id in row_ids:
            raise ValueError("Prepared release has a missing, unknown, or duplicate question ID.")
        record = source_by_id[question_id]
        category = _category(record)
        if item.get("category") != category:
            raise ValueError("Prepared-release category differs from the pinned source record.")
        sessions = _evidence_sessions(record)
        if set(item.get("evidence_session_ids", [])) != sessions:
            raise ValueError("Prepared-release evidence-session binding differs from the source record.")
        if reserved_sessions.intersection(sessions):
            raise ValueError("The existing 28-case release already reuses evidence-session IDs.")
        files = [file for file in item.get("files", []) if file.get("mode") == "oracle"]
        if len(files) != 1:
            raise ValueError("Each prepared case must bind exactly one Oracle file.")
        receipt = files[0]
        record_path = root / receipt["file"]
        if (not record_path.is_file() or record_path.stat().st_size != receipt.get("bytes")
                or _sha(record_path) != receipt.get("sha256")):
            raise ValueError("A prepared Oracle file does not match its stored receipt.")
        stored = _read_json(record_path)
        if isinstance(stored, list) and len(stored) == 1:
            stored = stored[0]
        if stored != record:
            raise ValueError("A prepared Oracle record differs from its pinned source record.")
        row_ids.add(question_id)
        reserved_sessions.update(sessions)
        for session_id in sessions:
            session_owners[session_id] = question_id
        by_split_category[(split, category)] += 1
    if set(by_split_category) != {(split, category)
                                  for split in ("development", "candidate-held-out")
                                  for category in CATEGORIES}:
        raise ValueError("The existing release does not cover all seven strata in both splits.")
    if any(by_split_category[(split, category)] != 2
           for split in ("development", "candidate-held-out") for category in CATEGORIES):
        raise ValueError("The existing release is not balanced at two cases per stratum and split.")

    execution = _read_json(execution_path)
    if not isinstance(execution, dict):
        raise ValueError("The existing execution manifest is malformed.")
    prior_dir = root / PRIOR_V5
    prior_protocol_path = prior_dir / "protocol.json"
    prior_subset_path = prior_dir / "longmemeval-subset.json"
    prior_run_path = prior_dir / "C-live.json"
    prior_analysis_path = prior_dir / "analysis.json"
    for path in (prior_protocol_path, prior_subset_path, prior_run_path, prior_analysis_path):
        if not path.is_file():
            raise ValueError("The preserved v5 protocol, subset, run, and analysis must all exist.")
    prior_protocol = _read_json(prior_protocol_path)
    prior_subset = _read_json(prior_subset_path)
    prior_analysis = _read_json(prior_analysis_path)
    prior_run_sha = _sha(prior_run_path)
    prior_ids = {record.get("question_id") for record in prior_subset if isinstance(record, dict)}
    candidate_ids = {item["question_id"] for item in rows if item["split"] == "candidate-held-out"}
    if (len(prior_ids) != 14 or prior_ids != candidate_ids
            or prior_protocol.get("selection", {}).get("case_count") != 14
            or prior_protocol.get("source_files", {}).get("benchmark_subset_sha256") != _sha(prior_subset_path)):
        raise ValueError("The preserved v5 subset is not the exact existing 14-case candidate set.")
    prior_analysis_run_sha = (prior_analysis.get("source", {})
                              if isinstance(prior_analysis, dict) else {}).get("run_sha256")
    if prior_analysis_run_sha != prior_run_sha:
        raise ValueError("The preserved v5 analysis does not bind the exact frozen C-live run hash.")
    return prepared, row_ids, reserved_sessions, {
        "prepared_release_path": str(prepared_path.relative_to(root)),
        "prepared_release_sha256": _sha(prepared_path),
        "execution_manifest_path": str(execution_path.relative_to(root)),
        "execution_manifest_sha256": _sha(execution_path),
        "prepared_record_count": len(rows),
        "prepared_split_counts": dict(sorted(Counter(item["split"] for item in rows).items())),
        "prepared_question_ids_sha256": _sha_bytes("\n".join(sorted(row_ids)).encode()),
        "prepared_evidence_session_count": len(reserved_sessions),
        "prior_v5_protocol_path": str(prior_protocol_path.relative_to(root)),
        "prior_v5_protocol_sha256": _sha(prior_protocol_path),
        "prior_v5_subset_path": str(prior_subset_path.relative_to(root)),
        "prior_v5_subset_sha256": _sha(prior_subset_path),
        "prior_v5_run_path": str(prior_run_path.relative_to(root)),
        "prior_v5_run_sha256": prior_run_sha,
        "prior_v5_analysis_path": str(prior_analysis_path.relative_to(root)),
        "prior_v5_analysis_sha256": _sha(prior_analysis_path),
        "prior_v5_analysis_source_run_sha256": prior_analysis_run_sha,
        "prior_v5_case_count": len(prior_ids),
        "prior_v5_protocol_status": prior_protocol.get("status"),
        "execution_manifest_status": "preserved; new expansion uses a separate protocol and run directory",
    }


def select_records(source_records: list[dict[str, Any]], excluded_ids: set[str],
                   excluded_sessions: set[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return a stable 30-case selection using only non-answer metadata."""
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    used_sessions = set(excluded_sessions)
    eligible_ids = {record.get("question_id") for record in source_records} - excluded_ids
    if len(eligible_ids) != len(source_records) - len(excluded_ids):
        raise ValueError("Source IDs are not unique after applying the prior-release exclusion.")
    source_by_category: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_TARGETS}
    for record in source_records:
        if record["question_id"] not in excluded_ids:
            source_by_category[_category(record)].append(record)
    for category, target in CATEGORY_TARGETS.items():
        ordered = sorted(
            source_by_category[category],
            key=lambda record: (
                _sha_bytes(f"{SELECTION_SEED}|{category}|{record['question_id']}".encode("utf-8")),
                record["question_id"],
            ),
        )
        for record in ordered:
            if counts[category] >= target:
                break
            sessions = _evidence_sessions(record)
            if used_sessions.intersection(sessions):
                continue
            selected.append(record)
            counts[category] += 1
            used_sessions.update(sessions)
    if len(selected) != 30 or dict(counts) != CATEGORY_TARGETS:
        raise ValueError("The frozen 30-case allocation could not be satisfied without session overlap.")
    return selected, dict(counts)


def prepare(root: Path = ROOT, output: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    destination = (output or root / DEFAULT_OUTPUT).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing to overwrite a non-empty v6 directory: {destination}")

    source_manifest, oracle_path, source_records, source_by_id = _load_pinned_source(root)
    prepared, excluded_ids, excluded_sessions, previous = _load_prior_release(root, source_by_id)
    del prepared  # all bound paths and hashes are retained in the protocol below
    selected, counts = select_records(source_records, excluded_ids, excluded_sessions)
    selected_ids = {record["question_id"] for record in selected}
    selected_sessions: set[str] = set()
    selected_cases = []
    for record in selected:
        sessions = _evidence_sessions(record)
        if selected_sessions.intersection(sessions):
            raise ValueError("The expansion selection contains reused evidence sessions.")
        if sessions.intersection(excluded_sessions):
            raise ValueError("The expansion selection overlaps a prior prepared evidence session.")
        selected_sessions.update(sessions)
        selected_cases.append({
            "question_id": record["question_id"],
            "category": _category(record),
            "record_sha256": _canonical_record_sha256(record),
            "evidence_session_ids": sorted(sessions),
        })
    if len(selected_ids) != 30 or selected_ids.intersection(excluded_ids):
        raise ValueError("The new selection is not 30 unique cases disjoint from prior question IDs.")

    prepared_path = root / RELEASE / "prepared-release.json"
    execution_path = root / RELEASE / "execution-manifest.json"
    upstream_source = root / UPSTREAM / "evaluate_qa.py"
    upstream_binding_path = root / UPSTREAM / "source-binding.json"
    upstream_license = root / UPSTREAM / "LICENSE"
    binding = _read_json(upstream_binding_path)
    if not upstream_source.is_file() or _sha(upstream_source) != binding.get("source_sha256"):
        raise ValueError("Pinned upstream grader source does not match its source binding.")
    if not upstream_license.is_file():
        raise ValueError("Pinned upstream grader license file is missing.")

    runner_path = root / "scripts/run_phase4_c_expansion.py"
    analyzer_path = root / "scripts/analyze_phase4_c_expansion.py"
    grader_helper_path = root / "scripts/longmemeval_grading.py"
    preparer_path = root / "scripts/prepare_phase4_c_expansion.py"
    related_tests = sorted(path for path in (root / "scripts/tests").glob("test_*phase4_c_expansion*.py")
                            if path.is_file() and not path.is_symlink())
    required_sources = [runner_path, analyzer_path, grader_helper_path, preparer_path, *related_tests]
    if any(not path.is_file() for path in required_sources):
        missing = [str(path.relative_to(root)) for path in required_sources if not path.is_file()]
        raise FileNotFoundError("Freeze requires final runner/helper sources: " + ", ".join(missing))
    if not related_tests:
        raise FileNotFoundError("Freeze requires the focused v6 expansion tests to be present.")
    app_files = sorted((root / "backend/app").rglob("*.py"))
    app_source = {
        str(path.relative_to(root)): _sha(path)
        for path in [*app_files, runner_path, analyzer_path, grader_helper_path,
                     preparer_path, *related_tests]
    }

    destination.mkdir(parents=True, exist_ok=True)
    subset_path = destination / "longmemeval-subset.json"
    _write_json(subset_path, selected, mode=stat.S_IRUSR | stat.S_IWUSR)
    scorer_dir = destination / "upstream"
    scorer_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(upstream_source, scorer_dir / upstream_source.name)
    shutil.copyfile(upstream_binding_path, scorer_dir / upstream_binding_path.name)
    shutil.copyfile(upstream_license, scorer_dir / upstream_license.name)
    for path in scorer_dir.iterdir():
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    subset_sha = _sha(subset_path)
    planned_requests = len(selected) * len(STRATEGIES) * REPETITIONS
    oracle_meta = next(item for item in source_manifest["files"]
                       if item.get("file") == str(oracle_path.relative_to(root)))
    protocol = {
        "format": "proposal-c-independent-expansion-v1",
        "id": PROTOCOL_ID,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "frozen_before_v6_execution; human_reference_pending",
        "authorization": {
            "provider": "OpenRouter", "model": MODEL,
            "execution_budget": "Caller must enforce the frozen USD cost ceiling; no model calls are made by this preparer.",
        },
        "source": {
            "dataset": "LongMemEval cleaned Oracle",
            "license": source_manifest["license"],
            "revision": oracle_meta.get("commit"),
            "source_manifest": str((root / RELEASE / "source-manifest.json").relative_to(root)),
            "source_manifest_sha256": _sha(root / RELEASE / "source-manifest.json"),
            "oracle_source": str(oracle_path.relative_to(root)),
            "oracle_source_sha256": _sha(oracle_path),
            "oracle_record_count": len(source_records),
        },
        "selection": {
            "split": "candidate-held-out-expansion-v6",
            "release_manifest": str(prepared_path.relative_to(root)),
            "release_manifest_sha256": _sha(prepared_path),
            "execution_manifest": str(execution_path.relative_to(root)),
            "execution_manifest_sha256_at_freeze": _sha(execution_path),
            "case_count": len(selected),
            "batch_size": BATCH_SIZE,
            "strata": dict(sorted(counts.items())),
            "selection_seed": SELECTION_SEED,
            "selection_rule": (
                "Exclude every ID and evidence session from both prior prepared splits. "
                "Within each frozen stratum, order eligible records by SHA256(seed|category|question_id), "
                "then greedily select the requested count while excluding reused haystack/answer session IDs. "
                "No question, answer, target response, or score is used in selection."
            ),
            "selected_cases": selected_cases,
            "excluded_prior_release": previous,
            "selected_question_ids_sha256": _sha_bytes("\n".join(sorted(selected_ids)).encode("utf-8")),
            "selected_evidence_session_count": len(selected_sessions),
            "all_new_sessions_disjoint_from_prior_release": True,
        },
        "target": {
            "provider": "openrouter", "model": MODEL,
            "temperature": 0, "random_seed": 42,
            "memory_strategies": STRATEGIES,
            "repetitions_per_strategy": REPETITIONS,
            "target_memory_capacity": 50,
            "reader_configuration": "strong",
            "target_memory_profile": {
                "label": "C expansion shared reader",
                "max_retrieved_records": 50,
                "context_character_budget": 16000,
                "output_token_limit": 2048,
                "retain_assistant_history": True,
                "retrieve_message_context": False,
                "isolate_project_scope": False,
                "prefer_current_state": False,
            },
            "planned_target_requests": planned_requests,
        },
        "scorer": {
            "provider": "openrouter", "model": MODEL,
            "prompt_source": "Pinned LongMemEval get_anscheck_prompt from the bound upstream revision.",
            "transport": "OpenRouter chat completions; default provider routing; temperature 0; reasoning_effort none; max_tokens 128; bounded three attempts.",
            "parsing": "LongMemEval yes/no response convention; raw response and finish reason retained.",
            "deviation": "GPT-6 Luna is not LongMemEval's official metric model and is also the target model; grades are model-assisted compatibility evidence, not independent human labels.",
            "planned_scorer_requests": planned_requests,
        },
        "C": {"judge_model": MODEL},
        "analysis": {
            "unit": "case within repetition; histories/sessions are the independent sampling units",
            "primary_outcome": "Pinned-upstream GPT-6 Luna yes/no pass rate per strategy on the 30 new cases, paired by question ID within each of three repetitions.",
            "reported_values": "Per-strategy and per-repetition pass rates, paired Weak/Strong differences, paired win/loss/tie counts, and pooled case-level pass-rate difference with denominators.",
            "selection_rule": "Recommend Strong only if pooled v6 Strong accuracy exceeds Weak and Strong wins at least 2/3 repetition-level paired comparisons; otherwise report no clear winner.",
            "compare_only_within_each_repetition": True,
            "do_not_pool_repeated_calls_as_independent_histories": True,
            "cross_benchmark_score_subtraction": False,
            "threshold": None,
            "no_significance_or_generalisation_claim": True,
        },
        "budget": {
            "max_estimated_cost_usd": MAX_ESTIMATED_COST_USD,
            "planned_target_requests": planned_requests,
            "planned_scorer_requests": planned_requests,
            "estimated_provider_requests_total": planned_requests * 2,
            "stop_and_preserve_partial_evidence_at_ceiling": True,
        },
        "execution": {
            "batch_size": BATCH_SIZE,
            "batch_count": 2,
            "batch_case_counts": [15, 15],
            "preserve_partial_results": True,
        },
        "human_review": {
            "independent_reviewers_required": 2,
            "reviewers_must_not_see_model_scores_or_each_others_labels": True,
            "status": "pending; automated GPT-6 Luna grades are not human references",
        },
        "limitations": [
            "Thirty newly sampled cases extend the existing 14-case subset; they do not convert the collection into the complete 500-case official benchmark.",
            "Each repeated question shares its history across conditions and repetitions; repetitions are not independent histories.",
            "The target and grader use GPT-6 Luna; model grades are not independent semantic calibration.",
            "OpenRouter provider-default sampling may not be deterministic despite recorded temperature/seed settings.",
            "The existing v5 protocol, subset, and run remain unchanged and are referenced by hashes for comparison.",
            "Independent human review and licensing/source-use confirmation remain separate requirements.",
        ],
        "app_source": app_source,
        "source_files": {
            "benchmark_subset_sha256": subset_sha,
            "prepared_release_sha256": _sha(prepared_path),
            "prior_v5_subset_sha256": previous["prior_v5_subset_sha256"],
        },
        "runner_sha256": _sha(runner_path),
        "analyzer_sha256": _sha(analyzer_path),
        "grader_helper_sha256": _sha(grader_helper_path),
        "preparer_sha256": _sha(preparer_path),
        "frozen_subset_sha256": subset_sha,
        "upstream_scorer_binding": binding,
    }
    _write_json(destination / "protocol.json", protocol, mode=stat.S_IRUSR | stat.S_IWUSR)
    protocol_sha = _sha(destination / "protocol.json")
    (destination / "protocol.sha256").write_text(protocol_sha + "  protocol.json\n", encoding="ascii")
    (destination / "protocol.sha256").chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        "output": str(destination),
        "protocol_id": PROTOCOL_ID,
        "case_count": len(selected),
        "strata": dict(sorted(counts.items())),
        "planned_target_requests": planned_requests,
        "planned_scorer_requests": planned_requests,
        "max_estimated_cost_usd": MAX_ESTIMATED_COST_USD,
        "subset_sha256": subset_sha,
        "protocol_sha256": protocol_sha,
        "model_calls_made": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = prepare(args.root, args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
