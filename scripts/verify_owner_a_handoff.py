#!/usr/bin/env python3
"""Verify an English Owner A distribution without accessing the other split."""
import argparse
import csv
import platform
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))

DEFAULT_PACKAGE = ROOT / "handoff/owner-a"


def validate(package=DEFAULT_PACKAGE, schema=False):
    manifest = read_json(package / "freeze_manifest.json")
    inventory = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
    check(inventory == set(manifest["files"]) | {"freeze_manifest.json"}, "File inventory changed")
    for name, digest in manifest["files"].items():
        check(hashlib.sha256((package / name).read_bytes()).hexdigest() == digest, f"SHA mismatch: {name}")
    for path in package.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".csv"}:
            check(not re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", path.read_text()), f"Non-English CJK text: {path.name}")
    summary = read_json(package / "review_summary.json")
    check(not summary["ready_for_formal_evaluation"] and summary["human_annotators_completed"] == 0, "False human readiness claim")
    results, total, refined, all_ids = {}, 0, 0, set()
    split = summary["split"]
    check(split in {"development", "heldout"}, "Unknown split")
    for split, count in [(split, 195 if split == "development" else 130)]:
        base = package / split
        dataset = read_json(base / "annotation_dataset.json")
        conversations = dataset["conversations"]
        ids = {c["conversation_id"] for c in conversations}
        check(not ids & all_ids, "Split overlap")
        all_ids.update(ids)
        check(dataset["dataset_version"] == "2.0.0-ai-reviewed", "Unexpected version")
        labels = read_csv(base / "completed_labels.csv")
        decisions = read_csv(base / "decision_log.csv")
        def key(row):
            return row["item_id"], row["task"]
        lookup, log = {key(r): r for r in labels}, {key(r): r for r in decisions}
        check(len(labels) == len(lookup) == len(log) == len(decisions) == count, "Missing or duplicate review rows")
        check(set(lookup) == set(log), "Decision coverage mismatch")
        expected, source = {}, {}
        memories = {m["memory_id"]: m for c in conversations for m in c["gold_memories"]}
        for c in conversations:
            source[c["conversation_id"]] = {m["message_id"]: m["content"] for m in c["messages"]}
            for m in c["gold_memories"]:
                expected[m["memory_id"], "memory_inclusion"] = "include"
            for t in c["gold_tests"]:
                expected[t["test_id"], "test_validity"] = t["quality_label"]
            for e in c["gold_evaluations"]:
                expected[e["response_id"], "evaluator_verdict"] = "pass" if e["passed"] else "fail"
                expected[e["response_id"], "failure_dimension"] = e["failure_type"] or "none"
        pairs = re.findall(r"\*\*(A\d+-P\d+)\*\* (A\d+-G\d+) → (A\d+-G\d+)", (base / "blind/stage_1.md").read_text())
        for uid, src, tgt in pairs:
            expected[uid, "relationship_type"] = next((r["type"] for r in memories[src]["relationships"] if r["target_memory_id"] == tgt), "none")
        for k, row in lookup.items():
            decision = log[k]
            check(row["label"] == expected.get(k, "exclude" if row["task"] == "memory_inclusion" else None), f"Label/dataset mismatch: {k}")
            evidence = row["source_message_ids"].split("|")
            messages = source[row["conversation_id"]]
            check(set(evidence) <= messages.keys(), f"Invalid evidence: {k}")
            check(row["evidence_text"] == " | ".join(f"{sid}: {messages[sid]}" for sid in evidence), f"Evidence text drift: {k}")
            check(row["human_confirmed"] == "false" and row["label_provenance"] == "ai_assisted_source_visible_review", "False label provenance")
            check(row["decision_note"] and row["decision_note"] == decision["decision_note"], "Missing decision note")
            check(row["label"] == decision["final_ai_label"] and row["source_message_ids"] == decision["final_source_message_ids"], "Decision/label mismatch")
            refined += decision["initial_source_message_ids"] != decision["final_source_message_ids"]
        check(read_json(base / "source_conversations.json")["conversations"] == [{"conversation_id": c["conversation_id"], "messages": c["messages"]} for c in conversations], "Source drift")
        results[split] = {"completed_labels": count, "completed_decisions": count}
        if schema:
            sys.path.insert(0, str(ROOT / "backend"))
            from app.schemas.annotation import AnnotationDataset
            from app.schemas.pilot import PilotLabel, PilotAnalysisRequest
            from app.research.pilot import PilotAnnotationService
            from app.schemas.research import annotation_fingerprint
            model = AnnotationDataset.model_validate(dataset)
            for row in labels:
                PilotLabel.model_validate(row)
            fingerprint = annotation_fingerprint(model)
            check(fingerprint == manifest["api_dataset_fingerprints"][split], "Schema fingerprint drift")
            pending = read_json(base / "forms/human_annotation_pending.json")
            check((pending["dataset_id"], pending["dataset_version"]) == (dataset["dataset_id"], dataset["dataset_version"]), "Pending form identity mismatch")
            check({(item["item_id"], item["task"]) for item in pending["items"]} == set(lookup), "Pending form inventory mismatch")
            report = PilotAnnotationService().analyse(PilotAnalysisRequest.model_validate({"package": pending}))
            check(not report.ready_for_formal_evaluation and report.overall.paired_items == 0, "Unexpected human gate readiness")
            import pydantic
            results[split].update(api_fingerprint_sha256=fingerprint, human_paired_items=0, pydantic_version=pydantic.__version__)
        total += count
    check(total == summary["completed_label_rows"] == summary["completed_decision_rows"], "Summary count mismatch")
    check(refined == summary["evidence_sets_refined"], "Evidence change count mismatch")
    return {"integrity": "passed", "schema_checked": schema, "splits": results, "evidence_sets_refined": refined, "ready_for_formal_evaluation": False, "human_labels": 0, "python_version": platform.python_version()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.package, args.schema), indent=2))
    except (ValueError, KeyError, OSError, ImportError) as exc:
        parser.exit(1, f"Validation failed: {exc}\n")
