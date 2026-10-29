"""Create a blinded source-review worksheet for one saved presentation demo.

The public CSV omits run IDs, conditions, model grades, and evaluation reasons.
The private key retains those mappings for the custodian. A reviewer who has
already seen the results must disclose exposure; a worksheet alone does not
make that review independent or blind.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import secrets
from pathlib import Path

from verify_presentation_demo import application_source_hash


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def prepare(report_path: Path, source_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty review directory: {output_dir}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("scope") != "presentation_synthetic_engineering_demo_not_research_gold":
        raise ValueError("Only the declared synthetic presentation demo is supported.")
    if report.get("status") not in {"completed", "completed_after_generation_recovery"}:
        raise ValueError("A complete saved six-run report is required.")
    runs = report.get("runs", [])
    if len(runs) != 6 or len({run.get("run_id") for run in runs}) != 6:
        raise ValueError("Expected six unique saved runs.")
    source_sha = application_source_hash(Path(__file__).resolve().parents[1] / "backend" / "app")
    recorded = {
        (((run.get("configuration") or {}).get("reproducibility") or {})
         .get("audit_runtime_signature") or {}).get("source_sha256")
        for run in runs
    }
    if recorded != {source_sha}:
        raise ValueError("Report source digest does not match the current application source.")

    conversation = json.loads((source_dir / "conversation.json").read_text(encoding="utf-8"))
    source_hashes = report.get("source_hashes") or {}
    for name in ("conversation", "curated-inventory", "settings"):
        path = source_dir / f"{name}.json"
        if source_hashes.get(path.name) != digest(path):
            raise ValueError(f"Synthetic demo source changed: {path.name}")
    messages = {message["message_id"]: message for message in conversation["messages"]}
    memories = {memory["memory_id"]: memory for memory in (report.get("confirmation") or {}).get("inventory", [])}

    rows = []
    private = []
    for run in runs:
        tests = {test["test_id"]: test for test in run.get("tests", [])}
        responses = run.get("responses", [])
        evaluations = {item["response_id"]: item for item in run.get("evaluations", [])}
        if len(tests) != 8 or len(responses) != 8 or len(evaluations) != 8:
            raise ValueError("Each run must have eight tests, responses, and evaluations.")
        for response in responses:
            test = tests.get(response["test_id"])
            evaluation = evaluations.get(response["response_id"])
            if not test or not evaluation or evaluation.get("test_id") != response["test_id"]:
                raise ValueError("Response, test, and evaluation IDs do not reconcile.")
            evidence = []
            memory_ids = test.get("supporting_memory_ids") or []
            if not memory_ids:
                raise ValueError("Every review item must include source-bound reference memories.")
            for memory_id in memory_ids:
                memory = memories.get(memory_id)
                if not memory:
                    raise ValueError(f"Missing confirmed source memory: {memory_id}")
                for message_id in memory.get("source_message_ids", []):
                    message = messages.get(message_id)
                    if not message:
                        raise ValueError(f"Missing source message: {message_id}")
                    evidence.append({
                        "message_id": message_id,
                        "role": message["role"],
                        "text": message["content"],
                    })
            evidence = list({item["message_id"]: item for item in evidence}.values())
            review_id = "R" + secrets.token_hex(6).upper()
            rows.append({
                "review_id": review_id,
                "dimension": test["dimension"],
                "question": test["prompt"],
                "expected_behavior": test["expected_behavior"],
                "source_evidence_json": canonical(evidence),
                "target_answer": response["response_text"],
                "review_verdict": "",
                "failure_type": "",
                "critical_error": "",
                "supporting_source_message_ids": "",
                "reviewer_notes": "",
            })
            private.append({
                "review_id": review_id,
                "experiment_id": report["experiment_id"],
                "run_id": run["run_id"],
                "condition": run["strategy"],
                "repetition": run["repetition"],
                "test_id": test["test_id"],
                "response_id": response["response_id"],
                "evaluation_id": evaluation["evaluation_id"],
                "automatic_label": (
                    "uncertain" if evaluation.get("passed") is None
                    else "pass" if evaluation.get("passed") is True else "fail"
                ),
                "automatic_failure_type": evaluation.get("failure_type"),
                "automatic_reason": evaluation.get("reason"),
            })

    if len(rows) != 48 or len({row["review_id"] for row in rows}) != 48:
        raise ValueError("Expected 48 uniquely blinded answer rows.")
    secrets.SystemRandom().shuffle(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    public_csv = output_dir / "blind-review.csv"
    with public_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    private_path = output_dir / "review-key-private.json"
    private_path.write_text(json.dumps({
        "format": "presentation-demo-review-key-v1",
        "experiment_id": report["experiment_id"],
        "report_sha256": digest(report_path),
        "application_source_sha256": source_sha,
        "rows": private,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_path.chmod(0o600)
    instructions = output_dir / "BLIND_REVIEW_INSTRUCTIONS.md"
    instructions.write_text(
        "# Source-based answer review\n\n"
        "Review each of the 48 saved target answers against only the displayed source messages and expected behaviour. "
        "Do not infer a label from wording style or use automated scores. Choose `pass`, `fail`, or `uncertain`; mark a "
        "critical error only when the answer could materially mislead or harm the user. For a failure, cite the source "
        "message ID(s) and state the error type. Leave blank when evidence is insufficient.\n\n"
        "The public worksheet intentionally omits run ID, condition, repetition, model identity, and automated judgment. "
        "Keep `review-key-private.json` with the custodian; never give it to the reviewer. Reviewers must disclose any "
        "prior exposure to these answers, scores, or aggregate results and whether AI assistance was used. Exposure or "
        "AI assistance means the return is useful for correction but cannot be reported as an independent blind reference. "
        "This is a synthetic engineering case, not participant data or formal held-out evidence.\n\n"
        "Return the completed CSV without renaming `review_id` values. The reviewer should not inspect the app or "
        "private key until their first-pass labels are complete.\n",
        encoding="utf-8",
    )
    manifest = {
        "format": "presentation-demo-review-packet-v1",
        "scope": "synthetic-engineering-review-preparation-not-human-labels",
        "experiment_id": report["experiment_id"],
        "source_report_sha256": digest(report_path),
        "application_source_sha256": source_sha,
        "frozen_suite_fingerprint": report["frozen_suite"]["fingerprint"],
        "row_count": len(rows),
        "reviewer_labels_created": 0,
        "files": {
            public_csv.name: digest(public_csv),
            private_path.name: digest(private_path),
            instructions.name: digest(instructions),
        },
        "privacy_note": "Synthetic data only; private key contains run-condition and automatic judgment bindings.",
    }
    manifest_path = output_dir / "packet-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.report, args.source, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
