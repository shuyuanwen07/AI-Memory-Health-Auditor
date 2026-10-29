"""Validate and summarize only the separately frozen v6 Phase 4 C expansion."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from run_phase4_c_expansion import (
    EXPECTED_CASE_COUNT,
    EXPECTED_MODEL,
    EXPECTED_PROVIDER,
    EXPECTED_REPETITIONS,
    EXPECTED_STRATEGIES,
    FrozenInputError,
    _case_category,
    _case_id,
    _iter_batches,
    _read_json,
    _safe_root_path,
    canonical_json_sha256,
    sha256_bytes,
    validate_frozen_inputs,
)


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 4) if denominator else None


def _mean_median(values: list[float | int | None]) -> dict[str, Any]:
    observed = [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(float(value))]
    return {
        "n_with_value": len(observed),
        "mean": round(mean(observed), 4) if observed else None,
        "median": round(median(observed), 4) if observed else None,
    }


def _load_analysis_helpers(inputs: dict[str, Any], dependencies: dict[str, Any] | None):
    if dependencies is not None:
        return dependencies["load_prompt"], dependencies["build_grader_payload"], dependencies["request_contract_sha256"]
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
        raise FrozenInputError(f"Malformed {label} identity in the v6 collection.")
    return int(repetition), str(strategy), qid


def validate_and_analyze(inputs: dict[str, Any], run: dict[str, Any],
                         dependencies: dict[str, Any] | None = None) -> dict[str, Any]:
    protocol = inputs["protocol"]
    if run.get("format") != "proposal-c-expansion-live-run-v1":
        raise FrozenInputError("The run file is not a v6 C expansion collection.")
    for key, expected in (("protocol_id", protocol["id"]), ("protocol_sha256", inputs["protocol_sha256"]),
                          ("subset_sha256", inputs["subset_sha256"])):
        if run.get(key) != expected:
            raise FrozenInputError(f"The v6 run receipt is not bound to the frozen {key}.")
    if run.get("target_configuration", {}).get("case_count") != EXPECTED_CASE_COUNT:
        raise FrozenInputError("The run receipt does not declare the complete 30-case target set.")
    target_config = run.get("target_configuration", {})
    if (target_config.get("provider") != EXPECTED_PROVIDER or target_config.get("model") != EXPECTED_MODEL
            or target_config.get("strategies") != EXPECTED_STRATEGIES
            or target_config.get("repetitions") != EXPECTED_REPETITIONS):
        raise FrozenInputError("The run receipt target matrix differs from the frozen provider/model/strategy/repetition matrix.")
    if (run.get("source_manifest_sha256") != protocol["source"]["source_manifest_sha256"]
            or run.get("oracle_source_sha256") != protocol["source"]["oracle_source_sha256"]
            or run.get("source_revision") != protocol["source"]["revision"]
            or run.get("upstream_binding") != inputs["upstream_binding"]):
        raise FrozenInputError("The run receipt source or upstream-scorer bindings differ from the frozen v6 protocol.")
    ceiling = run.get("max_cost_usd")
    estimated_cost = run.get("estimated_cost_usd")
    if (not isinstance(ceiling, (int, float)) or not math.isfinite(float(ceiling))
            or ceiling <= 0 or ceiling > min(1.0, float(protocol["budget"]["max_estimated_cost_usd"])) + 1e-12):
        raise FrozenInputError("The v6 run receipt has an invalid or raised USD cost ceiling.")
    if (not isinstance(estimated_cost, (int, float)) or not math.isfinite(float(estimated_cost))
            or estimated_cost < 0):
        raise FrozenInputError("The v6 run receipt has an invalid estimated cost total.")
    usage_cost_estimate = run.get("usage_based_cost_estimate_usd")
    if (not isinstance(usage_cost_estimate, (int, float))
            or not math.isfinite(float(usage_cost_estimate)) or usage_cost_estimate < 0):
        raise FrozenInputError("The v6 run receipt has an invalid token-usage-based cost estimate.")

    load_prompt, build_grader_payload, request_contract_sha256 = _load_analysis_helpers(inputs, dependencies)
    prompt_function, binding = load_prompt(inputs["directory"] / "upstream")
    if binding != inputs["upstream_binding"]:
        raise FrozenInputError("The upstream grader binding changed after the v6 freeze.")

    subset_by_id = {_case_id(case): case for case in inputs["subset"]}
    target_intent_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    for intent in run.get("target_call_intents", []):
        key = _identity(intent, "target call intent")
        if key in target_intent_by_key or key[2] not in subset_by_id:
            raise FrozenInputError("The target-call journal contains a duplicate or out-of-subset identity.")
        target_intent_by_key[key] = intent
    target_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    for receipt in run.get("target_receipts", []):
        key = _identity(receipt, "target receipt")
        if key in target_by_key or key[2] not in subset_by_id:
            raise FrozenInputError("The target collection has a duplicate or out-of-subset answer receipt.")
        if key[0] not in range(1, EXPECTED_REPETITIONS + 1) or key[1] not in EXPECTED_STRATEGIES:
            raise FrozenInputError("A target receipt lies outside the frozen strategy/repetition matrix.")
        response = receipt.get("response") or {}
        if response.get("model") != EXPECTED_MODEL:
            raise FrozenInputError("A target response was produced by a model other than the frozen GPT-6 Luna target.")
        payload = receipt.get("verified_request_payload")
        if not isinstance(payload, dict) or payload.get("model") != EXPECTED_MODEL:
            raise FrozenInputError("A target receipt is missing its exact frozen OpenRouter payload.")
        if request_contract_sha256(payload) != receipt.get("request_payload_sha256"):
            raise FrozenInputError("A target request payload does not match its receipt hash.")
        intent = target_intent_by_key.get(key)
        if intent is None or intent.get("request_payload_sha256") != receipt.get("request_payload_sha256"):
            raise FrozenInputError("A target response has no matching saved dispatch intent.")
        metadata = (response.get("execution_metadata") or {})
        contract = metadata.get("request_contract") or {}
        if contract.get("payload_sha256") and contract["payload_sha256"] != receipt["request_payload_sha256"]:
            raise FrozenInputError("The response request-contract hash does not match the saved target payload.")
        contract_attempts = receipt.get("request_contract_attempts", [])
        intent_attempts = intent.get("attempts", [])
        if len(contract_attempts) != len(intent_attempts):
            raise FrozenInputError("The saved target request attempts do not reconcile with the dispatch journal.")
        for contract_attempt, intent_attempt in zip(contract_attempts, intent_attempts):
            contract_digest = contract_attempt.get("request_contract_sha256")
            if (contract_attempt.get("attempt_index") != intent_attempt.get("attempt_index")
                    or contract_digest != intent_attempt.get("request_contract_sha256")):
                raise FrozenInputError("A target request attempt differs between the connector receipt and dispatch journal.")
        text = response.get("response_text")
        if not isinstance(text, str):
            raise FrozenInputError("A saved target receipt has no answer text.")
        response_hash = sha256_bytes(text.encode("utf-8"))
        if receipt.get("response_sha256") != response_hash or intent.get("response_sha256") != response_hash:
            raise FrozenInputError("The target answer does not match both its receipt and dispatch journal hashes.")
        if intent.get("status") != "completed":
            raise FrozenInputError("A target answer is present without a completed dispatch journal entry.")
        target_by_key[key] = receipt

    reader_case_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    reader_run_keys: set[tuple[int, str, int]] = set()
    for reader_run in run.get("reader_runs", []):
        repetition, strategy, batch_index = reader_run.get("repetition"), reader_run.get("strategy"), reader_run.get("batch_index")
        if repetition not in range(1, EXPECTED_REPETITIONS + 1) or strategy not in EXPECTED_STRATEGIES or batch_index not in (0, 1):
            raise FrozenInputError("A saved reader-run batch has an invalid repetition, strategy, or batch index.")
        run_key = (int(repetition), str(strategy), int(batch_index))
        if run_key in reader_run_keys:
            raise FrozenInputError("A reader-run batch is duplicated.")
        reader_run_keys.add(run_key)
        expected_ids = [_case_id(record) for record in _iter_batches(inputs["subset"], protocol["selection"]["batch_size"])[batch_index][1]]
        if reader_run.get("question_ids") != expected_ids:
            raise FrozenInputError("A saved reader-run batch does not match the frozen 15-case order.")
        result = reader_run.get("result") or {}
        if result.get("provider") != EXPECTED_PROVIDER or result.get("model") != EXPECTED_MODEL:
            raise FrozenInputError("A reader batch has a different provider or model from the v6 freeze.")
        conditions = result.get("conditions", [])
        if len(conditions) != 1 or conditions[0].get("strategy") != strategy:
            raise FrozenInputError("A reader batch does not contain exactly its frozen strategy.")
        cases = conditions[0].get("cases", [])
        if [case.get("case_id") for case in cases] != expected_ids:
            raise FrozenInputError("A reader batch contains missing, extra, or reordered case results.")
        for case_result in cases:
            qid = case_result["case_id"]
            key = (int(repetition), str(strategy), qid)
            if key in reader_case_by_key:
                raise FrozenInputError("A target case appears more than once in the reader batches.")
            receipt = target_by_key.get(key)
            if receipt is None or receipt["response"].get("response_text") != case_result.get("response_text"):
                raise FrozenInputError("The reader display answer does not reconcile to its saved target response.")
            reader_case_by_key[key] = case_result

    grade_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    for grade in run.get("grades", []):
        key = _identity(grade, "grader receipt")
        if key in grade_by_key or key[2] not in subset_by_id:
            raise FrozenInputError("The grader collection has a duplicate or out-of-subset receipt.")
        target = target_by_key.get(key)
        if target is None:
            raise FrozenInputError("A grader receipt has no matching target answer.")
        target_text = target["response"]["response_text"]
        if grade.get("target_response_sha256") != sha256_bytes(target_text.encode("utf-8")):
            raise FrozenInputError("A grader receipt is bound to a different target answer.")
        record = subset_by_id[key[2]]
        case_result = reader_case_by_key.get(key)
        if case_result is None:
            raise FrozenInputError("A grader receipt has no completed reader case record.")
        prompt = prompt_function(case_result.get("category", _case_category(record)), record["question"], record["answer"],
                                 target_text, abstention=key[2].endswith("_abs"))
        if grade.get("upstream_prompt_sha256") != sha256_bytes(prompt.encode("utf-8")):
            raise FrozenInputError("The grade prompt does not match the pinned upstream prompt and saved answer.")
        expected_payload = build_grader_payload(protocol["C"]["judge_model"], prompt)
        if grade.get("request_payload") != expected_payload or grade.get("request_payload_sha256") != canonical_json_sha256(expected_payload):
            raise FrozenInputError("The grader request payload does not match the frozen upstream-prompt request.")
        if grade.get("reported_model") not in (None, protocol["C"]["judge_model"]):
            raise FrozenInputError("A saved grade names a different grader model.")
        if grade.get("verdict_usable"):
            raw = str(grade.get("raw_verdict", "")).strip().casefold()
            expected_correct = raw.startswith("yes") if raw in {"yes", "yes.", "no", "no."} else None
            if expected_correct is None or grade.get("correct") is not expected_correct:
                raise FrozenInputError("A usable grade does not reconcile to the strict yes/no parser.")
        grade_by_key[key] = grade

    target_intents = run.get("target_call_intents", [])
    target_attempts = [attempt for intent in target_intents for attempt in intent.get("attempts", [])]
    grader_attempts = [attempt for grade in run.get("grades", []) for attempt in grade.get("attempts", [])]
    target_failed = [attempt for attempt in target_attempts if attempt.get("status") == "transport_error" or
                     isinstance(attempt.get("http_status"), int) and attempt["http_status"] >= 400]
    grader_failed = [attempt for attempt in grader_attempts if attempt.get("status") in {"unknown", "provider_error_saved"} or
                     isinstance(attempt.get("http_status"), int) and attempt["http_status"] >= 400]
    target_uncertain = [attempt for attempt in target_attempts if attempt.get("status") in {"pending", "transport_error"}]
    grader_uncertain = [attempt for attempt in grader_attempts if attempt.get("status") in {"pending", "unknown"}]

    per_repetition: list[dict[str, Any]] = []
    by_strategy: dict[str, dict[str, Any]] = {}
    category_results: dict[str, dict[str, Any]] = {}
    lexical_by_strategy: dict[str, dict[str, Any]] = {}
    latency_by_strategy: dict[str, dict[str, Any]] = {}
    token_by_strategy: dict[str, dict[str, Any]] = {}
    repetition_results: dict[int, dict[str, dict[str, Any]]] = {}
    all_categories = sorted(set(_case_category(case) for case in inputs["subset"]))

    for strategy in EXPECTED_STRATEGIES:
        grade_correct = 0
        grade_decided = 0
        grade_uncertain = 0
        grade_missing = 0
        lexical_matches = 0
        lexical_observed = 0
        latencies: list[float] = []
        input_tokens: list[int] = []
        output_tokens: list[int] = []
        grader_input_tokens: list[int] = []
        grader_output_tokens: list[int] = []
        by_strategy[strategy] = {}
        lexical_by_strategy[strategy] = {}
        latency_by_strategy[strategy] = {}
        token_by_strategy[strategy] = {}
        category_results[strategy] = {}

        for category in all_categories:
            expected_in_category = sum(_case_category(case) == category for case in inputs["subset"]) * EXPECTED_REPETITIONS
            category_grade_keys = [key for key in grade_by_key if key[1] == strategy and _case_category(subset_by_id[key[2]]) == category]
            correct = sum(grade_by_key[key].get("verdict_usable") and grade_by_key[key].get("correct") is True for key in category_grade_keys)
            decided = sum(bool(grade_by_key[key].get("verdict_usable")) for key in category_grade_keys)
            category_results[strategy][category] = {
                "correct": int(correct),
                "decided": int(decided),
                "uncertain": sum(not grade_by_key[key].get("verdict_usable") for key in category_grade_keys),
                "missing": max(0, expected_in_category - len(category_grade_keys)),
                "expected": expected_in_category,
                "strict_accuracy_percent": _pct(int(correct), expected_in_category),
                "decided_accuracy_percent": _pct(int(correct), int(decided)),
            }

        for repetition in range(1, EXPECTED_REPETITIONS + 1):
            expected_keys = [(repetition, strategy, _case_id(case)) for case in inputs["subset"]]
            grades = [grade_by_key[key] for key in expected_keys if key in grade_by_key]
            correct = sum(bool(grade.get("verdict_usable") and grade.get("correct") is True) for grade in grades)
            decided = sum(bool(grade.get("verdict_usable")) for grade in grades)
            uncertain = sum(not grade.get("verdict_usable") for grade in grades)
            missing = EXPECTED_CASE_COUNT - len(grades)
            rep_latencies = [
                reader_case_by_key[key].get("execution_metadata", {}).get("latency_ms")
                for key in expected_keys if key in reader_case_by_key
            ]
            rep_tokens_in = [target_by_key[key].get("input_tokens") for key in expected_keys if key in target_by_key]
            rep_tokens_out = [target_by_key[key].get("output_tokens") for key in expected_keys if key in target_by_key]
            rep_grader_tokens_in = [
                (grade_by_key[key].get("usage") or {}).get("prompt_tokens",
                 (grade_by_key[key].get("usage") or {}).get("input_tokens"))
                for key in expected_keys if key in grade_by_key
            ]
            rep_grader_tokens_out = [
                (grade_by_key[key].get("usage") or {}).get("completion_tokens",
                 (grade_by_key[key].get("usage") or {}).get("output_tokens"))
                for key in expected_keys if key in grade_by_key
            ]
            rep_lexical = [reader_case_by_key[key].get("lexical_match") for key in expected_keys
                           if key in reader_case_by_key and isinstance(reader_case_by_key[key].get("lexical_match"), bool)]
            rep_result = {
                "strategy": strategy,
                "repetition": repetition,
                "correct": int(correct),
                "decided": int(decided),
                "uncertain": int(uncertain),
                "missing": int(missing),
                "expected": EXPECTED_CASE_COUNT,
                "strict_accuracy_percent": _pct(int(correct), EXPECTED_CASE_COUNT),
                "decided_accuracy_percent": _pct(int(correct), int(decided)),
                "lexical_proxy": {
                    "matches": sum(v is True for v in rep_lexical),
                    "observed": len(rep_lexical),
                    "expected": EXPECTED_CASE_COUNT,
                    "accuracy_percent": _pct(sum(v is True for v in rep_lexical), len(rep_lexical)),
                },
                "target_latency_ms": _mean_median(rep_latencies),
                "target_tokens": {
                    "input_observed": len([v for v in rep_tokens_in if isinstance(v, (int, float))]),
                    "input_sum": sum(v for v in rep_tokens_in if isinstance(v, (int, float))) if rep_tokens_in else None,
                    "output_observed": len([v for v in rep_tokens_out if isinstance(v, (int, float))]),
                    "output_sum": sum(v for v in rep_tokens_out if isinstance(v, (int, float))) if rep_tokens_out else None,
                },
                "grader_tokens": {
                    "input_observed": len([v for v in rep_grader_tokens_in if isinstance(v, (int, float))]),
                    "input_sum": sum(v for v in rep_grader_tokens_in if isinstance(v, (int, float))) if rep_grader_tokens_in else None,
                    "output_observed": len([v for v in rep_grader_tokens_out if isinstance(v, (int, float))]),
                    "output_sum": sum(v for v in rep_grader_tokens_out if isinstance(v, (int, float))) if rep_grader_tokens_out else None,
                },
            }
            repetition_results.setdefault(repetition, {})[strategy] = rep_result
            per_repetition.append(rep_result)
            grade_correct += correct
            grade_decided += decided
            grade_uncertain += uncertain
            grade_missing += missing
            lexical_matches += sum(v is True for v in rep_lexical)
            lexical_observed += len(rep_lexical)
            latencies.extend([float(v) for v in rep_latencies if isinstance(v, (int, float))])
            input_tokens.extend([int(v) for v in rep_tokens_in if isinstance(v, int)])
            output_tokens.extend([int(v) for v in rep_tokens_out if isinstance(v, int)])
            grader_input_tokens.extend([int(v) for v in rep_grader_tokens_in if isinstance(v, int)])
            grader_output_tokens.extend([int(v) for v in rep_grader_tokens_out if isinstance(v, int)])

        by_strategy[strategy] = {
            "correct": int(grade_correct),
            "decided": int(grade_decided),
            "uncertain": int(grade_uncertain),
            "missing": int(grade_missing),
            "expected": EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS,
            "strict_accuracy_percent": _pct(int(grade_correct), EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS),
            "decided_accuracy_percent": _pct(int(grade_correct), int(grade_decided)),
        }
        lexical_by_strategy[strategy] = {
            "matches": lexical_matches,
            "observed": lexical_observed,
            "expected": EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS,
            "accuracy_percent": _pct(lexical_matches, lexical_observed),
        }
        latency_by_strategy[strategy] = _mean_median(latencies)
        token_by_strategy[strategy] = {
            "input_observed": len(input_tokens), "input_sum": sum(input_tokens) if input_tokens else None,
            "output_observed": len(output_tokens), "output_sum": sum(output_tokens) if output_tokens else None,
            "grader_input_observed": len(grader_input_tokens),
            "grader_input_sum": sum(grader_input_tokens) if grader_input_tokens else None,
            "grader_output_observed": len(grader_output_tokens),
            "grader_output_sum": sum(grader_output_tokens) if grader_output_tokens else None,
        }

    paired_repetitions = []
    strong_rep_wins = 0
    for repetition in range(1, EXPECTED_REPETITIONS + 1):
        weak = repetition_results[repetition]["weak_first_hit"]
        strong = repetition_results[repetition]["strong_rule_based"]
        if strong["correct"] > weak["correct"]:
            winner = "strong_rule_based"
            strong_rep_wins += 1
        elif strong["correct"] < weak["correct"]:
            winner = "weak_first_hit"
        else:
            winner = "tie"
        both = strong_only = weak_only = neither = unresolved_pair = 0
        for case in inputs["subset"]:
            qid = _case_id(case)
            wk = (repetition, "weak_first_hit", qid)
            sk = (repetition, "strong_rule_based", qid)
            wg, sg = grade_by_key.get(wk), grade_by_key.get(sk)
            if not wg or not sg or not wg.get("verdict_usable") or not sg.get("verdict_usable"):
                unresolved_pair += 1
            elif wg.get("correct") and sg.get("correct"):
                both += 1
            elif sg.get("correct"):
                strong_only += 1
            elif wg.get("correct"):
                weak_only += 1
            else:
                neither += 1
        paired_repetitions.append({
            "repetition": repetition,
            "weak_correct": weak["correct"],
            "strong_correct": strong["correct"],
            "weak_strict_accuracy_percent": weak["strict_accuracy_percent"],
            "strong_strict_accuracy_percent": strong["strict_accuracy_percent"],
            "strong_minus_weak_percentage_points": round(strong["strict_accuracy_percent"] - weak["strict_accuracy_percent"], 4),
            "paired_case_outcomes": {"both_correct": both, "strong_only_correct": strong_only,
                                      "weak_only_correct": weak_only, "neither_correct": neither,
                                      "unresolved": unresolved_pair},
            "repetition_winner": winner,
        })

    observed_reader_cases = len(reader_case_by_key)
    expected_reader_cases = EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS * len(EXPECTED_STRATEGIES)
    observed_grades = len(grade_by_key)
    expected_grades = EXPECTED_CASE_COUNT * EXPECTED_REPETITIONS * len(EXPECTED_STRATEGIES)
    pooled_strong = by_strategy["strong_rule_based"]["strict_accuracy_percent"]
    pooled_weak = by_strategy["weak_first_hit"]["strict_accuracy_percent"]
    all_grades_usable = observed_grades == expected_grades and all(
        bool(grade.get("verdict_usable")) for grade in grade_by_key.values()
    )
    collection_complete = (
        run.get("status") == "complete_automatic_collection"
        and len(target_by_key) == expected_reader_cases
        and observed_reader_cases == expected_reader_cases
        and all(intent.get("status") == "completed" for intent in target_intents)
        and all_grades_usable
    )
    strong_recommended = (
        collection_complete
        and pooled_strong is not None and pooled_weak is not None
        and pooled_strong > pooled_weak and strong_rep_wins >= 2
    )
    winner_decision = "strong_rule_based" if strong_recommended else "no_clear_winner"
    latency_tradeoff = {
        strategy: latency_by_strategy[strategy] for strategy in EXPECTED_STRATEGIES
    }
    tokens_tradeoff = {strategy: token_by_strategy[strategy] for strategy in EXPECTED_STRATEGIES}

    analysis = {
        "format": "proposal-c-expansion-analysis-v1",
        "scope": "v6_expansion_only; primary decision excludes all v5 observations",
        "protocol_id": protocol["id"],
        "protocol_sha256": inputs["protocol_sha256"],
        "subset_sha256": inputs["subset_sha256"],
        "preserved_v5_binding": protocol["selection"]["excluded_prior_release"],
        "upstream_source_revision": protocol["source"]["revision"],
        "primary_outcome": protocol["analysis"]["primary_outcome"],
        "predeclared_winner_rule": protocol["analysis"]["selection_rule"],
        "selected_case_count": EXPECTED_CASE_COUNT,
        "selected_category_counts": dict(sorted(Counter(_case_category(case) for case in inputs["subset"]).items())),
        "collection_status": run.get("status"),
        "scores": {
            "per_repetition": per_repetition,
            "paired_repetitions": paired_repetitions,
            "pooled": by_strategy,
            "category_level": category_results,
            "lexical_proxy_separate": lexical_by_strategy,
        },
        "operational_tradeoffs": {
            "target_latency_ms_mean_and_median": latency_tradeoff,
            "target_token_usage": tokens_tradeoff,
            "provider_request_failures": {
                "target_failed_attempts": len(target_failed),
                "target_uncertain_attempts": len(target_uncertain),
                "grader_failed_attempts": len(grader_failed),
                "grader_uncertain_attempts": len(grader_uncertain),
                "target_intents_unresolved": sum(intent.get("status") != "completed" for intent in target_intents),
                "grader_records_unusable_or_unresolved": sum(not bool(g.get("verdict_usable")) for g in grade_by_key.values()),
                "target_answers_expected": 180,
                "target_answers_saved": len(target_by_key),
                "target_answers_missing": 180 - len(target_by_key),
                "grader_answers_expected": 180,
                "grader_records_saved": observed_grades,
                "usable_grader_decisions": sum(bool(g.get("verdict_usable")) for g in grade_by_key.values()),
                "uncertain_or_unusable_grades": sum(not bool(g.get("verdict_usable")) for g in grade_by_key.values()),
                "missing_grades": 180 - observed_grades,
                "billing_uncertain": bool(run.get("billing_uncertain")),
            },
            "cost": {
                "estimated_usd": run.get("estimated_cost_usd"),
                "usage_based_estimate_usd": run.get("usage_based_cost_estimate_usd"),
                "rate_assumptions_usd_per_token": run.get("cost_rate_assumptions_usd_per_token"),
                "ceiling_usd": run.get("max_cost_usd"),
                "limit_reached": run.get("status") == "paused_cost_ceiling",
                "cost_estimate_note": "The usage-based estimate multiplies reported token counts by the frozen rate assumptions; the reserved estimate includes unknown or failed attempts. Neither is an invoice; provider billing is not independently verified.",
            },
        },
        "decision": {
            "recommended_strategy": winner_decision,
            "collection_complete_for_predeclared_rule": collection_complete,
            "strong_wins_of_three_repetition_comparisons": strong_rep_wins,
            "pooled_strong_accuracy_higher": pooled_strong is not None and pooled_weak is not None and pooled_strong > pooled_weak,
            "rule_passed": strong_recommended,
            "tradeoff_summary": (
                f"Strong is recommended under the predeclared rule; latency and token-use summaries remain separate diagnostics."
                if strong_recommended else
                ("The v6 collection is incomplete; the predeclared winner rule cannot be applied. Report no clear winner."
                 if not collection_complete else
                 "The predeclared Strong rule was not fully satisfied; report no clear winner. Latency, token use, and lexical proxy are separate diagnostics.")
            ),
        },
        "coverage": {
            "complete_for_predeclared_rule": collection_complete,
            "expected_reader_case_records": expected_reader_cases,
            "reader_case_records_saved": observed_reader_cases,
            "expected_grader_records": expected_grades,
            "grader_records_saved": observed_grades,
        },
        "limitations": list(run.get("compatibility_limitations", [])) + [
            "The GPT-6 Luna grader's pass rate is not an official LongMemEval score.",
            "Automatic grader outputs have zero independent human labels in this collection.",
            "Thirty new cases are not guaranteed to be statistically independent; category and shared-session clustering remain relevant.",
            "The predeclared rule selects a preferred policy for this local v6 collection only and does not establish AC1, AC3, or population-level generalisation.",
        ],
    }
    return analysis


def build_comparison_summary(root: Path, v6_analysis: dict[str, Any], v5_analysis_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    v5_binding = v6_analysis.get("preserved_v5_binding") or {}
    bound_analysis_path = _safe_root_path(root, v5_binding.get("prior_v5_analysis_path", ""), "preserved v5 analysis")
    v5_path = v5_analysis_path or bound_analysis_path
    v5 = _read_json(v5_path)
    scores = v5.get("scores", {})
    v5_repetitions = scores.get("per_repetition", [])
    v5_pooled = scores.get("aggregate", {})
    v5_protocol_path = _safe_root_path(root, v5_binding.get("prior_v5_protocol_path", ""), "preserved v5 protocol")
    v5_protocol = _read_json(v5_protocol_path)
    v5_source = v5.get("source", {})
    if sha256_bytes(v5_path.read_bytes()) != v5_binding.get("prior_v5_analysis_sha256"):
        raise FrozenInputError("The v5 analysis used for the 44-case secondary summary is not the analysis frozen by v6.")
    if v5_source.get("run_sha256") != v5_binding.get("prior_v5_analysis_source_run_sha256"):
        raise FrozenInputError("The v5 analysis source run hash differs from the v6-frozen analysis binding.")
    bound_run = _safe_root_path(root, v5_binding.get("prior_v5_run_path", ""), "preserved v5 run")
    bound_subset = _safe_root_path(root, v5_binding.get("prior_v5_subset_path", ""), "preserved v5 subset")
    if (sha256_bytes(v5_protocol_path.read_bytes()) != v5_binding.get("prior_v5_protocol_sha256")
            or sha256_bytes(bound_subset.read_bytes()) != v5_binding.get("prior_v5_subset_sha256")
            or v5_protocol.get("source_files", {}).get("benchmark_subset_sha256") != v5_binding.get("prior_v5_subset_sha256")):
        raise FrozenInputError("The v5 protocol or subset used for comparison is not the source frozen by v6.")
    if (v5_binding.get("prior_v5_analysis_source_run_sha256") != v5_binding.get("prior_v5_run_sha256")
            or sha256_bytes(bound_run.read_bytes()) != v5_binding.get("prior_v5_run_sha256")):
        raise FrozenInputError("The v5 analysis source run hash differs from the preserved v5 C-live.json hash.")
    if (v5_source.get("protocol_sha256") != v5_binding.get("prior_v5_protocol_sha256")
            or v5_source.get("subset_sha256") != v5_binding.get("prior_v5_subset_sha256")):
        raise FrozenInputError("The v5 analysis is not tied to the v5 protocol and subset frozen by v6.")
    v6_pooled = v6_analysis["scores"]["pooled"]
    v5_counts = {
        "weak_first_hit": {"correct": v5_pooled.get("weak_first_hit", {}).get("correct"),
                            "total": v5_pooled.get("weak_first_hit", {}).get("total"),
                            "accuracy_percent": v5_pooled.get("weak_first_hit", {}).get("accuracy_percent")},
        "strong_rule_based": {"correct": v5_pooled.get("strong_rule_based", {}).get("correct"),
                              "total": v5_pooled.get("strong_rule_based", {}).get("total"),
                              "accuracy_percent": v5_pooled.get("strong_rule_based", {}).get("accuracy_percent")},
    }
    if (v5_counts["weak_first_hit"]["correct"], v5_counts["weak_first_hit"]["total"],
            v5_counts["strong_rule_based"]["correct"], v5_counts["strong_rule_based"]["total"]) != (12, 42, 35, 42):
        raise FrozenInputError("The preserved v5 reference analysis differs from its known 12/42 and 35/42 upstream-grader totals.")
    v5_by_rep: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in v5_repetitions:
        v5_by_rep[int(row["repetition"])][row["strategy"]] = row
    v6_by_rep = {row["repetition"]: row for row in v6_analysis["scores"]["paired_repetitions"]}
    combined_per_rep = []
    for repetition in range(1, EXPECTED_REPETITIONS + 1):
        v6_pair = v6_by_rep[repetition]
        record = {"repetition": repetition}
        for strategy in EXPECTED_STRATEGIES:
            old = v5_by_rep[repetition][strategy]
            v6_row = next(row for row in v6_analysis["scores"]["per_repetition"]
                          if row["repetition"] == repetition and row["strategy"] == strategy)
            correct = int(old["correct"]) + int(v6_row["correct"])
            total = 14 + EXPECTED_CASE_COUNT
            record[strategy] = {"correct": correct, "total": total, "accuracy_percent": _pct(correct, total)}
        record["strong_minus_weak_percentage_points"] = round(
            record["strong_rule_based"]["accuracy_percent"] - record["weak_first_hit"]["accuracy_percent"], 4)
        record["winner"] = "strong_rule_based" if record["strong_minus_weak_percentage_points"] > 0 else \
                            "weak_first_hit" if record["strong_minus_weak_percentage_points"] < 0 else "tie"
        combined_per_rep.append(record)
    combined_pooled = {}
    for strategy in EXPECTED_STRATEGIES:
        correct = v5_counts[strategy]["correct"] + v6_pooled[strategy]["correct"]
        total = int(v5_counts[strategy]["total"]) + int(v6_pooled[strategy]["expected"])
        combined_pooled[strategy] = {"correct": correct, "total": total, "accuracy_percent": _pct(correct, total)}

    v5_app_source = v5_protocol.get("app_source", {})
    v6_protocol = v6_analysis["protocol_id"]
    v6_source_digest_map = v6_analysis.get("source_code_sha256", {})
    shared_source_paths = set(v5_app_source) & set(v6_source_digest_map)
    changed_paths = sorted(path for path in shared_source_paths
                           if v5_app_source[path] != v6_source_digest_map[path])
    v5_only_paths = sorted(set(v5_app_source) - set(v6_source_digest_map))
    v6_only_paths = sorted(set(v6_source_digest_map) - set(v5_app_source))
    same_dataset_revision = (v5_source.get("upstream_source_revision") == v6_analysis.get("upstream_source_revision"))
    return {
        "format": "proposal-c-expansion-v5-v6-comparison-v1",
        "scope": "secondary descriptive comparison; does not alter the v6 predeclared winner rule",
        "v5": {
            "protocol_id": v5_protocol.get("id"),
            "analysis_sha256": sha256_bytes(v5_path.read_bytes()),
            "collection_period": "2026-10-27",
            "case_count_per_repetition": 14,
            "pooled_upstream_prompt_scores": v5_counts,
            "estimated_cost_usd_excluding_uncertain_failed_attempts": v5["collection"].get("billing_estimate_usd_excluding_unknown_failed_attempt_billing"),
            "billing_uncertain": v5["collection"].get("failed_attempt_billing_uncertain"),
        },
        "v6": {
            "protocol_id": v6_protocol,
            "analysis_sha256": v6_analysis.get("analysis_sha256"),
            "collection_period": "2026-10-28",
            "case_count_per_repetition": EXPECTED_CASE_COUNT,
            "pooled_upstream_prompt_scores": {
                strategy: {"correct": v6_pooled[strategy]["correct"], "total": v6_pooled[strategy]["expected"],
                          "accuracy_percent": v6_pooled[strategy]["strict_accuracy_percent"]}
                for strategy in EXPECTED_STRATEGIES
            },
            "predeclared_v6_decision": v6_analysis["decision"]["recommended_strategy"],
        },
        "combined_44_case_secondary": {
            "status": "descriptive_only",
            "cases_per_repetition": 44,
            "pooled_expected_answers_per_strategy": 132,
            "pooled_scores": combined_pooled,
            "per_repetition": combined_per_rep,
            "same_pinned_longmemeval_source_revision": same_dataset_revision,
            "v5_v6_application_runner_source_identical": not changed_paths,
            "changed_source_paths": changed_paths,
            "source_paths_only_in_v5_snapshot": v5_only_paths,
            "source_paths_only_in_v6_snapshot": v6_only_paths,
            "limitations": [
                "The v5 and v6 cohorts were collected on different days under different frozen source/runner snapshots; the 44-case total is secondary only.",
                "The cases share the same LongMemEval source collection and may share filler sessions/themes; combined rows are not guaranteed independent.",
                "The combined total is not used by the predeclared v6 selection rule and does not establish official benchmark performance or human-calibrated validity.",
            ],
        },
    }


def analyze_directory(root: Path, directory: Path, v5_analysis_path: Path | None = None,
                      dependencies: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    inputs = validate_frozen_inputs(root, directory)
    run_path = directory / "C-live.json"
    if not run_path.is_file():
        raise FileNotFoundError("The v6 C-live.json collection does not exist yet.")
    run = _read_json(run_path)
    analysis = validate_and_analyze(inputs, run, dependencies)
    analysis["source_code_sha256"] = inputs["protocol"].get("app_source", {})
    summary = build_comparison_summary(inputs["root"], analysis, v5_analysis_path)
    analysis_path = directory / "analysis.json"
    summary_path = directory / "comparison-summary.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    analysis_sha = sha256_bytes(analysis_path.read_bytes())
    (directory / "analysis.sha256").write_text(analysis_sha + "  analysis.json\n", encoding="utf-8")
    summary["v6"]["analysis_sha256"] = analysis_sha
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return analysis, summary


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--v5-analysis", type=Path, default=None)
    args = parser.parse_args()
    directory = args.directory if args.directory.is_absolute() else args.root / args.directory
    analysis, summary = analyze_directory(args.root, directory, args.v5_analysis)
    print(json.dumps({
        "status": analysis["collection_status"],
        "v6_recommendation": analysis["decision"]["recommended_strategy"],
        "v6_weak": analysis["scores"]["pooled"]["weak_first_hit"]["strict_accuracy_percent"],
        "v6_strong": analysis["scores"]["pooled"]["strong_rule_based"]["strict_accuracy_percent"],
        "combined_44_case_status": summary["combined_44_case_secondary"]["status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    _main()
