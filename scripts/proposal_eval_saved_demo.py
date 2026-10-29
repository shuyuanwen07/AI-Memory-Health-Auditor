"""Recompute a limited Weak/Strong presentation run from its saved CSV export.

This validates the exported rows and produces descriptive app-run statistics.
It does not supply human labels, authenticate the original source, or turn the
single synthetic demo into formal Proposal Experiment B evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT_DIR = ROOT / "experiments/presentation-demo-20261023/result"
STRATEGIES = {
    "weak_first_hit": "Weak First Hit",
    "strong_rule_based": "Strong Rule Based",
}
DIMS = ("accuracy", "freshness", "conflict_resolution", "appropriate_use")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strategy(row: dict[str, str]) -> str:
    condition_id = row.get("condition_id", "")
    for key in STRATEGIES:
        if f"::{key}::" in condition_id:
            return key
    condition = row.get("condition", "")
    for key, label in STRATEGIES.items():
        if label.lower() in condition.lower():
            return key
    raise ValueError(f"Cannot identify saved strategy for {row.get('run_id', '')}.")


def analyse(result_dir: Path) -> dict[str, Any]:
    csv_path = result_dir / "experiment.csv"
    summary_path = result_dir / "SUMMARY.json"
    report_path = result_dir / "presentation-demo-report.json"
    verification_path = result_dir / "verification.json"
    for path in (csv_path, summary_path, report_path, verification_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if report.get("scope") != "presentation_synthetic_engineering_demo_not_research_gold":
        raise ValueError("The saved run is not the expected synthetic presentation demo.")
    if report.get("research_evidence") is not False:
        raise ValueError("The saved report no longer declares this run non-research evidence.")
    if verification.get("report_sha256") != sha256(report_path):
        raise ValueError("The verification receipt does not match the saved report bytes.")
    if verification.get("status") != "passed":
        raise ValueError("The saved presentation verification did not pass.")
    if summary.get("experiment_id") != report.get("experiment_id") or summary.get("total_answers") != 48 or summary.get("total_evaluations") != 48:
        raise ValueError("The saved summary does not reconcile to the original report and 48 answer/evaluation rows.")

    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(row.get("experiment_id") != report.get("experiment_id") for row in rows):
        raise ValueError("CSV rows do not consistently identify the saved experiment.")

    run_rows = [row for row in rows if row.get("record_type") == "run" and row.get("metric") == "status"]
    answer_rows = [row for row in rows if row.get("record_type") == "answer"]
    if len(run_rows) != 6 or len(answer_rows) != 48:
        raise ValueError(f"Expected six saved runs and 48 answers; got {len(run_rows)} and {len(answer_rows)}.")
    expected_counts = (verification.get("json_answer_count"), verification.get("csv_answer_count"),
                       verification.get("evaluation_count"))
    if expected_counts != (48, 48, 48):
        raise ValueError(f"Verification receipt has unexpected answer/evaluation counts: {expected_counts}.")
    if verification.get("source_semantic_correctness_proven") is not False:
        raise ValueError("Expected the saved verification to retain its semantic-validity limitation.")

    run_ids: set[str] = set()
    run_strategy: dict[str, str] = {}
    for row in run_rows:
        run_id = row.get("run_id", "")
        if not run_id or row.get("value") != "COMPLETED" or run_id in run_ids:
            raise ValueError("Saved run list is incomplete, duplicated, or not completed.")
        run_ids.add(run_id)
        run_strategy[run_id] = _strategy(row)
    per_strategy_runs = Counter(run_strategy.values())
    if per_strategy_runs != Counter({key: 3 for key in STRATEGIES}):
        raise ValueError(f"Expected three runs per policy; found {dict(per_strategy_runs)}.")

    seen_answers: set[tuple[str, str, str, str]] = set()
    suite_by_run: dict[str, list[tuple[str, str, str, tuple[str, ...]]]] = defaultdict(list)
    counts: dict[str, dict[str, Counter[str]]] = {
        strategy: {dimension: Counter() for dimension in DIMS} for strategy in STRATEGIES
    }
    for row in answer_rows:
        run_id = row.get("run_id", "")
        key = (run_id, row.get("test_id", ""), row.get("response_id", ""), row.get("evaluation_id", ""))
        if run_id not in run_ids or not all(key) or key in seen_answers:
            raise ValueError("Answer rows have missing/duplicate IDs or refer to an unknown run.")
        seen_answers.add(key)
        dimension = row.get("dimension", "")
        outcome = row.get("outcome", "").lower()
        if dimension not in DIMS or outcome not in {"pass", "fail", "uncertain"}:
            raise ValueError(f"Unexpected saved outcome or dimension: {dimension!r}/{outcome!r}.")
        try:
            memory_ids = json.loads(row.get("supporting_memory_ids", "[]") or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid evidence-memory list for {row['test_id']}.") from exc
        if not isinstance(memory_ids, list) or not all(isinstance(value, str) for value in memory_ids):
            raise ValueError(f"Invalid evidence-memory list for {row['test_id']}.")
        signature = (dimension, row.get("prompt", ""), row.get("expected_behavior", ""), tuple(sorted(memory_ids)))
        if not signature[1] or not signature[2]:
            raise ValueError(f"Missing prompt or expected behaviour for {row['test_id']}.")
        suite_by_run[run_id].append(signature)
        counts[run_strategy[run_id]][dimension][outcome] += 1
    canonical_suites = {
        run_id: sorted(signatures) for run_id, signatures in suite_by_run.items()
    }
    suite_fingerprints = {
        run_id: hashlib.sha256(json.dumps(signatures, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        for run_id, signatures in canonical_suites.items()
    }
    if set(suite_by_run) != run_ids or len(suite_by_run) != 6:
        raise ValueError("Saved answers do not cover all six run IDs.")
    if any(len(signatures) != 8 for signatures in canonical_suites.values()):
        raise ValueError("Expected eight distinct content-based questions in every run.")
    content_fingerprints = set(suite_fingerprints.values())
    test_id_sets = {
        tuple(sorted(row["test_id"] for row in answer_rows if row["run_id"] == run_id))
        for run_id in run_ids
    }

    condition_metrics: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("record_type") != "condition" or row.get("metric") not in {
            "overall_mean", "overall_standard_deviation", "answers_passed", "answers_decided",
            "pending_judgments", "completed_runs", "failed_runs",
        }:
            continue
        strategy = _strategy(row)
        condition_metrics.setdefault(strategy, {})[row["metric"]] = row.get("value", "")

    strategies_out: dict[str, Any] = {}
    for strategy, dimensions in counts.items():
        per_dimension: dict[str, Any] = {}
        for dimension, values in dimensions.items():
            decided = values["pass"] + values["fail"]
            per_dimension[dimension] = {
                "passed": values["pass"],
                "failed": values["fail"],
                "pending": values["uncertain"],
                "decided": decided,
                "score_percent": round(values["pass"] / decided * 100, 1) if decided else None,
            }
        source = condition_metrics.get(strategy, {})
        if int(source.get("completed_runs", -1)) != 3 or int(source.get("failed_runs", -1)) != 0:
            raise ValueError(f"App export condition metrics disagree with saved run rows for {strategy}.")
        strategies_out[strategy] = {
            "runs": per_strategy_runs[strategy],
            "app_reported_overall_mean_percent": float(source["overall_mean"]),
            "app_reported_overall_population_sd_percent": float(source["overall_standard_deviation"]),
            "answers_passed": int(source["answers_passed"]),
            "answers_decided": int(source["answers_decided"]),
            "pending_judgments": int(source["pending_judgments"]),
            "by_dimension": per_dimension,
        }

    if sum(v["answers_passed"] + v["pending_judgments"] + sum(x["failed"] for x in v["by_dimension"].values())
           for v in strategies_out.values()) != 48:
        raise ValueError("Recomputed outcomes do not reconcile to the 48 saved answers.")

    return {
        "format": "saved-presentation-demo-b-reanalysis-v1",
        "scope": "One synthetic presentation history; exploratory target-policy evidence only, not formal Experiment B.",
        "experiment_id": report["experiment_id"],
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "source_hashes_reported_by_original_run": report.get("source_hashes", {}),
        "evidence_files": {
            "experiment_csv_sha256": sha256(csv_path),
            "summary_sha256": sha256(summary_path),
            "original_report_sha256": sha256(report_path),
            "verification_receipt_sha256": sha256(verification_path),
            "frozen_suite_sha256": sha256(result_dir / "frozen-test-suite.json"),
        },
        "source_binding": "The saved report binds the synthetic source hashes and verification receipt; no final Git commit SHA was found on the database runs.",
        "target_model": summary.get("model"),
        "source_message_count": summary.get("message_count"),
        "known_source_gap_summary": "The original summary records a missing South deployment value in the first Strong response's target memories; the system's semantic correctness was not independently proven.",
        "application_source_fingerprint_in_verification": verification.get("current_application_source_sha256"),
        "model_sampling": "Temperature and seed are retained in run metadata; the run does not establish provider-enforced seed determinism.",
        "repetitions_per_strategy": 3,
        "questions_per_run": 8,
        "shared_suite_fingerprint": report.get("frozen_suite", {}).get("fingerprint"),
        "export_reconciled_question_content_fingerprint": next(iter(content_fingerprints)) if len(content_fingerprints) == 1 else None,
        "same_question_content_and_evidence_across_runs": len(content_fingerprints) == 1,
        "run_local_test_ids_are_recreated": len(test_id_sets) > 1,
        "runs": len(run_ids),
        "answers_and_evaluations": len(answer_rows),
        "strategies": strategies_out,
        "human_reference": "No new human annotation; semantic correctness and independent review are not established.",
        "preserved_generation_failure": report.get("preserved_historical_generation_failure"),
        "first_attempt_failures": report.get("first_attempt_failures", []),
        "limitations": [
            "One authored synthetic history and repeated runs do not support population-level generalisation.",
            "All scores are application-generated judgments; no independent human outcome labels are bound to this run.",
            "The saved verification confirms input/export correspondence, not semantic correctness of the source or scores.",
            "The final project Git revision was not recorded on the database runs, so this is historical, not current-release acceptance.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument("--output", type=Path, default=ROOT / "output/proposal-evaluation/saved-presentation-demo-b-reanalysis.json")
    args = parser.parse_args()
    result = analyse(args.result_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "experiment_id": result["experiment_id"],
                      "answers": result["answers_and_evaluations"],
                      "weak_mean": result["strategies"]["weak_first_hit"]["app_reported_overall_mean_percent"],
                      "strong_mean": result["strategies"]["strong_rule_based"]["app_reported_overall_mean_percent"]}, indent=2))


if __name__ == "__main__":
    main()
