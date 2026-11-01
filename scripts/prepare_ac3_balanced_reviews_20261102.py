"""Prepare opaque source-only references and freeze their conservative consensus."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1"
TYPES = ("accuracy", "freshness", "conflict_resolution", "appropriate_use")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def pack():
    data = read(STUDY / "dataset-draft.json")
    assert len(data["sources"]) == 30 and len(data["items"]) == 150
    source_ids = {s["source_id"] for s in data["sources"]}
    ids = {i["review_id"] for i in data["items"]}
    assert len(source_ids) == 30 and len(ids) == 150
    assert all(i["source_id"] in source_ids for i in data["items"])
    packet = {
        "format": "ac3-balanced-source-only-blind-reference-v1",
        "study_kind": "curated_synthetic_evaluator_diagnostic_not_natural_target_performance",
        "instructions": [
            "Independently judge each question and supplied answer using only its source messages. No intended category, model score, proposed rubric revision or other reviewer is supplied.",
            "Source claims can intentionally conflict. Check whether explicit same-scope exclusivity and lack of resolution support a conflict-handling question, rather than treating all contradictory records as an invalid test.",
            "Accuracy is an ordinary unsupported or incorrect fact. Freshness requires actual misuse of an explicitly superseded state. Conflict resolution requires actual mishandling of incompatible active claims. Appropriate use requires actual misapplication of scope/default/exception.",
            "Infer the actual answer error, never a category from the question topic alone. Do not force precedence. Separate material errors can be multiple; insufficient causal evidence can remain uncertain.",
            "Return source_checks for every source, and items for every review_id; keep missing, invalid and uncertain observations. Cite supplied message IDs.",
            "Schema: source_checks=[{source_id,validity:valid|invalid|uncertain,reason}]; items=[{review_id,question_validity:valid|invalid|uncertain,verdict:pass|fail|uncertain,failure_type:accuracy|freshness|conflict_resolution|appropriate_use|null,failure_type_status:single|multiple|uncertain|not_applicable,evidence_message_ids:[...],reason}].",
            "Include reviewer_declaration with reviewer_kind=AI,model=gpt-6-astra,reasoning_effort=max,completed_independently=true,has_seen_other_reviewer_or_automatic_scores=false,completed_by_human=false,human_confirmation_pending=true.",
        ],
        "sources": data["sources"], "items": data["items"],
    }
    write(STUDY / "blind-review/material.json", packet)
    print(json.dumps({"sources": 30, "items": 150, "sha256": sha(STUDY / "blind-review/material.json")}))


def merge():
    packet = read(STUDY / "blind-review/material.json")
    current_draft = read(STUDY / "dataset-draft.json")
    if packet["sources"] != current_draft["sources"] or packet["items"] != current_draft["items"]:
        raise ValueError("Draft changed after the independent reference packet was prepared")
    reviews = [read(STUDY / f"review-max/reviewer-{i}.json") for i in (1, 2)]
    answers = []
    sources = []
    expected = {x["review_id"] for x in packet["items"]}
    source_ids = {x["source_id"] for x in packet["sources"]}
    allowed_evidence = {x["source_id"]: {m["message_id"] for m in x["messages"]} for x in packet["sources"]}
    item_sources = {x["review_id"]: x["source_id"] for x in packet["items"]}
    for review in reviews:
        declaration = review["reviewer_declaration"]
        assert declaration["model"] == "gpt-6-astra" and declaration["reasoning_effort"] == "max"
        assert declaration["completed_independently"] is True and declaration["has_seen_other_reviewer_or_automatic_scores"] is False
        assert {x["review_id"] for x in review["items"]} == expected and len(review["items"]) == 150
        assert {x["source_id"] for x in review["source_checks"]} == source_ids and len(review["source_checks"]) == 30
        for item in review["items"]:
            assert item["question_validity"] in ("valid", "invalid", "uncertain")
            assert item["verdict"] in ("pass", "fail", "uncertain")
            assert set(item["evidence_message_ids"]) <= allowed_evidence[item_sources[item["review_id"]]]
            assert item["evidence_message_ids"] or item["verdict"] == "uncertain"
            assert item["failure_type"] in (*TYPES, None)
            assert item["failure_type_status"] in ("single", "multiple", "uncertain", "not_applicable")
            if item["verdict"] == "pass":
                assert item["failure_type"] is None
    item_maps = [{x["review_id"]: x for x in r["items"]} for r in reviews]
    source_maps = [{x["source_id"]: x for x in r["source_checks"]} for r in reviews]
    for source in packet["sources"]:
        pair = [r[source["source_id"]] for r in source_maps]
        sources.append({"source_id": source["source_id"], "accepted_by_both": all(x["validity"] == "valid" for x in pair), "reviews": pair})
    source_ok = {s["source_id"] for s in sources if s["accepted_by_both"]}
    for item in packet["items"]:
        pair = [r[item["review_id"]] for r in item_maps]
        valid = item["source_id"] in source_ok and all(x["question_validity"] == "valid" for x in pair)
        verdict = pair[0]["verdict"] if valid and pair[0]["verdict"] == pair[1]["verdict"] else "uncertain"
        category = pair[0]["failure_type"] if verdict == "fail" and all(x["failure_type_status"] == "single" for x in pair) and pair[0]["failure_type"] == pair[1]["failure_type"] and pair[0]["failure_type"] in TYPES else None
        answers.append({"review_id": item["review_id"], "source_id": item["source_id"], "question_source_valid": valid,
                        "verdict": verdict, "failure_type": category, "reviews": pair})
    failures = Counter(x["failure_type"] for x in answers if x["verdict"] == "fail")
    counts = Counter(x["verdict"] for x in answers)
    ready = counts["pass"] >= 30 and all(failures[t] >= 30 for t in TYPES) and len(source_ok) == 30 and all(x["question_source_valid"] for x in answers)
    consensus = {"format": "ac3-balanced-independent-max-reference-v1", "ready_for_scoring": ready,
                 "human_confirmation_pending": True, "completed_by_human": False,
                 "review_model": "gpt-6-astra", "reasoning_effort": "max",
                 "source_packet_sha256": sha(STUDY / "blind-review/material.json"),
                 "review_files_sha256": {f"reviewer-{i}.json": sha(STUDY / f"review-max/reviewer-{i}.json") for i in (1, 2)},
                 "verdict_counts": dict(counts), "actual_agreed_failure_type_counts": dict(failures),
                 "sources": sources, "items": answers,
                 "limits": "Actual independent reference agreement, not intended injection tags. AI reference findings await human verification."}
    write(STUDY / "reference-consensus.json", consensus)
    if ready:
        # Freeze exactly the reviewed records, not a post-scoring selected subset.
        write(STUDY / "dataset-frozen.json", read(STUDY / "dataset-draft.json"))
    print(json.dumps({"ready": ready, "verdicts": dict(counts), "types": dict(failures)}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", action="store_true")
    p.add_argument("--merge", action="store_true")
    args = p.parse_args()
    if args.pack:
        pack()
    elif args.merge:
        merge()
    else:
        p.error("Choose --pack or --merge")
