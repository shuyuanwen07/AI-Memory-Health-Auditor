"""Analyze the frozen v7 four-strategy same-history replay without model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from run_phase4_c_four_arm_v7 import (
    EXPECTED_CASE_COUNT,
    EXPECTED_MODEL,
    EXPECTED_ORDER_BY_REPETITION,
    EXPECTED_PROVIDER,
    EXPECTED_REPETITIONS,
    EXPECTED_STRATEGIES,
    FrozenInputError,
    _case_category,
    _case_id,
    _read_json,
    _safe_root_path,
    canonical_json_sha256,
    sha256_bytes,
    sha256_file,
    validate_frozen_inputs,
)


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 4) if denominator else None


def _summary(values: list[Any]) -> dict[str, Any]:
    clean = [float(value) for value in values if isinstance(value, (int, float))
             and math.isfinite(float(value))]
    return {"n": len(clean), "mean": round(mean(clean), 4) if clean else None,
            "median": round(median(clean), 4) if clean else None}


def _load_helpers(inputs: dict[str, Any], dependencies: dict[str, Any] | None):
    if dependencies is not None:
        return (dependencies["load_prompt"], dependencies["build_grader_payload"],
                dependencies["request_contract_sha256"])
    backend = str(inputs["root"] / "backend")
    scripts = str(inputs["root"] / "scripts")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from app.target_ai.request_contracts import request_contract_sha256
    from longmemeval_grading import build_openrouter_grader_payload, load_upstream_prompt
    return load_upstream_prompt, build_openrouter_grader_payload, request_contract_sha256


def _identity(row: dict[str, Any], label: str) -> tuple[int, str, str]:
    repetition, strategy, qid = row.get("repetition"), row.get("strategy"), row.get("question_id")
    if repetition not in range(1, EXPECTED_REPETITIONS + 1) or strategy not in EXPECTED_STRATEGIES or not isinstance(qid, str):
        raise FrozenInputError(f"Malformed {label} identity in the v7 collection.")
    return int(repetition), str(strategy), qid


def _pair_summary(left: str, right: str, repetition: int,
                  grades: dict[tuple[int, str, str], dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    both = left_only = right_only = neither = unresolved = 0
    for case in cases:
        qid = _case_id(case)
        a, b = grades.get((repetition, left, qid)), grades.get((repetition, right, qid))
        if not a or not b or not a.get("verdict_usable") or not b.get("verdict_usable"):
            unresolved += 1
        elif a.get("correct") and b.get("correct"):
            both += 1
        elif a.get("correct"):
            left_only += 1
        elif b.get("correct"):
            right_only += 1
        else:
            neither += 1
    return {"left_strategy": left, "right_strategy": right, "repetition": repetition,
            "both_correct": both, "left_only_correct": left_only, "right_only_correct": right_only,
            "neither_correct": neither, "unresolved": unresolved,
            "paired_cases": both + left_only + right_only + neither + unresolved}


def _verify_pacing_sessions(run: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    sessions = run.get("pacing_sessions", [])
    all_starts = []
    session_reports = []
    min_interval = float(protocol["execution"]["openrouter_minimum_start_to_start_seconds"])
    cooldown = float(protocol["execution"]["initial_cooldown_seconds"])
    seen_session_ids = set()
    for session in sessions:
        if not isinstance(session.get("session_id"), str) or session["session_id"] in seen_session_ids:
            raise FrozenInputError("A pacing session has a missing or duplicate session ID.")
        seen_session_ids.add(session["session_id"])
        starts = session.get("request_starts_utc", [])
        try:
            started = datetime.fromisoformat(session["started_at_utc"])
            parsed = [datetime.fromisoformat(value) for value in starts]
        except (KeyError, TypeError, ValueError) as exc:
            raise FrozenInputError("A saved pacing session has malformed UTC timestamps.") from exc
        if any((parsed[i] - parsed[i - 1]).total_seconds() < min_interval - 0.001
               for i in range(1, len(parsed))):
            raise FrozenInputError("Saved OpenRouter POST start times violate the frozen minimum spacing.")
        if parsed and (parsed[0] - started).total_seconds() < cooldown - 0.001:
            raise FrozenInputError("The first OpenRouter POST did not observe the frozen initial cooldown.")
        all_starts.extend(starts)
        session_reports.append({"session_id": session.get("session_id"),
                                "request_count": len(starts),
                                "first_dispatch_cooldown_seconds": round((parsed[0] - started).total_seconds(), 4) if parsed else None,
                                "minimum_observed_start_interval_seconds": round(min(
                                    ((parsed[i] - parsed[i - 1]).total_seconds() for i in range(1, len(parsed))),
                                    default=0.0), 4) if len(parsed) > 1 else None})
    if len(all_starts) != len(run.get("provider_dispatch_starts_utc", [])):
        raise FrozenInputError("The saved provider dispatch timestamps do not reconcile with pacing sessions.")
    return {"sessions": session_reports, "dispatch_count": len(all_starts),
            "minimum_interval_seconds": min_interval, "initial_cooldown_seconds": cooldown,
            "verified": bool(all_starts), "status": "verified" if all_starts else "no_provider_dispatches_recorded"}


def validate_and_analyze(inputs: dict[str, Any], run: dict[str, Any],
                         dependencies: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = inputs["protocol"]
    expected = EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS * len(EXPECTED_STRATEGIES)
    if run.get("format") != "proposal-c-four-arm-live-run-v1":
        raise FrozenInputError("The run file is not a v7 four-arm collection.")
    for key, value in (("protocol_id", protocol["id"]), ("protocol_sha256", inputs["protocol_sha256"]),
                       ("subset_sha256", inputs["subset_sha256"])):
        if run.get(key) != value:
            raise FrozenInputError(f"The v7 run receipt is not bound to frozen {key}.")
    target_config = run.get("target_configuration", {})
    if (target_config.get("provider") != EXPECTED_PROVIDER or target_config.get("model") != EXPECTED_MODEL
            or target_config.get("strategies") != EXPECTED_STRATEGIES
            or target_config.get("repetitions") != EXPECTED_REPETITIONS
            or target_config.get("case_count") != EXPECTED_CASE_COUNT):
        raise FrozenInputError("The v7 run target matrix differs from the frozen four-arm design.")
    if (run.get("source_manifest_sha256") != protocol["source"]["source_manifest_sha256"]
            or run.get("oracle_source_sha256") != protocol["source"]["oracle_source_sha256"]
            or run.get("source_revision") != protocol["source"]["revision"]
            or run.get("upstream_binding") != inputs["upstream_binding"]):
        raise FrozenInputError("The v7 run source or scorer binding differs from the frozen protocol.")
    cap, estimate = run.get("max_cost_usd"), run.get("estimated_cost_usd")
    if (not isinstance(cap, (int, float)) or cap <= 0 or cap > 0.40 + 1e-12
            or not isinstance(estimate, (int, float)) or not math.isfinite(float(estimate)) or estimate < 0):
        raise FrozenInputError("The v7 run has an invalid USD cost ledger or exceeds its hard ceiling.")
    usage_estimate = run.get("usage_based_cost_estimate_usd")
    if not isinstance(usage_estimate, (int, float)) or not math.isfinite(float(usage_estimate)) or usage_estimate < 0:
        raise FrozenInputError("The v7 run has an invalid usage-based cost estimate.")

    load_prompt, build_grader_payload, request_hash = _load_helpers(inputs, dependencies)
    prompt_function, binding = load_prompt(inputs["directory"] / "upstream")
    if binding != inputs["upstream_binding"]:
        raise FrozenInputError("The pinned scorer prompt binding changed after the v7 freeze.")
    subset_by_id = {_case_id(row): row for row in inputs["subset"]}
    if len(subset_by_id) != EXPECTED_CASE_COUNT:
        raise FrozenInputError("The v7 subset question IDs are not unique.")

    reader_cases: dict[tuple[int, str, str], dict[str, Any]] = {}
    reader_runs_seen = set()
    for row in run.get("reader_runs", []):
        rep, strategy, batch = row.get("repetition"), row.get("strategy"), row.get("batch_index")
        run_key = (rep, strategy, batch)
        if (rep not in range(1, 4) or strategy not in EXPECTED_STRATEGIES or batch not in (0, 1)
                or run_key in reader_runs_seen):
            raise FrozenInputError("A saved v7 reader batch has an invalid or duplicate identity.")
        reader_runs_seen.add(run_key)
        condition_list = (row.get("result") or {}).get("conditions", [])
        if len(condition_list) != 1:
            raise FrozenInputError("Each saved v7 batch must contain exactly one strategy condition.")
        for case_result in condition_list[0].get("cases", []):
            qid = case_result.get("case_id")
            key = (rep, strategy, qid)
            if qid not in subset_by_id or key in reader_cases:
                raise FrozenInputError("A v7 reader result is duplicate or outside the frozen subset.")
            if not isinstance(case_result.get("response_text"), str):
                raise FrozenInputError("A v7 reader result has no response text.")
            reader_cases[key] = case_result

    intents = {}
    for intent in run.get("target_call_intents", []):
        key = _identity(intent, "target call intent")
        if key[2] not in subset_by_id or key in intents:
            raise FrozenInputError("The v7 target-call journal has a duplicate or out-of-subset identity.")
        intents[key] = intent
    targets = {}
    for receipt in run.get("target_receipts", []):
        key = _identity(receipt, "target receipt")
        if key[2] not in subset_by_id or key in targets:
            raise FrozenInputError("The v7 target collection has a duplicate or out-of-subset identity.")
        response = receipt.get("response") or {}
        text = response.get("response_text")
        if response.get("model") != EXPECTED_MODEL or not isinstance(text, str):
            raise FrozenInputError("A v7 target response is missing or names a different model.")
        if receipt.get("response_sha256") != sha256_bytes(text.encode("utf-8")):
            raise FrozenInputError("A v7 target answer hash does not match its saved text.")
        if reader_cases.get(key, {}).get("response_text") != text:
            raise FrozenInputError("A target receipt does not match the corresponding saved reader output.")
        payload = receipt.get("verified_request_payload")
        intent = intents.get(key)
        if (not isinstance(payload, dict) or payload.get("model") != EXPECTED_MODEL
                or request_hash(payload) != receipt.get("request_payload_sha256")
                or intent is None or intent.get("status") != "completed"
                or intent.get("request_payload_sha256") != receipt.get("request_payload_sha256")
                or intent.get("response_sha256") != receipt.get("response_sha256")):
            raise FrozenInputError("A v7 target receipt does not reconcile with its exact dispatch intent and request hash.")
        attempts = receipt.get("request_contract_attempts", [])
        journal_attempts = intent.get("attempts", [])
        if len(attempts) != len(journal_attempts):
            raise FrozenInputError("Target request attempts do not reconcile between connector and journal.")
        for saved, journal in zip(attempts, journal_attempts):
            if (saved.get("attempt_index") != journal.get("attempt_index")
                    or saved.get("request_contract_sha256") != journal.get("request_contract_sha256")):
                raise FrozenInputError("A target request attempt differs between connector receipt and journal.")
        targets[key] = receipt

    grades = {}
    for grade in run.get("grades", []):
        key = _identity(grade, "grader result")
        if key[2] not in subset_by_id or key in grades:
            raise FrozenInputError("The v7 grader results have a duplicate or out-of-subset identity.")
        case = subset_by_id[key[2]]
        target_case = reader_cases.get(key)
        if target_case is not None:
            prompt = prompt_function(target_case.get("category", _case_category(case)), case["question"],
                                     case["answer"], target_case["response_text"], abstention=key[2].endswith("_abs"))
            if grade.get("upstream_prompt_sha256") != sha256_bytes(prompt.encode("utf-8")):
                raise FrozenInputError("The saved grade prompt does not match the pinned upstream scorer.")
            payload = build_grader_payload(protocol["scorer"]["model"], prompt)
            if (grade.get("request_payload") != payload
                    or grade.get("request_payload_sha256") != canonical_json_sha256(payload)):
                raise FrozenInputError("The saved grader payload differs from the pinned model, prompt, or settings.")
            if grade.get("target_response_sha256") != sha256_bytes(target_case["response_text"].encode("utf-8")):
                raise FrozenInputError("The grade is bound to a different target answer.")
        if grade.get("verdict_usable"):
            raw = str(grade.get("raw_verdict", "")).strip().casefold()
            if raw not in {"yes", "yes.", "no", "no."} or grade.get("finish_reason") != "stop":
                raise FrozenInputError("A usable automatic grade does not satisfy the strict yes/no scoring rule.")
            if grade.get("correct") is not raw.startswith("yes"):
                raise FrozenInputError("A usable automatic grade does not match its strict parsed verdict.")
        elif grade.get("correct") is not None:
            raise FrozenInputError("An unusable automatic grade must not be counted as a pass or failure.")
        grades[key] = grade

    # Full expected matrix remains the denominator even when the cost cap pauses the collection.
    score_by_strategy = {}
    by_repetition = {}
    categories = sorted({_case_category(case) for case in inputs["subset"]})
    for strategy in EXPECTED_STRATEGIES:
        strategy_grades = [grades.get((rep, strategy, qid)) for rep in range(1, 4) for qid in subset_by_id]
        usable = [g for g in strategy_grades if g and g.get("verdict_usable")]
        correct = sum(g.get("correct") is True for g in usable)
        score_by_strategy[strategy] = {
            "correct": correct, "expected": EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS,
            "saved": sum(g is not None for g in strategy_grades), "usable": len(usable),
            "unresolved_or_missing": EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS - len(usable),
            "strict_pass_rate_percent": _pct(correct, EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS),
            "decided_only_pass_rate_percent": _pct(correct, len(usable)),
            "category_results": {},
            "repetitions": [],
        }
        for category in categories:
            qids = [_case_id(case) for case in inputs["subset"] if _case_category(case) == category]
            expected_cat = len(qids) * EXPECTED_REPETITIONS
            cat_grades = [grades.get((rep, strategy, qid)) for rep in range(1, 4) for qid in qids]
            cat_usable = [g for g in cat_grades if g and g.get("verdict_usable")]
            cat_correct = sum(g.get("correct") is True for g in cat_usable)
            score_by_strategy[strategy]["category_results"][category] = {
                "correct": cat_correct, "expected": expected_cat,
                "usable": len(cat_usable), "strict_pass_rate_percent": _pct(cat_correct, expected_cat),
            }
        for rep in range(1, 4):
            rep_rows = [grades.get((rep, strategy, qid)) for qid in subset_by_id]
            rep_usable = [g for g in rep_rows if g and g.get("verdict_usable")]
            rep_correct = sum(g.get("correct") is True for g in rep_usable)
            rep_record = {"repetition": rep, "strategy": strategy, "correct": rep_correct,
                          "expected": EXPECTED_CASE_COUNT, "usable": len(rep_usable),
                          "unresolved_or_missing": EXPECTED_CASE_COUNT - len(rep_usable),
                          "strict_pass_rate_percent": _pct(rep_correct, EXPECTED_CASE_COUNT)}
            score_by_strategy[strategy]["repetitions"].append(rep_record)
            by_repetition[(rep, strategy)] = rep_record

    all_pairs = []
    wins = {strategy: {other: 0 for other in EXPECTED_STRATEGIES if other != strategy}
            for strategy in EXPECTED_STRATEGIES}
    for i, left in enumerate(EXPECTED_STRATEGIES):
        for right in EXPECTED_STRATEGIES[i + 1:]:
            for rep in range(1, 4):
                lhs, rhs = by_repetition[(rep, left)], by_repetition[(rep, right)]
                if lhs["correct"] > rhs["correct"]:
                    wins[left][right] += 1
                elif rhs["correct"] > lhs["correct"]:
                    wins[right][left] += 1
                record = _pair_summary(left, right, rep, grades, inputs["subset"])
                record["left_correct"] = lhs["correct"]
                record["right_correct"] = rhs["correct"]
                record["left_strict_pass_rate_percent"] = lhs["strict_pass_rate_percent"]
                record["right_strict_pass_rate_percent"] = rhs["strict_pass_rate_percent"]
                all_pairs.append(record)

    target_expected = expected
    target_count = len(targets)
    grade_count = len(grades)
    usable_grade_count = sum(bool(g.get("verdict_usable")) for g in grades.values())
    ceiling_respected = float(estimate) <= min(float(cap), 0.40) + 1e-12
    complete = (ceiling_respected and run.get("status") == "complete_automatic_collection" and target_count == target_expected
                and len(reader_cases) == target_expected and grade_count == target_expected
                and usable_grade_count == target_expected
                and len(intents) == target_expected and all(i.get("status") == "completed" for i in intents.values()))
    highest = max((row["correct"] for row in score_by_strategy.values()), default=-1)
    leaders = [strategy for strategy, row in score_by_strategy.items() if row["correct"] == highest]
    candidate = leaders[0] if len(leaders) == 1 else None
    winner = candidate if candidate and all(wins[candidate][other] >= 2 for other in EXPECTED_STRATEGIES if other != candidate) else None
    recommendation = winner if complete else None
    pacing = _verify_pacing_sessions(run, protocol)
    v6_binding = protocol["selection"]["v6_lineage"]
    analysis = {
        "format": "proposal-c-four-arm-analysis-v1",
        "scope": "exploratory_same_v6_30_histories; do not generalize as independent sample",
        "protocol_id": protocol["id"], "protocol_sha256": inputs["protocol_sha256"],
        "subset_sha256": inputs["subset_sha256"], "v6_lineage": v6_binding,
        "collection_status": run.get("status"), "selected_case_count": EXPECTED_CASE_COUNT,
        "selected_category_counts": dict(Counter(_case_category(row) for row in inputs["subset"])),
        "scores": {"per_strategy": score_by_strategy, "all_pairwise_per_repetition": all_pairs,
                   "repetition_order": EXPECTED_ORDER_BY_REPETITION},
        "coverage": {"target_answers_expected": target_expected, "target_answers_saved": target_count,
                     "reader_case_records_saved": len(reader_cases), "grader_records_expected": expected,
                     "grader_records_saved": grade_count, "usable_grader_decisions": usable_grade_count,
                     "complete_for_winner_rule": complete},
        "decision": {"recommended_strategy": recommendation or "no_clear_winner",
                     "rule_applied_only_when_complete": True, "collection_complete": complete,
                     "unique_highest_candidate": candidate,
                     "repetition_wins_by_strategy": wins,
                     "required_wins_against_each_competitor": 2,
                     "rule_passed": bool(recommendation),
                     "selection_rule": protocol["analysis"]["selection_rule"]},
        "cost": {"estimated_usd": run.get("estimated_cost_usd"),
                 "usage_based_estimate_usd": run.get("usage_based_cost_estimate_usd"),
                 "ceiling_usd": run.get("max_cost_usd"),
                 "limit_reached": run.get("status") == "paused_cost_ceiling",
                 "ceiling_respected": ceiling_respected,
                 "billing_uncertain": bool(run.get("billing_uncertain")),
                 "rate_assumptions_usd_per_token": run.get("cost_rate_assumptions_usd_per_token")},
        "request_pacing": pacing,
        "limitations": list(run.get("compatibility_limitations", [])) + [
            "The v7 comparison replays prior v6 histories whose outcomes were already observed; it is exploratory and not independent confirmation.",
            "Three repetitions per case are repeated measurements, not additional histories.",
            "GPT-6 Luna supplies both target outputs and automatic scorer decisions; these are not independent human labels or an official benchmark score.",
            "Any incomplete collection or unusable automatic grade prevents a winner recommendation.",
            "A model winner on these local cases does not alone establish Auditor real-world value or correctness.",
        ],
    }
    summary = {
        "format": "proposal-c-four-arm-dashboard-v1", "protocol_id": protocol["id"],
        "protocol_sha256": inputs["protocol_sha256"], "v6_lineage": v6_binding,
        "scope": "exploratory; same previously observed v6 30 histories; GPT-6 Luna automatic grades, not human labels",
        "status": run.get("status"), "complete_for_decision": complete,
        "case_count": EXPECTED_CASE_COUNT, "repetitions": EXPECTED_REPETITIONS,
        "strategies": [{"strategy": name, **score_by_strategy[name]} for name in EXPECTED_STRATEGIES],
        "pairwise": all_pairs,
        "recommendation": recommendation or "no_clear_winner",
        "decision_rule": protocol["analysis"]["selection_rule"],
        "cost": analysis["cost"], "request_pacing": pacing,
        "caveat": "Repeated replay on the already-seen v6 histories is exploratory; automatic model grades do not count as independent human review.",
    }
    return analysis, summary


def analyze_directory(root: Path, directory: Path, dependencies: dict[str, Any] | None = None):
    inputs = validate_frozen_inputs(root, directory)
    run_path = inputs["directory"] / "C-live.json"
    if not run_path.is_file():
        raise FileNotFoundError("The v7 C-live.json collection does not exist yet.")
    run = _read_json(run_path)
    analysis, summary = validate_and_analyze(inputs, run, dependencies)
    analysis["source_code_sha256"] = inputs["protocol"].get("app_source", {})
    analysis_path = inputs["directory"] / "analysis.json"
    summary_path = inputs["directory"] / "four-arm-summary.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    analysis_sha = sha256_file(analysis_path)
    (inputs["directory"] / "analysis.sha256").write_text(analysis_sha + "  analysis.json\n", encoding="ascii")
    summary["analysis_sha256"] = analysis_sha
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return analysis, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory if args.directory.is_absolute() else args.root / args.directory
    analysis, summary = analyze_directory(args.root, directory)
    print(json.dumps({"collection_status": analysis["collection_status"],
                      "recommendation": summary["recommendation"],
                      "target_answers": analysis["coverage"]["target_answers_saved"],
                      "usable_grades": analysis["coverage"]["usable_grader_decisions"],
                      "analysis": str(directory / "analysis.json"),
                      "dashboard_summary": str(directory / "four-arm-summary.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
