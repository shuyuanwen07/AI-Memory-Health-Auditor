"""Paired MAX rubric test on disclosed, curated diagnostic answers.

This tests an evaluator, not the natural performance of a target model. A
source-only independent review gate precedes all scoring. No expected answer,
intended class or review judgment is supplied to the scorer.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1"
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["passed", "reason", "evidence_memory_ids", "failure_type", "classification_reason"],
    "properties": {
        "passed": {"type": ["boolean", "null"]}, "reason": {"type": "string"},
        "evidence_memory_ids": {"type": "array", "items": {"type": "string"}},
        "failure_type": {"type": ["string", "null"], "enum": ["accuracy", "freshness", "conflict_resolution", "appropriate_use", None]},
        "classification_reason": {"type": "string"},
    },
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def write(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("x", encoding="utf8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        temp = path.with_suffix(path.suffix + ".pending")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        temp.replace(path)


def verify():
    p = read(STUDY / "protocol.json")
    for name, expected in p["bound_files_sha256"].items():
        path = Path("/app") / Path(name).relative_to("backend") if ROOT == Path("/") and name.startswith("backend/") else ROOT / name
        if sha(path) != expected:
            raise ValueError(f"Frozen study file changed: {name}")
    return p


def payload_for(item, sources, instructions):
    source = sources[item["source_id"]]
    memories = [{"memory_id": m["message_id"], "canonical_value": m["content"],
                 "timestamp": m.get("timestamp")} for m in source["messages"]]
    user_input = "Question: " + item["question"] + "\nTarget answer: " + item["answer"] + "\nConfirmed memory records: " + json.dumps(memories, ensure_ascii=False)
    return {"model": "gpt-6-astra", "reasoning": {"effort": "max"}, "max_output_tokens": 8192,
            "instructions": instructions, "input": user_input,
            "text": {"format": {"type": "json_schema", "name": "ac3_taxonomy_judgment", "strict": True, "schema": SCHEMA}}}, memories


def freeze():
    # Independent review consensus, including exclusions, must exist before calls.
    dataset = read(STUDY / "dataset-frozen.json")
    refs = read(STUDY / "reference-consensus.json")
    packet = read(STUDY / "blind-review/material.json")
    if refs["source_packet_sha256"] != sha(STUDY / "blind-review/material.json") or dataset["sources"] != packet["sources"] or dataset["items"] != packet["items"]:
        raise ValueError("Frozen inputs are not the independently reviewed records")
    if refs.get("ready_for_scoring") is not True or len(dataset["items"]) != 150:
        raise ValueError("Reference review gate is not ready")
    if (STUDY / "protocol.json").exists():
        raise ValueError("Existing frozen study is preserved")
    from ast import literal_eval, parse
    # Read the exact baseline text without importing application state on host.
    original = ROOT / "backend/app/evaluator/taxonomy_evaluator.py"
    tree = parse(original.read_text())
    rubric = next(literal_eval(n.value) for n in tree.body if getattr(n, "targets", None) and any(getattr(t, "id", None) == "RUBRIC" for t in n.targets))
    baseline = STUDY / "original-rubric.txt"
    baseline.write_text(rubric, encoding="utf8")
    bound = [STUDY / "dataset-frozen.json", STUDY / "reference-consensus.json",
             baseline, STUDY / "development/revised-rubric.txt", STUDY / "ANALYSIS-PLAN.md", STUDY / "blind-review/material.json",
             Path(__file__).resolve(), ROOT / "backend/app/evaluator/llm_judge.py"]
    bound += sorted((STUDY / "review-max").glob("reviewer-*.json"))
    rng = random.Random(20261102)
    case_ids = [item["review_id"] for item in dataset["items"]]
    rng.shuffle(case_ids)
    first_arms = ["original"] * 75 + ["revised"] * 75
    rng.shuffle(first_arms)
    pairs = [{"review_id": rid, "arms": [first, "revised" if first == "original" else "original"]}
             for rid, first in zip(case_ids, first_arms, strict=True)]
    jobs = [{"arm": arm, "review_id": pair["review_id"]} for pair in pairs for arm in pair["arms"]]
    protocol = {
        "format": "ac3-balanced-max-paired-protocol-v1", "frozen_at_utc": now(),
        "study_kind": "controlled_curated_fault_injection_evaluator_diagnostic",
        "target_model_performance_claim": False, "new_histories": 30, "planned_cases": 150,
        "planned_judge_calls": 300, "provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max",
        "output_token_limit": 8192, "provider_attempts": 1, "timeout_seconds": 300, "workers": 8,
        "provider_circuit_breaker": "Stop not-yet-dispatched jobs after an authentication or rate-limit response; no automatic request retries.",
        "experimental_variable": "original versus revised scoring rubric only",
        "temperature_sent": None, "seed_sent": None, "job_order_seed": 20261102,
        "judge_input": ["question", "saved_curated_answer", "source_confirmed_memory_records"],
        "withheld_from_judge": ["reference_answer", "intended_category", "question_dimension", "review_labels", "case_kind"],
        "minimum_reference_pass": 30, "minimum_actual_failures_per_type": 30,
        "thresholds": {"failure_detection_min": 0.8, "correct_category_all_reference_failures_min": 0.8,
                       "question_reference_validity_min": 0.9, "false_positive_max": 0.1, "decided_coverage_min": 0.8},
        "bound_files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in bound}, "jobs": jobs, "pair_schedule": pairs,
        "dispatch_order": "Randomized between cases; sequential within each pair; exactly75original-first and75revised-first pairs.",
        "limits": ["Curated diagnostic errors do not estimate natural target error frequency.",
                   "Independent reference agents and scorers share the Astra family.",
                   "Thirty synthetic source clusters are not a population-random sample.",
                   "Improvement is a hypothesis; strong baseline performance or ties remain reportable.",
                   "New AI reference checks require separate human verification; prior approval does not cover these new cases."],
    }
    write(STUDY / "protocol.json", protocol, exclusive=True)
    print(json.dumps({"frozen": str(STUDY / "protocol.json"), "sha256": sha(STUDY / "protocol.json"), "model_calls": 0}))


def worker(arm, review_id):
    import httpx
    from app.evaluator.llm_judge import LLMBehaviourEvaluator
    verify()
    data = read(STUDY / "dataset-frozen.json")
    item = next(x for x in data["items"] if x["review_id"] == review_id)
    sources = {s["source_id"]: s for s in data["sources"]}
    rubric_path = STUDY / ("original-rubric.txt" if arm == "original" else "development/revised-rubric.txt")
    payload, memories = payload_for(item, sources, rubric_path.read_text())
    result = {"state": "dispatched", "arm": arm, "review_id": review_id, "started_utc": now(),
              "provider": "openai", "requested_model": "gpt-6-astra", "reasoning_effort": "max",
              "request_attempts": 1, "output_token_limit": 8192, "request_payload_sha256": digest(payload),
              "shared_input_sha256": digest(payload["input"])}
    try:
        response = httpx.post("https://api.openai.com/v1/responses", headers={
            "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
            json=payload, timeout=300)
        result["http_status"] = response.status_code
        if not response.is_success:
            raise ValueError("Provider request failed")
        data = response.json()
        text = "".join(p.get("text", "") for o in data.get("output", []) if o.get("type") == "message" for p in o.get("content", []) if p.get("type") == "output_text")
        result.update(raw_output_text=text, usage=data.get("usage"), reported_model=data.get("model"), provider_reasoning=data.get("reasoning"), completion_status=data.get("status"), provider_response_id=data.get("id"))
        verdict = json.loads(text)
        LLMBehaviourEvaluator._validated_result(verdict, {m["memory_id"] for m in memories})
        if verdict.get("passed") is not None and not verdict.get("evidence_memory_ids"):
            raise ValueError("Decided assessment lacks supplied evidence")
        if data.get("model") != "gpt-6-astra" or data.get("status") != "completed":
            raise ValueError("Provider model/completion mismatch")
        result.update(state="returned", judgment=verdict, usage=data.get("usage"),
                      reported_model=data.get("model"), completion_status=data.get("status"), provider_response_id=data.get("id"))
    except Exception as exc:
        result.update(state="failed_without_retry", error_type=type(exc).__name__)
    result["completed_utc"] = now()
    print(json.dumps(result, ensure_ascii=False))


def execute():
    protocol = verify()
    provider_stop = Event()
    def one(job):
        path = STUDY / "scores" / job["arm"] / (job["review_id"] + ".json")
        if path.exists():
            return read(path)
        if provider_stop.is_set():
            return {**job, "state": "not_dispatched_provider_stop"}
        write(path, {**job, "state": "dispatched", "started_utc": now()}, exclusive=True)
        try:
            result = subprocess.run(["docker", "compose", "exec", "-T", "backend", "python",
                "/scripts/run_ac3_balanced_taxonomy_20261102.py", "--worker", job["arm"], job["review_id"]],
                cwd=ROOT, capture_output=True, text=True, timeout=360)
            raw = STUDY / "raw" / job["arm"] / (job["review_id"] + ".stdout")
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(result.stdout)
            if result.returncode:
                raise ValueError("Worker process failed")
            record = json.loads(result.stdout)
            record["raw_sha256"] = sha(raw)
        except Exception as exc:
            record = {**job, "state": "ambiguous_without_retry", "error_type": type(exc).__name__}
        if record.get("http_status") in (401, 403, 429):
            provider_stop.set()
        write(path, record)
        print(json.dumps({**job, "state": record["state"]}), flush=True)
        return record
    def one_pair(pair):
        return [one({"arm": arm, "review_id": pair["review_id"]}) for arm in pair["arms"]]
    with ThreadPoolExecutor(max_workers=protocol["workers"]) as pool:
        paired_results = list(pool.map(one_pair, protocol["pair_schedule"]))
    results = [result for pair in paired_results for result in pair]
    write(STUDY / "collection-summary.json", {"planned": 300, "returned": sum(x["state"] == "returned" for x in results),
                                               "errors_or_ambiguous": sum(x["state"] != "returned" for x in results)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", nargs=2, metavar=("ARM", "REVIEW_ID"))
    args = parser.parse_args()
    if args.worker:
        worker(*args.worker)
    elif args.freeze:
        freeze()
    elif args.execute:
        execute()
    else:
        parser.error("Choose --freeze, --execute or --worker")
