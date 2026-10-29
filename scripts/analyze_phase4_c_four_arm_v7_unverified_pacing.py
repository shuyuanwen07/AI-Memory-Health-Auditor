"""Analyze v7 descriptively when saved UTC pacing cannot be verified.

The pinned analyzer is reused unchanged for all collection, source, scorer,
request, response, grade and cost checks. Only its pacing gate is replaced in
memory with a hash-bound addendum report; the resulting analysis cannot select
a winner and is written outside the frozen evidence directory.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

import analyze_phase4_c_four_arm_v7 as pinned_analyzer
from phase4_c_four_arm_v7_pacing_addendum import (
    PacingAddendumError,
    sha256_file,
    verify_addendum,
)
from run_phase4_c_four_arm_v7 import FrozenInputError, _read_json, validate_frozen_inputs

TIMING_FAILURES = {
    "Saved OpenRouter POST start times violate the frozen minimum spacing.",
    "The first OpenRouter POST did not observe the frozen initial cooldown.",
}
OUTPUT_FORMAT = "proposal-c-four-arm-v7-unverified-pacing-result-v1"
PACING_LIMITATION = (
    "The raw UTC pacing journal includes an interval below the frozen timing threshold. "
    "No monotonic timestamps were persisted, so actual request spacing and the cause of the UTC discrepancy "
    "cannot be independently determined. Scores are descriptive only; no winner recommendation is allowed."
)


def analyze_validated_run(inputs: dict[str, Any], run: dict[str, Any], addendum: dict[str, Any],
                          source_sha256: dict[str, str], addendum_sha256: str,
                          dependencies: dict[str, Any] | None = None
                          ) -> tuple[dict[str, Any], dict[str, Any]]:
    if run.get("status") == "running":
        raise PacingAddendumError("Refuse post-run analysis while the journal still says running.")
    observations = verify_addendum(addendum, run, inputs["protocol"], source_sha256)
    try:
        pinned_analyzer._verify_pacing_sessions(run, inputs["protocol"])
    except FrozenInputError as exc:
        if str(exc) not in TIMING_FAILURES or not observations["violations"]:
            raise PacingAddendumError("The frozen analyzer rejected a non-timing invariant; addendum cannot bypass it.") from exc
    else:
        raise PacingAddendumError("The strict analyzer verifies pacing; do not use the exception path.")

    pacing_report = {
        "sessions": observations["sessions"],
        "dispatch_count": observations["dispatch_count"],
        "minimum_interval_seconds": observations["required_minimum_start_interval_seconds"],
        "initial_cooldown_seconds": observations["required_initial_cooldown_seconds"],
        "verified": False,
        "status": "utc_timing_unverifiable",
        "cause_assessment": "unknown",
        "violations": observations["violations"],
        "raw_timestamp_record_sha256": observations["raw_timestamp_record_sha256"],
        "pacing_addendum_sha256": addendum_sha256,
    }
    original_pacing_validator = pinned_analyzer._verify_pacing_sessions
    try:
        # This narrowly replaces only the pinned analyzer's timing gate in this
        # process. No timestamp is edited or synthesized; every other frozen
        # validation and score computation remains the original implementation.
        pinned_analyzer._verify_pacing_sessions = lambda _run, _protocol: pacing_report
        analysis, summary = pinned_analyzer.validate_and_analyze(inputs, run, dependencies)
    finally:
        pinned_analyzer._verify_pacing_sessions = original_pacing_validator

    collection_complete = bool(analysis["decision"]["collection_complete"])
    analysis["source_run_sha256"] = source_sha256["run"]
    analysis["source_subset_sha256"] = source_sha256["subset"]
    analysis["request_pacing"] = pacing_report
    analysis["coverage"]["collection_complete"] = collection_complete
    analysis["coverage"]["complete_for_winner_rule"] = False
    analysis["decision"]["decision_eligible"] = False
    analysis["decision"]["complete_for_decision"] = False
    analysis["decision"]["recommended_strategy"] = "no_clear_winner"
    analysis["decision"]["rule_passed"] = False
    analysis["decision"]["recommendation_blocked_reason"] = "Recorded UTC pacing is unverified; winner selection is suppressed."
    analysis["pacing_exception"] = {
        "status": "utc_timing_unverifiable",
        "cause_assessment": "unknown",
        "pacing_addendum_sha256": addendum_sha256,
        "raw_timestamp_record_sha256": observations["raw_timestamp_record_sha256"],
        "pacing_verified": False,
        "winner_recommendation_allowed": False,
    }
    analysis["limitations"].append(PACING_LIMITATION)

    summary["source_run_sha256"] = source_sha256["run"]
    summary["source_subset_sha256"] = source_sha256["subset"]
    summary["collection_complete"] = collection_complete
    summary["complete_for_decision"] = False
    summary["recommendation"] = "no_clear_winner"
    summary["request_pacing"] = pacing_report
    summary["pacing_exception"] = analysis["pacing_exception"]
    summary["caveat"] = f"{summary.get('caveat', '').strip()} {PACING_LIMITATION}".strip()
    return analysis, summary


def _write_private(path: Path, data: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _source_hashes(inputs: dict[str, Any], run_path: Path) -> dict[str, str]:
    return {"run": sha256_file(run_path),
            "protocol": inputs["protocol_sha256"],
            "subset": inputs["subset_sha256"]}


def analyze_directory(root: Path, directory: Path, addendum_path: Path, output_dir: Path,
                      dependencies: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = validate_frozen_inputs(root, directory)
    directory = inputs["directory"]
    run_path = directory / "C-live.json"
    protocol_path = directory / "protocol.json"
    subset_path = directory / "longmemeval-subset.json"
    if not run_path.is_file() or run_path.is_symlink():
        raise PacingAddendumError("The v7 run journal is missing or unsafe.")
    run_before = sha256_file(run_path)
    source_hashes = _source_hashes(inputs, run_path)
    run = _read_json(run_path)
    addendum_path = addendum_path.resolve()
    if addendum_path.is_symlink() or not addendum_path.is_file():
        raise PacingAddendumError("The private pacing addendum is missing or unsafe.")
    addendum_sha = sha256_file(addendum_path)
    addendum = _read_json(addendum_path)
    analysis, summary = analyze_validated_run(inputs, run, addendum, source_hashes,
                                               addendum_sha, dependencies)
    source_after = {"run": sha256_file(run_path), "protocol": sha256_file(protocol_path),
                    "subset": sha256_file(subset_path)}
    if source_after != source_hashes or run_before != source_hashes["run"]:
        raise PacingAddendumError("Frozen evidence changed during analysis; no result bundle was written.")

    output_dir = output_dir if output_dir.is_absolute() else inputs["root"] / output_dir
    output_dir = output_dir.resolve()
    try:
        output_dir.relative_to(directory)
    except ValueError:
        pass
    else:
        raise PacingAddendumError("Analysis output must be outside the frozen run directory.")
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Refuse to overwrite an existing analysis directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_dir.parent.is_symlink():
        raise PacingAddendumError("Analysis output parent must not be a symlink.")
    output_dir.mkdir(mode=0o700)
    addendum_relative = os.path.relpath(addendum_path, output_dir)
    try:
        analysis["source_code_sha256"] = inputs["protocol"].get("app_source", {})
        analysis_path = output_dir / "analysis.json"
        summary_path = output_dir / "four-arm-summary.json"
        _write_private(analysis_path, analysis)
        analysis_sha = sha256_file(analysis_path)
        summary["analysis_sha256"] = analysis_sha
        _write_private(summary_path, summary)
        summary_sha = sha256_file(summary_path)
        manifest = {
            "format": OUTPUT_FORMAT,
            "source_sha256": source_hashes,
            "addendum_path": addendum_relative,
            "pacing_addendum_sha256": addendum_sha,
            "analysis_file": "analysis.json", "analysis_sha256": analysis_sha,
            "summary_file": "four-arm-summary.json", "summary_sha256": summary_sha,
            "pinned_analyzer_sha256": sha256_file(Path(__file__).resolve().parent / "analyze_phase4_c_four_arm_v7.py"),
            "wrapper_sha256": sha256_file(Path(__file__)),
            "addendum_tool_sha256": addendum.get("tool_sha256"),
            "pinned_analyzer_other_checks_reused": True,
            "pacing_verified": False,
            "decision_eligible": False,
            "collection_complete": bool(analysis["decision"]["collection_complete"]),
            "winner_recommendation_allowed": False,
        }
        _write_private(output_dir / "validation-manifest.json", manifest)
        return {"output_dir": str(output_dir), "analysis_sha256": analysis_sha,
                "summary_sha256": summary_sha, "pacing_addendum_sha256": addendum_sha,
                "collection_complete": manifest["collection_complete"],
                "complete_for_decision": False, "recommended_strategy": "no_clear_winner"}
    except BaseException:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--directory", type=Path, required=True, help="Frozen v7 evidence directory.")
    parser.add_argument("--addendum", type=Path, required=True, help="Private pacing addendum JSON.")
    parser.add_argument("--output-dir", type=Path, required=True, help="New output directory, separate from frozen evidence.")
    args = parser.parse_args()
    result = analyze_directory(args.root, args.directory, args.addendum, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
