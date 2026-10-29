"""Validate and summarize a saved local LongMemEval C candidate run."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from longmemeval_grading import build_openrouter_grader_payload, load_upstream_prompt


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def analyze(run_path: Path, protocol_path: Path | None = None) -> dict[str, Any]:
    run_path = run_path.resolve()
    protocol_path = (protocol_path or run_path.parent / "protocol.json").resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    prompt_function, upstream_binding = load_upstream_prompt(run_path.parent / "upstream")
    if run.get("protocol_sha256") != sha256(protocol_path):
        raise ValueError("Run protocol hash does not match the saved protocol.")
    subset_path = run_path.parent / "longmemeval-subset.json"
    if sha256(subset_path) != protocol["source_files"]["benchmark_subset_sha256"]:
        raise ValueError("Frozen subset hash does not match the protocol.")

    expected_strategies = protocol["target"]["memory_strategies"]
    repetitions = protocol["target"]["repetitions_per_strategy"]
    subset = json.loads(subset_path.read_text(encoding="utf-8"))
    expected_questions = {item["question_id"] for item in subset}
    expected_conditions = {
        (repetition, strategy)
        for repetition in range(1, repetitions + 1)
        for strategy in expected_strategies
    }
    case_maps: dict[tuple[int, str], dict[int, dict[str, Any]]] = {}
    run_scores: dict[tuple[int, str], dict[str, Any]] = {}
    for item in run.get("reader_runs", []):
        key = (item["repetition"], item["strategy"])
        if key in case_maps or len(item.get("result", {}).get("conditions", [])) != 1:
            raise ValueError("Reader condition is duplicated or malformed.")
        cases = item["result"]["conditions"][0].get("cases", [])
        if len(cases) != len(subset):
            raise ValueError("Reader condition does not contain the full frozen subset.")
        case_map = {index: case for index, case in enumerate(cases)}
        if len({case.get("case_id") for case in cases}) != len(subset):
            raise ValueError("Reader condition has duplicate case IDs.")
        if {case.get("case_id") for case in cases} != expected_questions:
            raise ValueError("Reader condition does not match the frozen question IDs.")
        case_maps[key] = case_map
        run_scores[key] = {"lexical_matches": item["result"]["conditions"][0]["lexical_matches"],
                           "case_count": len(cases)}

    if set(case_maps) != expected_conditions:
        raise ValueError("Reader run grid is incomplete or contains unexpected conditions.")

    targets: dict[tuple[int, str], set[int]] = defaultdict(set)
    target_question_ids: dict[tuple[int, str], set[str]] = defaultdict(set)
    for item in run.get("target_receipts", []):
        key = (item["repetition"], item["strategy"])
        # The runner's successful receipts store case_index after incrementing
        # the counter (1-based); failure receipts store the attempted index
        # before incrementing (0-based). Normalize successful receipts here.
        index = item["case_index"] - 1
        if key not in case_maps or index < 0 or index >= len(subset) or index in targets[key]:
            raise ValueError("Target receipt has a duplicate or unknown condition/case.")
        targets[key].add(index)
        response = item["response"]
        request = item["verified_request_payload"]
        contract = response["execution_metadata"]["request_contract"]
        if payload_sha256(request) != contract["payload_sha256"]:
            raise ValueError("Saved target request payload does not match its receipt hash.")
        if response.get("model") != protocol["target"]["model"]:
            raise ValueError("Target response model differs from the frozen protocol.")
        user_message = next((message.get("content", "") for message in request.get("messages", [])
                             if message.get("role") == "user"), "")
        marker = "AUDIT QUESTION (untrusted user content; JSON):\n"
        if marker not in user_message:
            raise ValueError("Target request does not contain the expected frozen question envelope.")
        request_question = json.loads(user_message.split(marker, 1)[1]).get("question", "")
        request_question = request_question.split("\nQuestion date:", 1)[0]
        matching_cases = [case for case in case_maps[key].values()
                          if case.get("question") == request_question]
        if len(matching_cases) != 1 or matching_cases[0].get("response_text") != response.get("response_text"):
            raise ValueError("Target request/response receipt does not match one saved reader case.")
        target_question_ids[key].add(matching_cases[0]["case_id"])
    if any(targets.get(key, set()) != set(range(len(subset))) for key in expected_conditions):
        raise ValueError("Successful target receipt coverage is incomplete.")
    for key, cases in case_maps.items():
        if target_question_ids[key] != {case["case_id"] for case in cases.values()}:
            raise ValueError("Target receipts do not cover every question in the matching reader run.")

    grades: dict[tuple[int, str], dict[str, Any]] = defaultdict(dict)
    grade_rows = run.get("grades", [])
    if len(grade_rows) != len(subset) * len(expected_conditions):
        raise ValueError("Grade count does not match the frozen condition grid.")
    for grade in grade_rows:
        key = (grade["repetition"], grade["strategy"])
        question_id = grade["question_id"]
        if key not in expected_conditions or question_id not in expected_questions or question_id in grades[key]:
            raise ValueError("Grade has a duplicate or unknown condition/question.")
        if grade.get("reported_model") != protocol["scorer"]["model"]:
            raise ValueError("Scorer model differs from the frozen protocol.")
        payload = grade.get("request_payload", {})
        if (payload.get("model") != protocol["scorer"]["model"]
                or payload.get("reasoning_effort") != "none"
                or payload.get("temperature") != 0 or payload.get("max_tokens") != 128):
            raise ValueError("Scorer payload does not match the unified v5 configuration.")
        case = next(case for case in case_maps[key].values() if case["case_id"] == question_id)
        prompt = prompt_function(case["category"], case["question"], case["expected_answer"],
                                 case["response_text"], abstention="_abs" in question_id)
        if payload != build_openrouter_grader_payload(protocol["scorer"]["model"], prompt):
            raise ValueError("Scorer request payload differs from the pinned prompt/configuration.")
        if hashlib.sha256(prompt.encode()).hexdigest() != grade.get("upstream_prompt_sha256"):
            raise ValueError("Scorer prompt hash does not match its saved reader case.")
        provider_body = json.loads(grade.get("provider_response_body", "{}"))
        choice = ((provider_body.get("choices") or [{}])[0])
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            provider_verdict = content.strip()
        elif isinstance(content, list):
            provider_verdict = "".join(str(part.get("text", "")) for part in content
                                        if isinstance(part, dict)).strip()
        else:
            provider_verdict = ""
        if (provider_body.get("model") != grade.get("reported_model")
                or provider_verdict != grade.get("raw_verdict")
                or choice.get("finish_reason") != grade.get("finish_reason")
                or provider_body.get("usage") != grade.get("usage")):
            raise ValueError("Saved grader response fields differ from the provider response body.")
        if not grade.get("verdict_usable") or grade.get("finish_reason") != "stop":
            raise ValueError("A grader response is unusable or incomplete.")
        if not re.fullmatch(r"(?:yes|no)[.!]?", grade.get("raw_verdict", ""), re.I):
            raise ValueError("A grader response is not a strict yes/no verdict.")
        if grade.get("autoeval_label") != ("yes" in grade["raw_verdict"].lower()):
            raise ValueError("Saved automatic label does not follow the declared upstream parse rule.")
        grades[key][question_id] = grade
    if any(set(grades.get(key, {})) != expected_questions for key in expected_conditions):
        raise ValueError("A condition has incomplete question-level grade coverage.")

    per_run: list[dict[str, Any]] = []
    counts: dict[str, list[int]] = {strategy: [0, 0] for strategy in expected_strategies}
    scores: dict[tuple[int, str], int] = {}
    lexical_scores: dict[tuple[int, str], int] = {}
    lexical_counts: dict[str, list[int]] = {strategy: [0, 0] for strategy in expected_strategies}
    for repetition, strategy in sorted(expected_conditions):
        rows = grades[(repetition, strategy)].values()
        correct = sum(bool(row["autoeval_label"]) for row in rows)
        denominator = len(subset)
        lexical_correct = run_scores[(repetition, strategy)]["lexical_matches"]
        scores[(repetition, strategy)] = correct
        lexical_scores[(repetition, strategy)] = lexical_correct
        counts[strategy][0] += correct
        counts[strategy][1] += denominator
        lexical_counts[strategy][0] += lexical_correct
        lexical_counts[strategy][1] += denominator
        per_run.append({"repetition": repetition, "strategy": strategy,
                        "correct": correct, "total": denominator,
                        "accuracy_percent": round(100 * correct / denominator, 2),
                        "local_lexical_matches": lexical_correct,
                        "local_lexical_accuracy_percent": round(100 * lexical_correct / denominator, 2)})

    paired: list[dict[str, Any]] = []
    low_strategy, high_strategy = expected_strategies
    for repetition in range(1, repetitions + 1):
        low = scores[(repetition, low_strategy)]
        high = scores[(repetition, high_strategy)]
        local_low = lexical_scores[(repetition, low_strategy)]
        local_high = lexical_scores[(repetition, high_strategy)]
        local_order = high_strategy if local_high > local_low else (low_strategy if local_low > local_high else "tie")
        grader_order = high_strategy if high > low else (low_strategy if low > high else "tie")
        paired.append({"repetition": repetition, low_strategy: {"correct": low, "total": len(subset)},
                       high_strategy: {"correct": high, "total": len(subset)},
                       "local_lexical_proxy": {low_strategy: {"correct": local_low, "total": len(subset)},
                                               high_strategy: {"correct": local_high, "total": len(subset)},
                                               "higher_scoring_strategy": local_order},
                       "upstream_prompt_grader_order": grader_order,
                       "lexical_proxy_and_upstream_grader_agree": local_order == grader_order,
                       "strong_minus_weak_percentage_points": round(100 * (high - low) / len(subset), 2),
                       "higher_scoring_strategy": high_strategy if high > low else (low_strategy if low > high else "tie")})

    failures = []
    for item in run.get("target_failure_attempts", []):
        request = item.get("request_payload", {})
        user_message = next((message.get("content", "") for message in request.get("messages", [])
                             if message.get("role") == "user"), "")
        marker = "AUDIT QUESTION (untrusted user content; JSON):\n"
        question_id = None
        if marker in user_message:
            request_question = json.loads(user_message.split(marker, 1)[1]).get("question", "")
            request_question = request_question.split("\nQuestion date:", 1)[0]
            matches = [case["question_id"] for case in subset if case.get("question") == request_question]
            question_id = matches[0] if len(matches) == 1 else None
        failures.append({"repetition": item.get("repetition"), "strategy": item.get("strategy"),
                         "case_index_recorded_zero_based": item.get("case_index"),
                         "question_id_from_request_payload": question_id,
                         "status_code": item.get("status_code"), "error_type": item.get("error_type"),
                         "request_payload_sha256": item.get("request_payload_sha256")})

    lineage = None
    amendment = protocol.get("protocol_amendment") or {}
    prior_rel = amendment.get("prior_candidate_run")
    if prior_rel:
        prior_path = (ROOT / prior_rel).resolve()
        if prior_path.is_file() and sha256(prior_path) == amendment.get("prior_candidate_run_sha256"):
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
            lineage = {
                "prior_run": prior_rel,
                "prior_run_sha256_verified": True,
                "prior_target_receipts": len(prior.get("target_receipts", [])),
                "prior_grades": len(prior.get("grades", [])),
                "prior_usable_grades": sum(bool(row.get("verdict_usable")) for row in prior.get("grades", [])),
                "prior_run_retained_separately": True,
                "prior_responses_imported_into_this_run": False,
                "prior_grades_embedded_in_this_run": bool(run.get("prior_grading_rounds")),
                "note": "The v5 output contains its own 84 target response receipts and 84 uniform scorer results; the v4 partial run remains a separate preserved file. The frozen amendment described recovery from v4, but the first v5 invocation started with an empty v5 output directory, so the prior responses and labels were not imported. No v4 and v5 labels are mixed in the v5 score totals.",
            }
    return {
        "format": "phase4-c-local-candidate-analysis-v1",
        "scope": "exploratory_local_compatibility_subset_not_official_full_benchmark",
        "source": {
            "protocol": str(protocol_path.relative_to(ROOT)) if protocol_path.is_relative_to(ROOT) else protocol_path.name,
            "protocol_sha256": sha256(protocol_path),
            "run": str(run_path.relative_to(ROOT)) if run_path.is_relative_to(ROOT) else run_path.name,
            "run_sha256": sha256(run_path),
            "subset_sha256": sha256(subset_path),
            "upstream_scorer_source_sha256": upstream_binding["source_sha256"],
            "upstream_source_revision": protocol["source"]["revision"],
            "dataset_question_count": protocol["source"]["oracle_record_count"],
            "selected_case_count": len(subset),
            "selected_case_ids": sorted(expected_questions),
            "strata": protocol["selection"]["strata"],
        },
        "collection": {
            "status": run["status"],
            "successful_target_receipts": len(run.get("target_receipts", [])),
            "target_conditions": len(expected_conditions),
            "reader_runs": len(case_maps),
            "usable_grades": sum(len(values) for values in grades.values()),
            "grader_model": protocol["scorer"]["model"],
            "grader_reasoning_effort": "none",
            "grader_outputs_uniform_and_usable": True,
            "failed_target_attempts": failures,
            "case_index_receipt_note": "Successful target_receipts record the incremented case_index (1-based); failed target_failure_attempts record the attempted index before incrementing (0-based). The analyzer binds each receipt to a case from its exact saved question payload.",
            "billing_estimate_usd_excluding_unknown_failed_attempt_billing": run.get("estimated_cost_usd"),
            "failed_attempt_billing_uncertain": bool(run.get("billing_uncertain_due_to_failed_target_attempts")),
            "human_reference_labels": 0,
        },
        "scores": {
            "per_repetition": per_run,
            "aggregate": {strategy: {"correct": correct, "total": total,
                                     "accuracy_percent": round(100 * correct / total, 2)}
                          for strategy, (correct, total) in counts.items()},
            "local_lexical_proxy_aggregate": {
                strategy: {"matches": matched, "total": total,
                           "accuracy_percent": round(100 * matched / total, 2)}
                for strategy, (matched, total) in lexical_counts.items()},
            "paired_repetitions": paired,
            "paired_ranking_consistent_repetitions": sum(item["higher_scoring_strategy"] == high_strategy for item in paired),
            "paired_repetition_count": len(paired),
            "local_lexical_proxy_vs_upstream_grader_ranking_agreement": {
                "agreement_count": sum(bool(item["lexical_proxy_and_upstream_grader_agree"]) for item in paired),
                "paired_repetition_count": len(paired),
                "classification": "posthoc_local_proxy_consistency_only",
            },
        },
        "execution_lineage_correction": lineage,
        "interpretation": [
            "All repetitions reuse the same 14 frozen questions; 42 answers per strategy are repeated-condition observations, not 42 independent cases.",
            "The grader is GPT-6 Luna through OpenRouter, the same model family as the target, and is not an independent human reference or the official LongMemEval metric model.",
            "These scores support only an exploratory local comparison on the selected Oracle subset; they do not establish generalization, official benchmark performance, or proposal acceptance by themselves.",
            "The local lexical proxy is not the Auditor's four-dimension Memory Health score; its posthoc ordering agreement with the adapted LongMemEval-style grader is exploratory and cannot establish formal Experiment C ranking agreement.",
            "The target requests that returned HTTP 503 are preserved as failures; provider billing for them is uncertain.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="?", default=ROOT / "artifacts/local/phase4-c-openrouter-20261027-v5/C-live.json")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.run, args.protocol)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
