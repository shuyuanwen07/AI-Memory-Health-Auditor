#!/usr/bin/env python3
"""Publish the compact, source-hash-bound Proposal A/B/C dashboard summary.

This script reads only the preserved local Phase 4 evidence bundle and the
already-published v6 aggregate. It makes no provider calls and never reads the
application database. The output contains aggregate counts, not answer text.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "artifacts/local/phase4-20261027"
V6_REPORT = ROOT / "frontend/public/reports/phase4-c-expanded-v6.json"
OUTPUT = ROOT / "frontend/public/reports/proposal-final-results-v1.json"

SOURCES = [
    "artifacts/local/phase4-20261027/analysis.json",
    "artifacts/local/phase4-20261027/A-verification-summary.json",
    "artifacts/local/phase4-20261027/A-AI-cross-check.json",
    "artifacts/local/phase4-20261027/human-reconciliation/A-reference-analysis-v1.json",
    "artifacts/local/phase4-20261027/human-reconciliation/A-chat-confirmed-revision-v1.json",
    "artifacts/local/phase4-20261027/human-reconciliation/A-open-items-v1.json",
    "artifacts/local/phase4-20261027/B-live.json",
    "artifacts/local/phase4-20261027/C-live.json",
    "artifacts/local/phase4-20261027/protocol.json",
    "artifacts/local/phase4-20261027/verification-summary.json",
    "artifacts/local/phase4-20261027/evidence-manifest.json",
    "frontend/public/reports/phase4-c-expanded-v6.json",
    "output/proposal-delivery/reconciliation-user-2026-10-28.json",
    "output/proposal-delivery/human-review-independence-user-confirmation-2026-10-28.json",
]

POLICIES = [
    ("weak_first_hit", "First-match retrieval"),
    ("strong_rule_based", "Relationship-priority retrieval"),
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def accuracy(correct: int, total: int) -> float | None:
    return round(correct * 100 / total, 4) if total else None


def publish() -> dict:
    analysis = read_json(BUNDLE / "analysis.json")
    a_execution = read_json(BUNDLE / "A-verification-summary.json")
    a_ai = read_json(BUNDLE / "A-AI-cross-check.json")
    a_reference = read_json(BUNDLE / "human-reconciliation/A-reference-analysis-v1.json")
    a_chat = read_json(BUNDLE / "human-reconciliation/A-chat-confirmed-revision-v1.json")
    a_open = read_json(BUNDLE / "human-reconciliation/A-open-items-v1.json")
    b_live = read_json(BUNDLE / "B-live.json")
    c_live = read_json(BUNDLE / "C-live.json")
    verification = read_json(BUNDLE / "verification-summary.json")
    v6 = read_json(V6_REPORT)
    reconciliation = read_json(ROOT / SOURCES[-2])
    confirmation = read_json(ROOT / SOURCES[-1])
    review_rows = [row for row in reconciliation['items'] if row.get('queue_id') == 'proposal_c_v6_review_180']
    integrity = reconciliation['source_integrity']
    return_hashes = [integrity['reviewer_a_return_source_sha256'], integrity['reviewer_b_return_source_sha256']]
    if (len(review_rows) != 180 or len({row['item_id'] for row in review_rows}) != 180
            or confirmation.get('format') != 'human-review-independence-confirmation-v1'
            or confirmation.get('applies_to_return_sha256') != return_hashes
            or integrity.get('template_identities_and_source_material_match_master') is not True):
        raise ValueError('Expanded C review provenance is incomplete')
    review_agreed = sum(row['status'] == 'reviewer_agreement_recorded_no_adjudication' for row in review_rows)
    review_unresolved = sum(row['status'] == 'missing_or_uncertain_pending_human_review' for row in review_rows)
    if review_agreed + review_unresolved != 180:
        raise ValueError('Unexpected expanded C review status')

    # A combines the retained 36-answer run ledger with the explicitly
    # retrospective, AI-assisted case review. The adopted verdicts are not
    # treated as independent human gold or as formal discovery/recall.
    per_method = []
    a_totals = {key: 0 for key in ("total", "decided_reference", "reference_pass", "reference_fail", "uncertain_reference", "tp", "fp", "fn", "tn")}
    display_names = {
        "Contextual/indirect Auditor tests": "Contextual / indirect tests",
        "Direct questions": "Direct questions",
        "Fixed templates": "Fixed templates",
    }
    for method in a_reference["methods"]:
        counts = method["counts"]
        row = {
            "label": display_names.get(method["method"], method["method"]),
            "answers": counts["total"],
            "resolved": counts["decided_reference"],
            "passes": counts["reference_pass"],
            "failures": counts["reference_fail"],
            "uncertain": counts["uncertain_reference"],
            "confusion": {"tp": counts["tp"], "fp": 0, "fn": 0, "tn": counts["tn"]},
        }
        per_method.append(row)
        for key in a_totals:
            a_totals[key] += counts.get(key, 0)

    adopted = a_chat["counts_per_reviewer"]
    assert adopted == {"pass": 3, "fail": 27, "uncertain": 6}
    assert (a_execution["completed_answers"], a_execution["histories"], a_execution["conditions"], a_execution["questions_per_condition"]) == (36, 3, 9, 4)
    assert (a_totals["total"], a_totals["decided_reference"], a_totals["reference_pass"], a_totals["reference_fail"], a_totals["uncertain_reference"]) == (36, 30, 3, 27, 6)

    a = {
        "answers": a_execution["completed_answers"],
        "histories": a_execution["histories"],
        "methods": a_execution["conditions"] // a_execution["histories"],
        "questions_per_method_per_history": a_execution["questions_per_condition"],
        "conditions": a_execution["conditions"],
        "execution_verified": a_execution["verified_request_body_hashes"] == a_execution["completed_answers"]
        and a_execution["target_and_evaluation_settings_match"] and a_execution["equal_budgets_and_realised_call_attempts"],
        "retrospective_review": {
            "resolved": a_totals["decided_reference"],
            "total": a_totals["total"],
            "passes": a_totals["reference_pass"],
            "failures": a_totals["reference_fail"],
            "uncertain": a_totals["uncertain_reference"],
            "confusion_vs_adopted_references": {
                "tp": a_totals["tp"], "fp": a_totals["fp"],
                "fn": a_totals["fn"], "tn": a_totals["tn"],
                "decided_total": a_totals["tp"] + a_totals["fp"] + a_totals["fn"] + a_totals["tn"],
            },
            "per_method": per_method,
            "review_process": a_reference["scope"],
            "review_authorship": a_reference["reference_authorship"],
            "formal_status": a_reference["formal_status"],
        },
        "formal_failure_discovery_rate": a_reference["formal_failure_discovery_rate"],
        "formal_failure_detection_recall": a_reference["formal_failure_detection_recall"],
        "unresolved_items": len(a_open["remaining_ambiguous_answers"]),
        "independent_blind_gold": False,
        "automatic_initial_counts": a_ai["automatic_counts"],
        "limitations": [
            "The retrospective labels were AI-assisted after exposure to automatic results and later adopted through chat; they are not independent blind gold.",
            "Six of 36 responses remain uncertain because the prompt/reference alignment is ambiguous.",
            "Formal distinct-failure discovery and failure-detection recall remain unmeasured; explicit defect-to-inventory mapping is incomplete.",
        ],
    }

    # B is the canonical 72-answer collection. Its primary score is the
    # unweighted macro mean across four dimensions, not a pooled answer rate.
    b_source = analysis["B"]
    b_policies = []
    dimension_labels = {
        "accuracy": "Accuracy", "freshness": "Freshness",
        "conflict_resolution": "Conflict resolution", "appropriate_use": "Appropriate use",
    }
    schedule_per_dimension = b_source["distinct_synthetic_histories"] * len(b_source["repetitions"])
    for policy_id, label in POLICIES:
        summary = b_source["policies"][policy_id]
        dimensions = []
        for dimension, values in summary["dimensions"].items():
            dimensions.append({
                "category": dimension_labels.get(dimension, dimension),
                "correct": values["pass"],
                "decided": values["total"],
                "scheduled": schedule_per_dimension,
                "uncertain": schedule_per_dimension - values["total"],
                "accuracy_percent": accuracy(values["pass"], values["total"]),
            })
        repeated = []
        for repetition in sorted(b_source["repetitions"], key=int):
            item = b_source["repetitions"][repetition][policy_id]
            repeated.append({
                "repetition": int(repetition),
                "macro_accuracy_percent": item["macro_percentage"],
                "passes": item["pass"], "failures": item["fail"], "uncertain": item["uncertain"],
                "dimension_scores": [
                    {"category": dimension_labels.get(dimension, dimension), "correct": result["pass"],
                     "decided": result["total"], "accuracy_percent": accuracy(result["pass"], result["total"])}
                    for dimension, result in item["dimensions"].items()
                ],
            })
        b_policies.append({
            "id": policy_id,
            "label": label,
            "canonical_answers": 36,
            "macro_accuracy_percent": summary["macro_percentage"],
            "population_sd_pp": summary["macro_population_stddev_across_repetitions"],
            "passes": summary["pass"], "failures": summary["fail"], "uncertain": summary["uncertain"],
            "dimensions": dimensions,
            "per_repetition": repeated,
        })
    paired_deltas = b_source["paired_history_macro_deltas_pp"]
    b = {
        "canonical_answers": b_source["answers"],
        "histories": b_source["distinct_synthetic_histories"],
        "policies": b_policies,
        "repetitions": len(b_source["repetitions"]),
        "answers_per_policy": 36,
        "answers_per_history_policy_repeat": 4,
        "score_definition": "Unweighted macro average of pass rates over Accuracy, Freshness, Conflict resolution and Appropriate use; each dimension denominator is the decided verdict count shown.",
        "paired_history_macro_deltas_pp": paired_deltas,
        "paired_mean_delta_pp": b_source["paired_mean_delta_pp"],
        "history_bootstrap_interval_pp": b_source["descriptive_history_bootstrap_95_interval_pp"],
        "exact_two_sided_sign_p": b_source["exact_two_sided_history_sign_p"],
        "independent_human_results_received": b_live["independent_human_results_received"],
        "protocol_sha256": b_live["protocol_sha256"],
        "limitations": [
            "Three synthetic histories share an authored scenario structure; repeats are correlated and are not independent population cases.",
            "The automated rule judgements do not have independent human calibration.",
            "One Relationship-priority result was uncertain; dimension denominators exclude undecided judgements.",
        ],
    }
    assert b["canonical_answers"] == 72 and abs(b["paired_mean_delta_pp"] - 72.2222222222) < 0.001

    # Keep the archived B/C rank-direction check separate from the newer v5/v6
    # LongMemEval collections: those collections use different frozen runner
    # snapshots and are not cross-metric agreement evidence.
    c_source = analysis["C"]
    archived_policies = []
    for policy_id, label in POLICIES:
        values = c_source["overall_policies"][policy_id]
        repeated = [
            {"repetition": int(rep), "correct": row[policy_id]["pass"], "total": row[policy_id]["total"],
             "accuracy_percent": row[policy_id]["percentage"]}
            for rep, row in sorted(c_source["repetitions"].items(), key=lambda item: int(item[0]))
        ]
        categories = [
            {"category": category, "correct": entry["pass"], "total": entry["total"],
             "accuracy_percent": accuracy(entry["pass"], entry["total"])}
            for category, entry in values["strata"].items()
        ]
        archived_policies.append({
            "id": policy_id, "label": label,
            "correct": values["pass"], "total": values["total"],
            "accuracy_percent": accuracy(values["pass"], values["total"]),
            "per_repetition": repeated, "categories": categories,
        })
    agreed = sum(1 for item in c_source["ranking_comparison"] if item["agreement"])

    def expanded_segment(segment: dict, name: str) -> dict:
        return {
            "case_count": segment["case_count"],
            "repetitions": segment["repetitions"],
            "policies": [
                {
                    "id": policy_id, "label": label,
                    "correct": segment["aggregate"][key]["correct"],
                    "total": segment["aggregate"][key]["total"],
                    "accuracy_percent": segment["aggregate"][key]["accuracy_percent"],
                    "per_repetition": [
                        {"repetition": row["repetition"], "correct": row[f"{key}_correct"],
                         "total": row["total"], "accuracy_percent": accuracy(row[f"{key}_correct"], row["total"])}
                        for row in segment["per_repetition"]
                    ],
                }
                for (policy_id, label), key in zip(POLICIES, ("weak", "strong"))
            ],
            "categories": [
                {
                    "category": row["category"], "case_count": row["case_count"],
                    "per_policy": [
                        {"id": policy_id, "label": label, "correct": row[key]["correct"],
                         "total": row[key]["total"], "accuracy_percent": row[key]["accuracy_percent"]}
                        for (policy_id, label), key in zip(POLICIES, ("weak", "strong"))
                    ],
                }
                for row in segment.get("category_results", [])
            ],
            "interpretation": segment.get("interpretation", name),
        }

    c = {
        "archived_compatibility": {
            "cases": 14, "available_cases": 500, "repetitions": 3,
            "target_answers": c_source["responses"], "usable_grades": c_source["usable_grades"],
            "policies": archived_policies,
            "b_c_ordering_agreement": {"agreed_repetitions": agreed, "total_repetitions": len(c_source["ranking_comparison"]),
                "scope": "Direction-of-ranking agreement only between B's dimension macro and this archived C subset; no absolute cross-dataset scores are compared."},
            "upstream_binding": c_live["upstream_binding"],
            "limitations": c_source["limitations"],
        },
        "expanded_v5_v6": {
            "source_revision": v6["source"]["revision"],
            "source_sha256": v6["source"]["source_sha256"],
            "v5": expanded_segment(v6["baseline_v5"], "Preserved v5 subset; separate collection."),
            "v6": expanded_segment(v6["extension_v6"], "New v6 extension; primary within-v6 comparison."),
            "v6_within_collection_repeat_wins": v6["decision"]["repeat_wins"],
            "v6_decision_rule": v6["decision"]["rule"],
            "v6_human_review": {"status": f"received; {review_agreed} agreed, {review_unresolved} unresolved",
                                "review_items": 180, "independent_histories": 30},
            "v6_operational_diagnostics": v6["extension_v6"]["operational_diagnostics"],
            "combined_secondary_summary": v6["combined"]["interpretation"],
            "cross_metric_agreement_claim": False,
            "limitations": [item for item in v6["limitations"] if "have not yet received independent human review" not in item] + [
                f"The user reports independent human review before automatic scores; original declarations conflict, and identities and procedures are not independently authenticated. {review_unresolved} answer judgments remain unresolved."],
        },
    }
    assert (c["archived_compatibility"]["cases"], c["archived_compatibility"]["available_cases"]) == (14, 500)
    assert [row["correct"] for row in c["archived_compatibility"]["policies"]] == [15, 30]
    assert agreed == 3
    assert [row["correct"] for row in c["expanded_v5_v6"]["v6"]["policies"]] == [19, 61]

    source_entries = [
        {"path": relative, "sha256": digest(ROOT / relative)} for relative in SOURCES
    ]
    script_relative = "scripts/publish_proposal_results_dashboard.py"
    return {
        "format": "proposal-final-results-dashboard-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_bundle": "artifacts/local/phase4-20261027",
        "source_revision": verification["runtime"]["git_commit"],
        "generator": {"path": script_relative, "sha256": digest(ROOT / script_relative), "version": "1"},
        "source_hashes": source_entries,
        "proposal_a": a,
        "proposal_b": b,
        "proposal_c": c,
    }


if __name__ == "__main__":
    report = publish()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Published {OUTPUT.relative_to(ROOT)} from {len(report['source_hashes'])} hash-recorded sources.")
