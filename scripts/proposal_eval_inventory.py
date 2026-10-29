"""Inventory local proposal experiment evidence without modifying source records."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_PATHS = {
    "latest_a_run": "artifacts/local/phase4-20261027/A-live.json",
    "latest_b_run": "artifacts/local/phase4-20261027/B-live.json",
    "phase4_archived_c_run": "artifacts/local/phase4-20261027/C-live.json",
    "latest_c_run": "artifacts/local/phase4-c-openrouter-20261027-v5/C-live.json",
    "latest_phase4_review_metrics": "output/engineering-verification/PHASE_4_REVIEW_METRICS_2026-10-27.md",
    "phase4_review_recheck_analysis_2026_10_28": "output/proposal-evaluation/phase4-review-recheck-2026-10-28.json",
    "latest_phase12_receipts": "artifacts/local/phase12-20261027/final",
    "latest_phase4_followup_logs": "artifacts/local/phase4-followup-20261027",
    "owner_c_raw_results": "artifacts/local/owner-c-heldout-v1/results.json",
    "owner_a_development_summary": "handoff/owner-a/review_summary.json",
    "owner_a_validation": "handoff/owner-a/validation_report.json",
    "owner_b_results_report": "handoff/owner-b/TEST_RESULTS.md",
    "owner_c_metrics_report": "handoff/owner-c/step5_metrics.json",
    "longmemeval_pilot_protocol": "experiments/longmemeval-pilot-20261015/pilot-protocol.json",
    "longmemeval_pilot_summary": "experiments/longmemeval-pilot-20261015/trial-summary.json",
    "longmemeval_pilot_results": "experiments/longmemeval-pilot-20261015/pilot-report.json",
    "longmemeval_pilot_source_metadata": "experiments/longmemeval-pilot-20261015/provenance.json",
    "release20_final_status": "experiments/stability-study-20261023-dev20-evidence-disjoint/FINAL_STATUS.json",
    "presentation_demo_report": "experiments/presentation-demo-20261023/result/presentation-demo-report.json",
    "presentation_demo_summary": "experiments/presentation-demo-20261023/result/SUMMARY.json",
    "presentation_demo_csv": "experiments/presentation-demo-20261023/result/experiment.csv",
    "presentation_demo_verification": "experiments/presentation-demo-20261023/result/verification.json",
    "presentation_demo_frozen_suite": "experiments/presentation-demo-20261023/result/frozen-test-suite.json",
    "presentation_demo_reanalysis": "output/proposal-evaluation/saved-presentation-demo-b-reanalysis.json",
    "current_source_presentation_demo_readme": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/README.md",
    "current_source_presentation_demo_report": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/presentation-demo-report.json",
    "current_source_presentation_demo_manifest": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/manifest.json",
    "current_source_presentation_demo_bundle": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/experiment.bundle.json",
    "current_source_presentation_demo_csv": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/experiment.csv",
    "current_source_presentation_demo_verification": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/verification.json",
    "current_source_presentation_review_csv": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/human-review/blind-review.csv",
    "current_source_presentation_review_instructions": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/human-review/BLIND_REVIEW_INSTRUCTIONS.md",
    "current_source_presentation_review_key_private": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/human-review/review-key-private.json",
    "current_source_presentation_review_manifest": "output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/human-review/packet-manifest.json",
    "current_source_tutor_repair_readme": "output/proposal-delivery/live-current-source-repair-2026-10-28/README.md",
    "current_source_tutor_repair_manifest": "output/proposal-delivery/live-current-source-repair-2026-10-28/manifest.json",
    "current_source_tutor_repair_bundle": "output/proposal-delivery/live-current-source-repair-2026-10-28/experiment.bundle.json",
    "current_source_tutor_review_csv": "output/proposal-delivery/live-current-source-repair-2026-10-28/human-review/blind-review.csv",
    "current_source_tutor_review_instructions": "output/proposal-delivery/live-current-source-repair-2026-10-28/human-review/BLIND_REVIEW_INSTRUCTIONS.md",
    "current_source_tutor_review_key_private": "output/proposal-delivery/live-current-source-repair-2026-10-28/human-review/review-key-private.json",
    "current_source_tutor_review_manifest": "output/proposal-delivery/live-current-source-repair-2026-10-28/human-review/packet-manifest.json",
    "isolated_clean_start_report": "docs/proposal-delivery/CLEAN_START_VERIFICATION.md",
    "assessed_source_archive": "output/proposal-delivery/source/AI-Memory-Health-Auditor-source.zip",
    "assessed_source_manifest": "output/proposal-delivery/source/source-manifest.json",
    "phase3_frozen_evaluations": "datasets/phase3-engineering-v1/evaluations.json",
    "phase3_frozen_retrieval": "datasets/phase3-engineering-v1/retrieval.json",
    "phase4_candidate_histories": "datasets/phase4-candidate-v1/source-histories.json",
    "user_supplied_phase4_review_archive": "reviewer-1(1).zip",
    "user_supplied_phase4_review_material": "reviewer-1(1)/material.json",
    "user_supplied_phase4_review_return": "reviewer-1(1)/review-result.json",
    "assisted_human_return_audit": "output/proposal-evaluation/assisted-human-return-2026-10-28.json",
    "user_supplied_review2_return": "output/proposal-evaluation/incoming-review/review2-result.json",
    "user_supplied_review2_material": "artifacts/local/phase4-formal-review-20261027/reviewer-2/material.json",
    "user_supplied_chongtai_recheck40_archive": "output/proposal-evaluation/incoming-review/chongtai-jia-recheck-40.zip",
    "review_followup_intake_manifest": "output/proposal-evaluation/review-followup-intake.json",
    "longmemeval_official_source_manifest": "output/longmemeval-official-v1/source-manifest.json",
    "longmemeval_official_oracle_source": "output/longmemeval-official-v1/source/longmemeval_oracle.json",
    "longmemeval_official_prepared_release": "output/longmemeval-official-v1/prepared-release.json",
    "longmemeval_official_execution_manifest": "output/longmemeval-official-v1/execution-manifest.json",
    "longmemeval_oracle_pilot_evidence": "output/longmemeval-official-v1/oracle-evidence.json",
    "longmemeval_oracle_pilot_receipts": "output/longmemeval-official-v1/oracle-receipt-checks.json",
    "longmemeval_oracle_ai_prereview": "output/longmemeval-official-v1/oracle-ai-pre-review.json",
    "longmemeval_oracle_blind_review_template": "output/longmemeval-official-v1/oracle-blind-review-template.json",
    "longmemeval_oracle_blind_review_condition_key": "output/longmemeval-official-v1/oracle-blind-review-condition-key.json",
    "longmemeval_full_history_evidence": "output/longmemeval-official-v1/full-history-evidence.json",
    "longmemeval_full_history_receipts": "output/longmemeval-official-v1/full-history-receipt-checks.json",
    "candidate_c_protocol": "artifacts/local/phase4-c-openrouter-20261027-v2/protocol.json",
    "candidate_c_subset": "artifacts/local/phase4-c-openrouter-20261027-v2/longmemeval-subset.json",
    "candidate_c_upstream_binding": "artifacts/local/phase4-c-openrouter-20261027-v2/upstream/source-binding.json",
    "candidate_c_v2_partial_run": "artifacts/local/phase4-c-openrouter-20261027-v2/C-live.json",
    "candidate_c_v3_partial_run": "artifacts/local/phase4-c-openrouter-20261027-v3/C-live.json",
    "candidate_c_v4_partial_run": "artifacts/local/phase4-c-openrouter-20261027-v4/C-live.json",
    "candidate_c_v4_interruption_receipt": "artifacts/local/phase4-c-openrouter-20261027-v4/interruption-receipt.json",
    "candidate_c_v5_protocol": "artifacts/local/phase4-c-openrouter-20261027-v5/protocol.json",
    "candidate_c_v5_subset": "artifacts/local/phase4-c-openrouter-20261027-v5/longmemeval-subset.json",
    "candidate_c_v5_raw_run": "artifacts/local/phase4-c-openrouter-20261027-v5/C-live.json",
    "candidate_c_v5_analysis": "artifacts/local/phase4-c-openrouter-20261027-v5/analysis.json",
}

MAX_HASH_BYTES = 32 * 1024 * 1024


def _git_path_state(root: Path, relative: str) -> str:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative], cwd=root,
        check=False, capture_output=True, text=True,
    )
    if tracked.returncode == 0:
        return "tracked"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative], cwd=root,
        check=False, capture_output=True,
    )
    return "ignored" if ignored.returncode == 0 else "untracked_or_not_in_git"


def inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    records: list[dict[str, Any]] = []
    for key, relative in EXPECTED_PATHS.items():
        path = root / relative
        row: dict[str, Any] = {
            "key": key,
            "path": relative,
            "state": "missing",
            "git_state": "not_applicable",
        }
        if path.is_file():
            size = path.stat().st_size
            row.update(state="file", bytes=size, git_state=_git_path_state(root, relative))
            if size <= MAX_HASH_BYTES:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                row["sha256"] = digest
            else:
                row["sha256"] = None
                row["hash_skipped_reason"] = "file exceeds 32 MiB inventory hashing limit"
        elif path.is_dir():
            row.update(state="directory", git_state=_git_path_state(root, relative))
            row["file_count"] = sum(1 for child in path.rglob("*") if child.is_file())
        records.append(row)
    states = {row["key"]: row["state"] for row in records}
    return {
        "format": "proposal-experiment-evidence-inventory-v1",
        "repository_root": str(root),
        "source_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=False,
            capture_output=True, text=True,
        ).stdout.strip() or None,
        "records": records,
        "summary": {
            "latest_a_b_c_originals_present": all(
                states.get(key) == "file" for key in ("latest_a_run", "latest_b_run", "latest_c_run")
            ),
            "archived_phase4_abc_originals_present": all(
                states.get(key) == "file" for key in ("latest_a_run", "latest_b_run", "phase4_archived_c_run")
            ),
            "separate_candidate_c_v5_present": states.get("latest_c_run") == "file",
            "present_count": sum(row["state"] != "missing" for row in records),
            "expected_count": len(records),
        },
        "boundary": (
            "This inventory records local path presence and hashes small files. It does not certify "
            "human-label authenticity, consent, experimental validity, or completeness of a run."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inventory(args.root)
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
