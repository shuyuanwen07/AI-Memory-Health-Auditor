"""Publish only aggregate, non-response evidence for the expanded C results page."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V5_DIR = ROOT / "artifacts/local/phase4-c-openrouter-20261027-v5"
V6_DIR = ROOT / "artifacts/local/phase4-c-openrouter-20261028-v6"
OUT = ROOT / "frontend/public/reports/phase4-c-expanded-v6.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def accuracy(correct: int, total: int) -> dict[str, int | float]:
    return {"correct": correct, "total": total,
            "accuracy_percent": round(100 * correct / total, 4) if total else 0.0}


def segment(case_count: int, repetitions: list[dict[str, Any]], protocol_sha: str,
            run_sha: str, winner: str, interpretation: str) -> dict[str, Any]:
    weak_correct = sum(row["weak_correct"] for row in repetitions)
    strong_correct = sum(row["strong_correct"] for row in repetitions)
    total = sum(row["total"] for row in repetitions)
    return {
        "case_count": case_count,
        "repetitions": len(repetitions),
        "per_repetition": repetitions,
        "aggregate": {"weak": accuracy(weak_correct, total), "strong": accuracy(strong_correct, total)},
        "protocol_sha256": protocol_sha,
        "run_sha256": run_sha,
        "winner": winner,
        "interpretation": interpretation,
    }


def main() -> None:
    v5 = read(V5_DIR / "analysis.json")
    v5_protocol = read(V5_DIR / "protocol.json")
    v5_run_path = V5_DIR / "C-live.json"
    v6 = read(V6_DIR / "analysis.json")
    v6_protocol = read(V6_DIR / "protocol.json")
    v6_run = read(V6_DIR / "C-live.json")
    compare = read(V6_DIR / "comparison-summary.json")
    protocol_path = V6_DIR / "protocol.json"
    run_path = V6_DIR / "C-live.json"
    if v6.get("collection_status") != "complete_automatic_collection":
        raise SystemExit("Refusing to publish an incomplete v6 collection.")
    if v6.get("decision", {}).get("rule_passed") is not True:
        raise SystemExit("Refusing to publish a decision that did not pass its frozen rule.")
    if len(v6_run.get("target_receipts", [])) != 180 or len(v6_run.get("grades", [])) != 180:
        raise SystemExit("Refusing to publish without the complete 180-answer and 180-grade grid.")
    if v6_run.get("protocol_sha256") != sha256(protocol_path):
        raise SystemExit("The saved v6 run is not bound to the frozen protocol file.")

    v5_reps = []
    v5scores = v5["scores"]["per_repetition"]
    for repetition in range(1, 4):
        weak = next(row for row in v5scores if row["repetition"] == repetition and row["strategy"] == "weak_first_hit")
        strong = next(row for row in v5scores if row["repetition"] == repetition and row["strategy"] == "strong_rule_based")
        v5_reps.append({"repetition": repetition, "weak_correct": weak["correct"], "strong_correct": strong["correct"], "total": 14})
    v5_segment = segment(14, v5_reps, sha256(V5_DIR / "protocol.json"), sha256(v5_run_path),
                         "strong_rule_based", "Preserved 14-case v5 cohort; separate collection from v6.")

    v6_reps = []
    for row in v6["scores"]["paired_repetitions"]:
        v6_reps.append({"repetition": row["repetition"], "weak_correct": row["weak_correct"],
                        "strong_correct": row["strong_correct"], "total": 30})
    decision = v6["decision"]["recommended_strategy"]
    v6_segment = segment(30, v6_reps, sha256(protocol_path), sha256(run_path), decision,
                         "Primary decision uses only the 30 new v6 cases and its predeclared three-repeat rule.")
    category_results = []
    for category in v6["selected_category_counts"]:
        weak = v6["scores"]["category_level"]["weak_first_hit"][category]
        strong = v6["scores"]["category_level"]["strong_rule_based"][category]
        category_results.append({
            "category": category,
            "case_count": v6["selected_category_counts"][category],
            "repetitions": 3,
            "weak": accuracy(weak["correct"], weak["expected"]),
            "strong": accuracy(strong["correct"], strong["expected"]),
        })
    v6_segment["category_results"] = category_results
    v6_segment["coverage"] = {"target_answers": 180, "usable_grades": 180, "complete": True}
    v6_segment["operational_diagnostics"] = {
        "target_latency_ms_mean": {
            "weak": v6["operational_tradeoffs"]["target_latency_ms_mean_and_median"]["weak_first_hit"]["mean"],
            "strong": v6["operational_tradeoffs"]["target_latency_ms_mean_and_median"]["strong_rule_based"]["mean"],
        },
        "target_input_tokens": {
            "weak": v6["operational_tradeoffs"]["target_token_usage"]["weak_first_hit"]["input_sum"],
            "strong": v6["operational_tradeoffs"]["target_token_usage"]["strong_rule_based"]["input_sum"],
        },
        "estimated_cost_usd": v6["operational_tradeoffs"]["cost"]["estimated_usd"],
        "billing_uncertain": v6["operational_tradeoffs"]["provider_request_failures"]["billing_uncertain"],
        "recovered_http_429_attempts": 3,
        "unresolved_requests": 0,
        "note": "Token-rate cost estimate, not a provider invoice; three explicit grader 429 responses were recovered under the saved operational addendum.",
    }
    v6_segment["human_review"] = {"status": "pending", "review_items": 180, "independent_histories": 30}

    combined_reps = []
    combined_raw = compare["combined_44_case_secondary"]["per_repetition"]
    for row in combined_raw:
        combined_reps.append({"repetition": row["repetition"],
                              "weak_correct": row["weak_first_hit"]["correct"],
                              "strong_correct": row["strong_rule_based"]["correct"], "total": 44})
    combined_segment = segment(44, combined_reps, None, None, "strong_rule_based",
                               "Secondary descriptive sum of separate v5 and v6 collections; not the primary decision.")
    combined_segment["source_snapshots_match"] = False

    public = {
        "format": "phase4-c-expanded-v6",
        "study_id": "phase4-c-expanded-study-v6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "revision": v6_protocol["source"]["revision"],
            "license": v6_protocol["source"]["license"],
            "source_sha256": v6_protocol["source"]["oracle_source_sha256"],
            "dataset": v6_protocol["source"]["dataset"],
            "citation": "Wu et al. (2025), LongMemEval: Benchmarking chat assistants on long-term interactive memory. ICLR. https://openreview.net/forum?id=pZiyCaVuti",
        },
        "baseline_v5": v5_segment,
        "extension_v6": v6_segment,
        "combined": combined_segment,
        "decision": {
            "selected_strategy": decision,
            "rule": "Choose Strong only when its pooled v6 pass rate exceeds Weak and it wins at least 2 of 3 repetition-level paired comparisons.",
            "reason": "Strong scored 61/90 (67.8%) versus Weak 19/90 (21.1%) and ranked higher in all three paired repetitions; the frozen rule passed.",
            "repeat_wins": 3,
        },
        "limitations": [
            "v6 is a local compatibility experiment on 30 newly selected cases from a 500-case source, not the full official benchmark or its official score.",
            "The automatic GPT-6 Luna grader shares the target model family; the 180 saved decisions have not yet received independent human review.",
            "Three repetitions reuse the same 30 source histories; 90 answers per strategy are not 90 independent histories.",
            "Category results are small descriptive subgroups; multi-session performance remains weak and temporal reasoning remains limited.",
            "The combined 44-case row is secondary: v5 and v6 were collected on different days and different frozen code snapshots.",
            "This page measures target retrieval-strategy outcomes. It does not by itself establish the Auditor's independent validity, extraction recall, or generalisation.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "sha256": sha256(OUT),
                      "bytes": OUT.stat().st_size, "contains_raw_answers": False}, indent=2))


if __name__ == "__main__":
    main()
