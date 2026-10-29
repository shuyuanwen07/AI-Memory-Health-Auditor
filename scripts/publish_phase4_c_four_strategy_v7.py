"""Validate the frozen v7 evidence and publish aggregate dashboard data only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import analyze_phase4_c_four_arm_v7 as analyzer
from analyze_phase4_c_four_arm_v7 import validate_and_analyze
from analyze_phase4_c_four_arm_v7_unverified_pacing import OUTPUT_FORMAT as UNVERIFIED_RESULT_FORMAT
from analyze_phase4_c_four_arm_v7_unverified_pacing import __file__ as UNVERIFIED_WRAPPER_PATH
from phase4_c_four_arm_v7_pacing_addendum import sha256_file, verify_addendum
from run_phase4_c_four_arm_v7 import EXPECTED_STRATEGIES, validate_frozen_inputs

LABELS = {
    "weak_first_hit": "First-match retrieval",
    "strong_rule_based": "Relationship-priority retrieval",
    "scope_aware": "Match the task and project",
    "temporal_importance": "Consider time and importance",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rate(correct: int, usable: int) -> float | None:
    return round(100 * correct / usable, 4) if usable else None


def _read_json_file(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"The validated result {label} is missing or unsafe.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"The validated result {label} is not readable JSON.") from exc


def _load_addendum_analysis(inputs: dict[str, Any], run: dict[str, Any], run_path: Path,
                            result_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    manifest_path = result_dir / "validation-manifest.json"
    manifest = _read_json_file(manifest_path, "manifest")
    if manifest.get("format") != UNVERIFIED_RESULT_FORMAT:
        raise ValueError("Unsupported post-run validation manifest.")
    source_hashes = {"run": sha256(run_path), "protocol": inputs["protocol_sha256"],
                     "subset": inputs["subset_sha256"]}
    if (manifest.get("source_sha256") != source_hashes
            or manifest.get("pinned_analyzer_other_checks_reused") is not True
            or manifest.get("pacing_verified") is not False
            or manifest.get("decision_eligible") is not False
            or manifest.get("winner_recommendation_allowed") is not False):
        raise ValueError("Post-run result manifest does not bind to current frozen inputs or safe decision limits.")
    expected_analyzer = inputs["protocol"].get("analyzer_sha256")
    actual_analyzer = sha256(Path(analyzer.__file__))
    if expected_analyzer != actual_analyzer or manifest.get("pinned_analyzer_sha256") != actual_analyzer:
        raise ValueError("The pinned analyzer differs from the post-run validated result.")
    wrapper_sha = sha256(Path(UNVERIFIED_WRAPPER_PATH))
    if manifest.get("wrapper_sha256") != wrapper_sha:
        raise ValueError("The post-run analysis wrapper changed after validation.")

    analysis_name, summary_name = manifest.get("analysis_file"), manifest.get("summary_file")
    if analysis_name != "analysis.json" or summary_name != "four-arm-summary.json":
        raise ValueError("Post-run result manifest names unexpected result files.")
    analysis_path, summary_path = result_dir / analysis_name, result_dir / summary_name
    if analysis_path.is_symlink() or summary_path.is_symlink():
        raise ValueError("Post-run analysis and summary files must not be symlinks.")
    if sha256(analysis_path) != manifest.get("analysis_sha256") or sha256(summary_path) != manifest.get("summary_sha256"):
        raise ValueError("Post-run analysis or summary hash differs from its validation manifest.")
    analysis, summary = _read_json_file(analysis_path, "analysis"), _read_json_file(summary_path, "summary")
    addendum_relative = manifest.get("addendum_path")
    if not isinstance(addendum_relative, str) or not addendum_relative:
        raise ValueError("Post-run manifest lacks the relative pacing addendum path.")
    addendum_candidate = result_dir / addendum_relative
    if addendum_candidate.is_symlink():
        raise ValueError("The source pacing addendum must not be a symlink.")
    addendum_path = addendum_candidate.resolve()
    if not addendum_path.is_file():
        raise ValueError("The source pacing addendum is missing or unsafe.")
    addendum_sha = sha256(addendum_path)
    if addendum_sha != manifest.get("pacing_addendum_sha256"):
        raise ValueError("Pacing addendum hash differs from the post-run validation manifest.")
    addendum = _read_json_file(addendum_path, "pacing addendum")
    observations = verify_addendum(addendum, run, inputs["protocol"], source_hashes)
    exception = analysis.get("pacing_exception")
    if (analysis.get("source_run_sha256") != source_hashes["run"]
            or analysis.get("protocol_sha256") != source_hashes["protocol"]
            or analysis.get("subset_sha256") != source_hashes["subset"]
            or not isinstance(exception, dict)
            or exception.get("pacing_addendum_sha256") != addendum_sha
            or exception.get("raw_timestamp_record_sha256") != observations["raw_timestamp_record_sha256"]
            or exception.get("pacing_verified") is not False
            or exception.get("winner_recommendation_allowed") is not False):
        raise ValueError("Post-run analysis is not bound to this raw run, subset, and unverified pacing addendum.")
    decision = analysis.get("decision", {})
    collection_complete = bool(decision.get("collection_complete"))
    if (decision.get("decision_eligible") is not False
            or decision.get("recommended_strategy") != "no_clear_winner"
            or decision.get("rule_passed") is not False
            or analysis.get("coverage", {}).get("complete_for_winner_rule") is not False
            or analysis.get("request_pacing", {}).get("verified") is not False
            or summary.get("complete_for_decision") is not False
            or summary.get("recommendation") != "no_clear_winner"
            or summary.get("collection_complete") is not collection_complete
            or manifest.get("collection_complete") is not collection_complete):
        raise ValueError("Post-run report must preserve collection completeness but suppress winner decisions.")
    if summary.get("analysis_sha256") != manifest.get("analysis_sha256"):
        raise ValueError("Post-run summary does not bind to the analysis file.")
    return analysis, summary, addendum, addendum_sha


def publish(root: Path, directory: Path, output: Path,
            validated_result_dir: Path | None = None) -> dict[str, Any]:
    inputs = validate_frozen_inputs(root, directory)
    run_path = inputs["directory"] / "C-live.json"
    before = sha256(run_path)
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if validated_result_dir is None:
        analysis, _ = validate_and_analyze(inputs, run)
        addendum = None
        addendum_sha = None
    else:
        analysis, _, addendum, addendum_sha = _load_addendum_analysis(inputs, run, run_path, validated_result_dir)
    if sha256(run_path) != before:
        raise RuntimeError("The collection changed during analysis; retry only after it stops.")
    coverage = analysis["coverage"]
    strategies = []
    for name in EXPECTED_STRATEGIES:
        row = analysis["scores"]["per_strategy"][name]
        repetitions = [{"repetition": r["repetition"], "correct": r["correct"], "total": r["usable"],
                        "accuracy_percent": rate(r["correct"], r["usable"])} for r in row["repetitions"]]
        categories = [{"category": category, "correct": value["correct"], "total": value["usable"],
                       "accuracy_percent": rate(value["correct"], value["usable"])}
                      for category, value in row["category_results"].items()]
        strategies.append({"id": name, "label": LABELS[name], "correct": row["correct"],
                           "total": row["usable"], "accuracy_percent": rate(row["correct"], row["usable"]),
                           "per_repetition": repetitions, "categories": categories})
    paired = []
    for left, right in combinations(EXPECTED_STRATEGIES, 2):
        reps = [r for r in analysis["scores"]["all_pairwise_per_repetition"]
                if r["left_strategy"] == left and r["right_strategy"] == right]
        if len(reps) != 3:
            raise ValueError("The analyzer did not produce all three repetition pairs.")
        both = sum(r["both_correct"] for r in reps)
        left_only = sum(r["left_only_correct"] for r in reps)
        right_only = sum(r["right_only_correct"] for r in reps)
        neither = sum(r["neither_correct"] for r in reps)
        total = both + left_only + right_only + neither
        a, b = rate(left_only + both, total), rate(right_only + both, total)
        paired.append({"left": left, "right": right, "left_only": left_only, "right_only": right_only,
                       "both": both, "neither": neither, "total": total,
                       "left_accuracy_percent": a, "right_accuracy_percent": b,
                       "difference_pp": round(a - b, 4) if a is not None and b is not None else None})
    collection_complete = bool(analysis["decision"]["collection_complete"])
    complete = bool(analysis["decision"].get("decision_eligible", collection_complete))
    pacing_status = analysis["request_pacing"].get("status", "verified")
    report = {
        "format": "phase4-c-four-strategy-v7", "study_id": "phase4-c-four-strategy-v7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol_id": analysis["protocol_id"], "protocol_sha256": analysis["protocol_sha256"],
        "run_sha256": before, "source_revision": inputs["protocol"]["source"]["revision"],
        "collection_status": analysis["collection_status"], "collection_complete": collection_complete,
        "complete_for_decision": complete, "pacing_status": pacing_status,
        "case_count": analysis["selected_case_count"], "repetitions": 3,
        "total_target_answers": coverage["target_answers_saved"],
        "total_usable_grades": coverage["usable_grader_decisions"],
        "estimated_cost_usd": analysis["cost"]["estimated_usd"],
        "usage_based_cost_estimate_usd": analysis["cost"]["usage_based_estimate_usd"],
        "request_dispatches": analysis["request_pacing"]["dispatch_count"],
        "recommended_strategy": analysis["decision"]["recommended_strategy"] if complete else "no_clear_winner",
        "decision_rule": inputs["protocol"]["analysis"]["selection_rule"],
        "strategies": strategies, "pairwise": paired, "limitations": analysis["limitations"],
    }
    if addendum is not None:
        report["pacing_addendum_sha256"] = addendum_sha
        report["limitations"] = list(report["limitations"]) + [
            "The pacing addendum preserves the raw UTC timestamps; no monotonic trace was saved, so pacing compliance and the cause of the discrepancy remain unverified. No strategy winner is declared."]
    output.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=".four-strategy-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return {"output": str(output), "sha256": sha256(output), "complete": complete,
            "target_answers": coverage["target_answers_saved"], "usable_grades": coverage["usable_grader_decisions"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validated-result-dir", type=Path,
                        help="Optional output of analyze_phase4_c_four_arm_v7_unverified_pacing.py; consumes it without re-running the strict analyzer.")
    args = parser.parse_args()
    print(json.dumps(publish(args.root, args.directory, args.output, args.validated_result_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
