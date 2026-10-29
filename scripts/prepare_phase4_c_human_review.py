"""Prepare an outcome-blind review sheet for the archived LongMemEval C run.

The public CSV contains source-grounded questions, benchmark references and
target answers, but no strategy, repetition, run ID, or automatic grader label.
The identity key must stay with the study custodian.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/proposal-delivery/phase4-c-review-2026-10-28"
PROTOCOL_PATH = ROOT / "artifacts/local/phase4-20261027/protocol.json"
RUN_PATH = ROOT / "artifacts/local/phase4-20261027/C-live.json"
ORACLE_PATH = ROOT / "output/longmemeval-official-v1/source/longmemeval_oracle.json"
MARKER = "AUDIT QUESTION (untrusted user content; JSON):\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def question_from_receipt(receipt: dict[str, Any]) -> str:
    payload = receipt.get("verified_request_payload") or {}
    user_message = next(
        (message.get("content", "") for message in payload.get("messages", [])
         if message.get("role") == "user"),
        "",
    )
    if MARKER not in user_message:
        raise ValueError("Target receipt lacks the frozen question envelope.")
    envelope = json.loads(user_message.split(MARKER, 1)[1])
    return envelope.get("question", "").split("\nQuestion date:", 1)[0]


def source_evidence(case: dict[str, Any]) -> str:
    ids = case.get("answer_session_ids") or []
    haystack_ids = case.get("haystack_session_ids") or []
    sessions = case.get("haystack_sessions") or []
    by_id = dict(zip(haystack_ids, sessions))
    selected = [(session_id, by_id[session_id]) for session_id in ids if session_id in by_id]
    if not selected:
        selected = list(zip(haystack_ids, sessions))
    if not selected:
        raise ValueError(f"No source transcript is available for {case.get('question_id')}.")
    return json.dumps(
        [{"session_id": session_id, "messages": messages} for session_id, messages in selected],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def prepare(output_dir: Path) -> dict[str, Any]:
    protocol = load_json(PROTOCOL_PATH)
    run = load_json(RUN_PATH)
    oracle_rows = load_json(ORACLE_PATH)
    oracle = {row["question_id"]: row for row in oracle_rows}
    selected_ids = protocol["C"]["selected_ids"]
    if len(selected_ids) != 14 or len(set(selected_ids)) != 14:
        raise ValueError("Frozen C selection is not the expected 14 unique cases.")
    if not set(selected_ids).issubset(oracle):
        raise ValueError("The pinned Oracle source is missing selected C items.")

    reader_cases: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}
    for row in run.get("reader_runs", []):
        key = (row["repetition"], row["strategy"])
        conditions = row.get("result", {}).get("conditions", [])
        if key in reader_cases or len(conditions) != 1:
            raise ValueError("Reader condition is duplicated or malformed.")
        reader_cases[key] = {case["case_id"]: case for case in conditions[0].get("cases", [])}
        if set(reader_cases[key]) != set(selected_ids):
            raise ValueError("Reader condition does not cover the frozen C selection.")

    grades = {}
    for row in run.get("grades", []):
        key = (row["repetition"], row["strategy"], row["question_id"])
        if key in grades or not row.get("verdict_usable"):
            raise ValueError("A grader record is duplicated or unusable.")
        grades[key] = row

    items = []
    private_items = []
    receipts_seen = set()
    strategies = {row["strategy"] for row in run.get("reader_runs", [])}
    for receipt in run.get("target_receipts", []):
        repetition, strategy = receipt["repetition"], receipt["strategy"]
        question = question_from_receipt(receipt)
        candidates = [case for case in reader_cases[(repetition, strategy)].values()
                      if case.get("question") == question
                      and case.get("response_text") == receipt.get("response", {}).get("response_text")]
        if len(candidates) != 1:
            raise ValueError("Target receipt does not match one frozen question/response.")
        case = candidates[0]
        qid = case["case_id"]
        grade_key = (repetition, strategy, qid)
        if grade_key not in grades or grade_key in receipts_seen:
            raise ValueError("Target receipt has no unique usable grader record.")
        receipts_seen.add(grade_key)
        source = oracle[qid]
        if source.get("question") != question:
            raise ValueError("Target question differs from the pinned LongMemEval source.")
        items.append({
            "question": question,
            "source_evidence": source_evidence(source),
            "benchmark_reference_answer": source["answer"],
            "target_response": receipt["response"]["response_text"],
            "human_judgment": "",
            "rationale": "",
        })
        private_items.append({
            "question_id": qid,
            "repetition": repetition,
            "strategy": strategy,
            "run_id": receipt["response"].get("run_id"),
            "response_id": receipt["response"].get("response_id"),
            "automatic_grader_label": grades[grade_key].get("autoeval_label"),
            "automatic_grader_model": grades[grade_key].get("reported_model"),
        })

    expected_count = len(selected_ids) * len(strategies) * protocol["C"]["repetitions"]
    if len(items) != expected_count or len(grades) != expected_count:
        raise ValueError("The C review sheet is not complete for its frozen condition grid.")

    rng = random.Random(20261028)
    order = list(range(len(items)))
    rng.shuffle(order)
    public_rows = []
    key_rows = []
    for blind_number, index in enumerate(order, 1):
        public_rows.append({"blind_item_id": f"C-{blind_number:03d}", **items[index]})
        key_rows.append({"blind_item_id": f"C-{blind_number:03d}", **private_items[index]})

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "blind-review.csv"
    instructions_path = output_dir / "BLIND_REVIEW_INSTRUCTIONS.md"
    readme_path = output_dir / "README.md"
    key_path = output_dir / "review-key-private.json"
    manifest_path = output_dir / "manifest.json"
    fields = list(public_rows[0])
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(public_rows)

    instructions_path.write_text(
        "# LongMemEval C answer review\n\n"
        "This sheet contains 84 target answers from the frozen 14-question local LongMemEval subset. "
        "Each question appears six times (two configurations, three repetitions); items are shuffled, "
        "and the configuration, repetition, run ID, and automatic grader label are omitted.\n\n"
        "For each row, compare the target response with the source transcript and the official "
        "benchmark reference answer. Enter **Pass**, **Fail**, or **Uncertain** in `human_judgment`, "
        "then give a short source-based explanation in `rationale`. Pass means the answer is correct "
        "and appropriately handles answerable or unanswerable questions. Fail means it gives a "
        "materially wrong or unsupported answer, or fails to abstain when the source does not answer "
        "the question. Use Uncertain when the source or reference is ambiguous or insufficient.\n\n"
        "Do not infer or add weak/strong labels. Complete the items independently before discussing "
        "any answers or looking at system scores. If you have already seen aggregate scores, record "
        "that exposure when returning the sheet; do not describe the result as an unexposed blind review. "
        "The project team has seen aggregate results, so this packet does not itself make their review "
        "independent.\n\n"
        "将每项答案与原始来源片段及 LongMemEval 参考答案比较，在 `human_judgment` 中填写 **Pass**、"
        "**Fail** 或 **Uncertain**，并在 `rationale` 写一句依据。请保留所有未决项；不要自行补填方法组别。\n\n"
        "This review checks the benchmark grader against the saved source/reference. It does not by "
        "itself establish independent Auditor validity or full-benchmark performance. Return only the "
        "completed CSV; keep `review-key-private.json` with the custodian.\n",
        encoding="utf-8",
    )
    readme_path.write_text(
        "# LongMemEval C grader review packet\n\n"
        "This folder contains a prepared, source-grounded review of all 84 saved "
        "grader decisions in the archived Proposal C compatibility run. It uses "
        "the frozen 14-question subset, two target configurations, and three "
        "repetitions. No human labels have been received.\n\n"
        "Give a reviewer only `blind-review.csv` and `BLIND_REVIEW_INSTRUCTIONS.md`. "
        "Do not share `review-key-private.json`; it maps blinded rows to the "
        "conditions and automatic judgments. The manifest records input and "
        "public-file hashes.\n\n"
        "The sheet checks the benchmark grader's saved decisions. It does not "
        "replace the separate A/B Auditor-validity review or expand C into the "
        "full 500-case benchmark.\n",
        encoding="utf-8",
    )
    key_path.write_text(json.dumps({
        "warning": "PRIVATE: do not provide this file to reviewers.",
        "source_protocol_sha256": sha256(PROTOCOL_PATH),
        "source_run_sha256": sha256(RUN_PATH),
        "mapping": key_rows,
    }, indent=2), encoding="utf-8")
    manifest = {
        "format": "phase4-c-human-review-packet-v1",
        "scope": "review of saved LongMemEval grader decisions; not an Auditor-validity result",
        "selected_case_count": len(selected_ids),
        "repetition_count": protocol["C"]["repetitions"],
        "review_item_count": len(public_rows),
        "status": "prepared; no human labels received",
        "source_hashes": {
            "protocol_sha256": sha256(PROTOCOL_PATH),
            "archived_C_run_sha256": sha256(RUN_PATH),
            "pinned_oracle_sha256": sha256(ORACLE_PATH),
        },
        "public_files": {
            readme_path.name: sha256(readme_path),
            csv_path.name: sha256(csv_path),
            instructions_path.name: sha256(instructions_path),
        },
        "private_key_sha256": sha256(key_path),
        "reviewer_warning": "Do not call the project team's review independent or unexposed if aggregate results were seen.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output_dir), indent=2))


if __name__ == "__main__":
    main()
