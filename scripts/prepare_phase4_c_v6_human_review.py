"""Prepare a blinded human answer-review packet from the saved Phase 4 C v6 run.

This script is offline: it reads the frozen subset and completed target receipts,
then writes a reviewer sheet and a separate private identity key. It never calls
the model or changes the experiment result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import secrets
import stat
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "artifacts/local/phase4-c-openrouter-20261028-v6"
DEFAULT_OUTPUT = ROOT / "output/proposal-delivery/phase4-c-v6-human-review"
EXPECTED_PROTOCOL_ID = "phase4-c-openrouter-gpt6-luna-expansion-20261028-v6"
EXPECTED_CASES = 30
EXPECTED_REPETITIONS = 3
EXPECTED_STRATEGIES = {"weak_first_hit", "strong_rule_based"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_text(case: dict[str, Any]) -> str:
    """Return answer-relevant source transcripts without exposing session IDs."""
    ids = case.get("answer_session_ids") or []
    haystack_ids = case.get("haystack_session_ids") or []
    sessions = case.get("haystack_sessions") or []
    if len(haystack_ids) != len(sessions):
        raise ValueError(f"Source transcript metadata is malformed for {case.get('question_id')}.")
    by_id = dict(zip(haystack_ids, sessions))
    chosen = [by_id[session_id] for session_id in ids if session_id in by_id]
    if not chosen:
        chosen = list(sessions)
    if not chosen:
        raise ValueError(f"No source transcript is available for {case.get('question_id')}.")
    return json.dumps(
        [{"source_transcript": number, "messages": messages}
         for number, messages in enumerate(chosen, 1)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _unique_key(row: dict[str, Any]) -> tuple[int, str, str]:
    try:
        repetition = int(row["repetition"])
        strategy = row["strategy"]
        question_id = row["question_id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("A saved v6 record has an incomplete answer identity.") from exc
    if repetition not in range(1, EXPECTED_REPETITIONS + 1):
        raise ValueError("A saved v6 record has a repetition outside the frozen three-run grid.")
    if strategy not in EXPECTED_STRATEGIES or not isinstance(question_id, str) or not question_id:
        raise ValueError("A saved v6 record has an unexpected strategy or missing question ID.")
    return repetition, strategy, question_id


def _reader_responses(run: dict[str, Any]) -> dict[tuple[int, str, str], str]:
    result: dict[tuple[int, str, str], str] = {}
    for reader_run in run.get("reader_runs", []):
        repetition = reader_run.get("repetition")
        strategy = reader_run.get("strategy")
        conditions = (reader_run.get("result") or {}).get("conditions", [])
        if not isinstance(conditions, list) or len(conditions) != 1:
            raise ValueError("A saved reader run has an unexpected condition count.")
        cases = conditions[0].get("cases", [])
        for case in cases:
            qid = case.get("case_id")
            response = case.get("response_text")
            key = _unique_key({"repetition": repetition, "strategy": strategy, "question_id": qid})
            if key in result or not isinstance(response, str):
                raise ValueError("A saved reader answer is duplicated or malformed.")
            result[key] = response
    return result


def prepare(run_path: Path, subset_path: Path, output_dir: Path, seed: int | None = None) -> dict[str, Any]:
    """Create a complete v6 review packet; never overwrite an existing packet."""
    run = load_json(run_path)
    subset = load_json(subset_path)
    if run.get("protocol_id") != EXPECTED_PROTOCOL_ID:
        raise ValueError("Input run is not bound to the frozen v6 expansion protocol.")
    if not isinstance(subset, list) or len(subset) != EXPECTED_CASES:
        raise ValueError("The v6 frozen subset must contain exactly 30 cases.")
    by_id = {row.get("question_id"): row for row in subset if isinstance(row, dict)}
    if len(by_id) != EXPECTED_CASES or any(not isinstance(qid, str) or not qid for qid in by_id):
        raise ValueError("The v6 subset has missing or duplicate question IDs.")
    if set(run.get("target_configuration", {}).get("strategies", [])) != EXPECTED_STRATEGIES:
        raise ValueError("The run's saved strategies differ from the frozen v6 comparison.")
    if run.get("target_configuration", {}).get("repetitions") != EXPECTED_REPETITIONS:
        raise ValueError("The run's saved repetition count differs from the frozen v6 comparison.")

    receipts = {}
    for receipt in run.get("target_receipts", []):
        key = _unique_key(receipt)
        if key in receipts:
            raise ValueError("The saved target receipts contain duplicate answer identities.")
        response = (receipt.get("response") or {}).get("response_text")
        if not isinstance(response, str) or not response.strip():
            raise ValueError("A target receipt has no saved answer text.")
        if key[2] not in by_id:
            raise ValueError("A target receipt refers to a question outside the frozen v6 subset.")
        receipts[key] = receipt

    expected_keys = {
        (repetition, strategy, qid)
        for repetition in range(1, EXPECTED_REPETITIONS + 1)
        for strategy in EXPECTED_STRATEGIES
        for qid in by_id
    }
    if set(receipts) != expected_keys:
        raise ValueError(f"Expected all {len(expected_keys)} saved v6 target answers before packet creation.")

    reader_responses = _reader_responses(run)
    if set(reader_responses) != expected_keys:
        raise ValueError("Saved reader-run answers do not cover the exact v6 target answer grid.")
    for key, receipt in receipts.items():
        response = receipt["response"]["response_text"]
        if reader_responses[key] != response:
            raise ValueError("A target receipt does not match its saved reader-run answer.")

    grades = {}
    for grade in run.get("grades", []):
        key = _unique_key(grade)
        if key in grades:
            raise ValueError("The saved grader records contain duplicate answer identities.")
        grades[key] = grade
    if not set(grades).issubset(expected_keys):
        raise ValueError("A grader record refers to an answer outside the frozen v6 grid.")

    items = []
    private_items = []
    for key in sorted(expected_keys):
        repetition, strategy, qid = key
        case = by_id[qid]
        items.append({
            "question": case["question"],
            "source_evidence": evidence_text(case),
            "benchmark_reference_answer": case["answer"],
            "target_response": receipts[key]["response"]["response_text"],
            "human_judgment": "",
            "rationale": "",
        })
        grade = grades.get(key, {})
        response = receipts[key].get("response") or {}
        private_items.append({
            "question_id": qid,
            "repetition": repetition,
            "strategy": strategy,
            "run_id": response.get("run_id"),
            "response_id": response.get("response_id"),
            "automatic_grader_label": grade.get("autoeval_label"),
            "automatic_grader_model": grade.get("reported_model"),
            "grader_verdict_usable": grade.get("verdict_usable"),
        })

    shuffle_seed = secrets.randbits(64) if seed is None else int(seed)
    rng = random.Random(shuffle_seed)
    order = list(range(len(items)))
    rng.shuffle(order)
    public_rows, key_rows = [], []
    for number, index in enumerate(order, 1):
        blind_id = f"V6-{number:03d}"
        public_rows.append({"blind_item_id": blind_id, **items[index]})
        key_rows.append({"blind_item_id": blind_id, **private_items[index]})

    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite a non-empty review packet directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "blind-review.csv"
    instructions_path = output_dir / "BLIND_REVIEW_INSTRUCTIONS.md"
    readme_path = output_dir / "README.md"
    key_path = output_dir / "review-key-private.json"
    manifest_path = output_dir / "manifest.json"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(public_rows[0]))
        writer.writeheader()
        writer.writerows(public_rows)

    instructions_path.write_text(
        "# Phase 4 C v6 human answer review\n\n"
        "Review each target response against the official reference answer and the supplied source transcript. "
        "Enter **Pass**, **Fail**, or **Uncertain** in `human_judgment`, then give a short evidence-based "
        "reason in `rationale`. Pass means the response is materially correct and handles answerable or "
        "unanswerable questions appropriately. Fail means it is materially incorrect, unsupported, or fails "
        "to abstain when the source does not contain the answer. Use Uncertain when the source is ambiguous "
        "or insufficient. Do not infer a configuration label.\n\n"
        "There are 180 answer judgments from 30 benchmark questions. Each question appears six times, "
        "because each of two configurations was run three times. These are repeated answers over the same "
        "30 histories, not 180 independent histories or independent cases. The randomized order and hidden "
        "identity key conceal the saved configuration and automatic grader labels, but repeated questions "
        "may make some answer variants recognizable.\n\n"
        "The packet supports a human check of these saved answers; by itself it does not establish full "
        "LongMemEval performance, independent Auditor validity, or generalisation beyond the selected 30 cases. "
        "If reviewers have already seen aggregate outcomes, record that exposure when returning the sheet.\n\n"
        "中文：请对照官方参考答案与所给原始来源片段，填写 **Pass**、**Fail** 或 **Uncertain**，并简要说明依据。"
        "本表有 180 条答案，来自 30 个问题（每个问题重复 6 次：两种配置各运行三次）；这不是 180 段独立历史。"
        "配置和自动评分标签已从表中隐藏，但重复问题可能让部分答案变体被识别。\n",
        encoding="utf-8",
    )
    readme_path.write_text(
        "# Phase 4 C v6 review packet\n\n"
        "Give the reviewer only `blind-review.csv` and `BLIND_REVIEW_INSTRUCTIONS.md`. Keep "
        "`review-key-private.json` with the study custodian; it links blinded items to question IDs, "
        "Weak/Strong configuration, repetition, run/response IDs, and saved automatic-grader metadata.\n\n"
        "The packet contains 180 repeated answer judgments over 30 selected LongMemEval questions "
        "(two configurations × three repetitions), not 180 independent histories. It does not make the "
        "30-case sample statistically independent or expand the study to the full 500-case benchmark.\n",
        encoding="utf-8",
    )

    key_data = json.dumps({
        "warning": "PRIVATE: do not provide this file to reviewers.",
        "source_run_sha256": sha256(run_path),
        "source_subset_sha256": sha256(subset_path),
        "mapping": key_rows,
    }, ensure_ascii=False, indent=2).encode("utf-8")
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(key_data)
    except BaseException:
        key_path.unlink(missing_ok=True)
        raise
    key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    manifest = {
        "format": "phase4-c-v6-human-review-packet-v1",
        "scope": "blinded human review of saved target answers; not 180 independent histories",
        "question_count": EXPECTED_CASES,
        "answers_per_question": len(EXPECTED_STRATEGIES) * EXPECTED_REPETITIONS,
        "review_item_count": len(public_rows),
        "shuffle_seed": shuffle_seed,
        "status": "prepared; no human labels received",
        "source_hashes": {
            "v6_C_live_sha256": sha256(run_path),
            "v6_subset_sha256": sha256(subset_path),
        },
        "public_files": {
            csv_path.name: sha256(csv_path),
            instructions_path.name: sha256(instructions_path),
            readme_path.name: sha256(readme_path),
        },
        "private_key_sha256": sha256(key_path),
        "limitations": [
            "180 judgments are repeated responses for 30 questions, not 180 independent histories.",
            "Repeated questions may allow reviewers to infer response variants despite hidden labels and randomized order.",
            "A human review of these selected cases does not establish full-benchmark performance or independent Auditor validity.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=RUN_DIR / "C-live.json")
    parser.add_argument("--subset", type=Path, default=RUN_DIR / "longmemeval-subset.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=None, help="Optional deterministic shuffle seed for reproducibility.")
    args = parser.parse_args()
    print(json.dumps(prepare(args.run, args.subset, args.output_dir, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
