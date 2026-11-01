"""Source-bound AC3 reference consensus and paired scorer analysis; no model calls.

The two MAX reference reviews are AI reviews, not independent human evidence.
Answer agreement and primary-error agreement are separate: uncertain error
types never remove an otherwise agreed pass/fail label from detection rates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "output/proposal-delivery/ac3-astra-max-retest-20261101-v2"
DIMENSIONS = ("accuracy", "freshness", "conflict_resolution", "appropriate_use")
EXPECTED_THRESHOLDS = {
    "failure_detection_recall_min": .8,
    "failure_classification_accuracy_min": .8,
    "test_validity_min": .9,
    "false_positive_rate_max": .1,
}
REVIEW_FILES = (
    ("review-max/reviewer-1/batch-1-80.review.json", "review-max/reviewer-1/batch-2-40.review.json"),
    ("review-max/reviewer-2/all-120.review.json",),
)
METRIC_DEFINITIONS = {
    "failure_recall_conservative": "TP / all agreed reference failures; automatic abstentions and request errors are missed failures.",
    "failure_recall_decided": "TP / (TP + decided FN); excludes automatic abstentions and request errors.",
    "decided_coverage": "Automatic pass/fail decisions / all agreed reference pass/fail answers.",
    "scheduled_decided_coverage": "Automatic pass/fail decisions on agreed references / all 120 frozen slots.",
    "false_positive_rate_decided": "FP / (FP + TN); reference-pass automatic abstentions are excluded and separately disclosed.",
    "false_positive_rate_lower_bound": "FP / all agreed reference passes; assumes no false-positive risk in abstentions.",
    "false_positive_rate_upper_bound": "(FP + all undecided reference passes) / all agreed reference passes.",
    "gold_primary_type_coverage": "Agreed single primary failure type / all agreed reference failures.",
    "classification_accuracy_detected_classifiable": "Correct primary types / detected failures with an agreed single reference type; missing automatic types remain in denominator.",
    "classification_accuracy_compared_types": "Correct / (correct + incorrect) primary types; excludes missing automatic types and nonclassifiable references.",
    "classification_accuracy_conservative_all_detected": "Verified correct primary types / all detected reference failures. Nonclassifiable reference types remain unverified, not known incorrect.",
    "joint_detection_and_classification_recall": "Verified correctly detected and typed failures / all agreed reference failures.",
    "automatic_type_coverage_all_failures": "Detected failures with an automatic primary type / all agreed reference failures, irrespective of reference-type agreement.",
}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def unique(items, key, label):
    result = {}
    for item in items:
        ident = item.get(key)
        if not isinstance(ident, str) or not ident or ident in result:
            raise ValueError(f"Missing/duplicate {key} in {label}: {ident}")
        result[ident] = item
    return result


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def validate_protocol(study):
    protocol = read(study / "protocol.json")
    if (protocol["thresholds"] != EXPECTED_THRESHOLDS
            or protocol["minimum_consensus_pass"] != 30
            or protocol["minimum_consensus_fail"] != 30
            or protocol["minimum_auto_coverage"] != .8
            or protocol["histories"] != 30 or protocol["questions"] != 120):
        raise ValueError("Frozen thresholds, class minima, coverage or sample size changed")
    if protocol["source_snapshot_sha256"] != sha(study / "sources.json"):
        raise ValueError("Source snapshot differs from frozen protocol")
    if (protocol["provider"], protocol["model"], protocol["reasoning_effort"]) != ("openai", "gpt-6-astra", "max"):
        raise ValueError("Target protocol is not OpenAI Astra MAX")
    scorer = protocol["scorer"]
    if (scorer["provider"], scorer["model"], scorer["reasoning_effort"],
            scorer["output_token_limit"], scorer["provider_attempts"]) != ("openai", "gpt-6-astra", "max", 8192, 1):
        raise ValueError("Scorer protocol is not the frozen Astra MAX single attempt")
    return protocol


def load_references(study, packet):
    expected = unique(packet["items"], "review_id", "blind packet")
    source_map = unique(packet["sources"], "source_handle", "blind packet sources")
    reviewers, declarations, manifest = [], [], {}
    for reviewer_index, paths in enumerate(REVIEW_FILES, 1):
        items, reviewer_declarations = [], []
        for relative in paths:
            path = study / relative
            data = read(path)
            manifest[relative] = sha(path)
            declaration = data["reviewer_declaration"]
            if (declaration.get("model") != "gpt-6-astra"
                    or declaration.get("reasoning_effort", declaration.get("effort")) != "max"
                    or declaration.get("completed_independently") is not True
                    or declaration.get("has_seen_other_reviewer_or_automatic_scores") is not False
                    or declaration.get("completed_by_human") is not False):
                raise ValueError(f"Unexpected AI reviewer declaration: {relative}")
            reviewer_declarations.append(declaration)
            for source in data["sources"]:
                if source_map.get(source["source_handle"]) != source:
                    raise ValueError(f"Reviewer source altered: {relative}")
            items.extend(data["items"])
        mapping = unique(items, "review_id", f"reviewer {reviewer_index}")
        if set(mapping) != set(expected):
            raise ValueError(f"Reviewer {reviewer_index} does not cover the exact 120 IDs")
        for ident, item in mapping.items():
            for field in ("source_handle", "question", "reference_behavior", "answer"):
                if item[field] != expected[ident][field]:
                    raise ValueError(f"Reviewer changed bound material: {ident}/{field}")
            if item.get("question_validity") not in {"valid", "invalid", "uncertain"}:
                raise ValueError(f"Invalid question validity: {ident}")
            if item.get("reference_validity") not in {"valid", "invalid", "uncertain"}:
                raise ValueError(f"Invalid reference validity: {ident}")
            if item.get("answer_verdict") not in {"pass", "fail", "uncertain"}:
                raise ValueError(f"Invalid answer verdict: {ident}")
            if item.get("failure_type_status") not in {"classified", "multiple", "uncertain", "not_applicable"}:
                raise ValueError(f"Invalid failure type status: {ident}")
            if item.get("failure_type") not in (*DIMENSIONS, None):
                raise ValueError(f"Invalid failure type: {ident}")
            if item["failure_type_status"] == "classified" and (
                    item["answer_verdict"] != "fail" or item["failure_type"] not in DIMENSIONS):
                raise ValueError(f"A classified type requires an actual failure: {ident}")
            if type(item.get("safe_but_incomplete")) is not bool:
                raise ValueError(f"Missing safe/incomplete flag: {ident}")
            source_ids = {m["message_id"] for m in source_map[item["source_handle"]]["messages"]}
            if not item.get("source_message_ids") or not set(item["source_message_ids"]) <= source_ids:
                raise ValueError(f"Reviewer evidence not bound to source: {ident}")
        reviewers.append(mapping)
        declarations.append({"reviewer": reviewer_index, "files": list(paths),
                             "declarations": reviewer_declarations})
    return reviewers, declarations, manifest


def combine_reference(first, second):
    question_valid = first["question_validity"] == second["question_validity"] == "valid"
    reference_valid = first["reference_validity"] == second["reference_validity"] == "valid"
    verdict = None
    if not (question_valid and reference_valid):
        status = "invalid_or_uncertain_question_or_reference"
    elif first["answer_verdict"] != second["answer_verdict"]:
        status = "answer_disagreement"
    elif first["answer_verdict"] == "uncertain":
        status = "answer_uncertain"
    else:
        verdict = first["answer_verdict"]
        status = "agreed_" + verdict
    gold_type = None
    if verdict != "fail":
        type_status = "not_applicable" if verdict == "pass" else "reference_answer_unresolved"
    elif (first["failure_type_status"] == second["failure_type_status"] == "classified"
          and first["failure_type"] == second["failure_type"]):
        gold_type, type_status = first["failure_type"], "agreed_single_primary_type"
    elif first["failure_type_status"] == second["failure_type_status"] == "classified":
        type_status = "primary_type_disagreement"
    elif "multiple" in (first["failure_type_status"], second["failure_type_status"]):
        type_status = "one_or_both_multiple"
    else:
        type_status = "one_or_both_uncertain"
    return {"question_agreed_valid": question_valid, "reference_agreed_valid": reference_valid,
            "answer_verdict": verdict, "answer_consensus_status": status,
            "primary_failure_type": gold_type, "primary_type_consensus_status": type_status,
            "safe_but_incomplete_agreed": first["safe_but_incomplete"] is second["safe_but_incomplete"],
            "safe_but_incomplete": first["safe_but_incomplete"] if first["safe_but_incomplete"] is second["safe_but_incomplete"] else None}


def normalize_prediction(record, *, candidate):
    if record is None:
        return {"verdict": "uncertain", "primary_failure_type": None, "request_state": "missing"}
    if candidate:
        state = record["state"]
        if state != "returned":
            return {"verdict": "uncertain", "primary_failure_type": None, "request_state": state}
        judgment = record["judgment"]
    else:
        state, judgment = "offline_replayed", record
    if type(judgment.get("passed")) not in (bool, type(None)):
        raise ValueError("Automatic passed must be boolean or null")
    primary_type = judgment.get("failure_type")
    if primary_type not in (*DIMENSIONS, None):
        raise ValueError("Invalid automatic primary type")
    verdict = "uncertain" if judgment["passed"] is None else "pass" if judgment["passed"] else "fail"
    if verdict != "fail" and primary_type is not None:
        raise ValueError("A non-failure must not have a primary failure type")
    return {"verdict": verdict, "primary_failure_type": primary_type, "request_state": state}


def counts_for(rows, scorer):
    counts = Counter()
    for row in rows:
        ref, auto = row["reference"], row[scorer]
        counts["scheduled_slots"] += 1
        if ref["answer_verdict"] is None:
            counts["reference_unresolved"] += 1
            continue
        truth, prediction = ref["answer_verdict"], auto["verdict"]
        counts["reference_" + truth] += 1
        if auto["request_state"] not in {"returned", "offline_replayed"}:
            counts["request_error_or_missing_reference_" + truth] += 1
        if prediction == "uncertain":
            counts["abstain_reference_" + truth] += 1
        elif prediction == "fail" and truth == "fail":
            counts["tp"] += 1
        elif prediction == "pass" and truth == "fail":
            counts["fn_decided"] += 1
        elif prediction == "fail":
            counts["fp"] += 1
        else:
            counts["tn"] += 1
        if truth != "fail":
            continue
        gold_type = ref["primary_failure_type"]
        if gold_type is not None:
            counts["reference_fail_single_type"] += 1
        else:
            counts["reference_fail_nonclassifiable"] += 1
        if prediction != "fail":
            continue
        auto_type = auto["primary_failure_type"]
        if auto_type is not None:
            counts["detected_with_automatic_type"] += 1
        if gold_type is None:
            counts["detected_reference_nonclassifiable"] += 1
            continue
        counts["detected_reference_classifiable"] += 1
        counts["category_missing" if auto_type is None else "category_correct" if auto_type == gold_type else "category_incorrect"] += 1
    return counts


def metrics_from_counts(counts):
    c = counts
    decided = c["tp"] + c["fn_decided"] + c["fp"] + c["tn"]
    return {
        "failure_recall_conservative": rate(c["tp"], c["reference_fail"]),
        "failure_recall_decided": rate(c["tp"], c["tp"] + c["fn_decided"]),
        "decided_coverage": rate(decided, c["reference_pass"] + c["reference_fail"]),
        "scheduled_decided_coverage": rate(decided, c["scheduled_slots"]),
        "false_positive_rate_decided": rate(c["fp"], c["fp"] + c["tn"]),
        "false_positive_rate_lower_bound": rate(c["fp"], c["reference_pass"]),
        "false_positive_rate_upper_bound": rate(c["fp"] + c["abstain_reference_pass"], c["reference_pass"]),
        "gold_primary_type_coverage": rate(c["reference_fail_single_type"], c["reference_fail"]),
        "classification_accuracy_detected_classifiable": rate(c["category_correct"], c["detected_reference_classifiable"]),
        "classification_accuracy_compared_types": rate(c["category_correct"], c["category_correct"] + c["category_incorrect"]),
        "classification_accuracy_conservative_all_detected": rate(c["category_correct"], c["tp"]),
        "joint_detection_and_classification_recall": rate(c["category_correct"], c["reference_fail"]),
        "automatic_type_coverage_all_failures": rate(c["detected_with_automatic_type"], c["reference_fail"]),
    }


def summarize(rows, scorer):
    counts = counts_for(rows, scorer)
    explicit_count_keys = (
        "scheduled_slots", "reference_pass", "reference_fail", "reference_unresolved", "tp", "fn_decided", "fp", "tn",
        "abstain_reference_fail", "abstain_reference_pass", "request_error_or_missing_reference_fail",
        "request_error_or_missing_reference_pass", "reference_fail_single_type", "reference_fail_nonclassifiable",
        "detected_with_automatic_type", "detected_reference_nonclassifiable", "detected_reference_classifiable",
        "category_correct", "category_incorrect", "category_missing",
    )
    metrics = metrics_from_counts(counts)
    return {"counts": {key: counts[key] for key in explicit_count_keys},
            "confusion_matrix": {"reference_fail": {"automatic_fail": counts["tp"], "automatic_pass": counts["fn_decided"], "automatic_undecided": counts["abstain_reference_fail"]},
                                 "reference_pass": {"automatic_fail": counts["fp"], "automatic_pass": counts["tn"], "automatic_undecided": counts["abstain_reference_pass"]}},
            "metrics": metrics,
            "request_states": dict(Counter(row[scorer]["request_state"] for row in rows))}


def threshold_checks(summary, validity, protocol, reference_histories):
    m, c = summary["metrics"], summary["counts"]
    criteria = {
        "failure_detection_recall_min": (m["failure_recall_conservative"], .8, "min"),
        "failure_classification_accuracy_min": (m["classification_accuracy_conservative_all_detected"], .8, "min"),
        "test_validity_min": (validity, .9, "min"),
        "false_positive_rate_max": (m["false_positive_rate_decided"], .1, "max"),
        "automatic_decided_coverage_min": (m["decided_coverage"], .8, "min"),
        "scheduled_decided_coverage_min": (m["scheduled_decided_coverage"], .8, "min"),
    }
    checks = {}
    for name, (measure, threshold, direction) in criteria.items():
        value = measure["value"]
        checks[name] = {"measure": measure, "threshold": threshold, "direction": direction,
                        "met": None if value is None else value >= threshold if direction == "min" else value <= threshold}
    checks["reference_pass_minimum"] = {"count": c["reference_pass"], "minimum": protocol["minimum_consensus_pass"], "met": c["reference_pass"] >= protocol["minimum_consensus_pass"]}
    checks["reference_fail_minimum"] = {"count": c["reference_fail"], "minimum": protocol["minimum_consensus_fail"], "met": c["reference_fail"] >= protocol["minimum_consensus_fail"]}
    checks["all_histories_with_agreed_reference"] = {"count": reference_histories, "planned": protocol["histories"], "met": reference_histories == protocol["histories"]}
    return {"checks": checks, "conservative_numerical_checks_met": all(x["met"] is True for x in checks.values()),
            "acceptance_status": "not_certified_human_confirmation_pending",
            "alternative_classifiable_only_check": {
                "measure": m["classification_accuracy_detected_classifiable"], "threshold": .8,
                "met": None if m["classification_accuracy_detected_classifiable"]["value"] is None else m["classification_accuracy_detected_classifiable"]["value"] >= .8,
                "status": "descriptive_alternative_not_a_post_result_replacement_for_the_primary_check"},
            "classification_denominator_notice": "The frozen JSON names the metric but omits its denominator. Existing AC3 service code uses correct categories / all detected reference failures; the earlier pilot draft uses detected failures with two agreed categories. Both are reported. The conservative all-detected check does not call unclassifiable reference types wrong; they are unverified. No post-result choice of the more favorable denominator establishes acceptance."}


def bootstrap(rows, iterations, seed):
    groups = defaultdict(list)
    for row in rows:
        groups[row["history_id"]].append(row)
    names = sorted(groups)
    hist_counts = {name: {scorer: counts_for(groups[name], scorer) for scorer in ("baseline", "candidate")} for name in names}
    chosen_metrics = ("failure_recall_conservative", "false_positive_rate_decided", "decided_coverage",
                      "classification_accuracy_detected_classifiable", "classification_accuracy_conservative_all_detected",
                      "joint_detection_and_classification_recall")
    samples = {view: {name: [] for name in chosen_metrics} for view in ("baseline", "candidate", "candidate_minus_baseline")}
    rng = random.Random(seed)
    for _ in range(iterations):
        totals = {"baseline": Counter(), "candidate": Counter()}
        for _draw in names:
            history = rng.choice(names)
            for scorer in totals:
                totals[scorer].update(hist_counts[history][scorer])
        metrics = {scorer: metrics_from_counts(total) for scorer, total in totals.items()}
        for metric in chosen_metrics:
            a, b = (metrics[scorer][metric]["value"] for scorer in ("baseline", "candidate"))
            for scorer, value in (("baseline", a), ("candidate", b), ("candidate_minus_baseline", None if a is None or b is None else b - a)):
                if value is not None:
                    samples[scorer][metric].append(value)
    result = {"method": "paired_history_cluster_percentile_bootstrap", "histories": len(names),
              "iterations": iterations, "seed": seed, "level": .95, "intervals": {},
              "interpretation": "The same 30 histories are resampled jointly for both scorers. Related synthetic histories are not a random population sample; these intervals describe observed-cohort resampling variability, not external generalisation."}
    for view, metrics in samples.items():
        result["intervals"][view] = {}
        for name, values in metrics.items():
            values.sort()
            enough = len(values) >= iterations * .9
            result["intervals"][view][name] = {
                "lower": values[int((len(values) - 1) * .025)] if enough else None,
                "upper": values[int((len(values) - 1) * .975)] if enough else None,
                "valid_iterations": len(values), "status": "descriptive" if enough else "insufficient_nonzero_denominators"}
    return result


def analyze(study, *, iterations=5000, seed=20261102):
    protocol = validate_protocol(study)
    packet = read(study / "blind-review/compact-all.json")
    private_key = read(study / "private-review-key.json")
    if private_key["material_sha256"] != sha(study / "blind-review/compact-all.json"):
        raise ValueError("Private key does not bind to the blind packet")
    mapping = unique(private_key["mapping"], "review_id", "private key")
    inputs = read(study / "private-scorer-inputs.json")["items"]
    inputs = unique([{**item, "test_id": item["test"]["test_id"]} for item in inputs], "test_id", "scorer inputs")
    if len(mapping) != 120 or len(inputs) != 120 or len({m["history_id"] for m in mapping.values()}) != 30:
        raise ValueError("Expected exactly 120 answers from 30 histories")
    if set(inputs) != {m["test_id"] for m in mapping.values()}:
        raise ValueError("Private key and target-answer IDs differ")
    public = unique(packet["items"], "review_id", "blind packet")
    if set(public) != set(mapping):
        raise ValueError("Blind packet IDs differ from mapping")
    reviewers, declarations, review_hashes = load_references(study, packet)
    baseline_data = read(study / "baseline-scores.json")
    baseline = unique(baseline_data["items"], "test_id", "baseline")
    if set(baseline) != set(inputs) or baseline_data["evaluator"] != "rule-based-v65":
        raise ValueError("Baseline must replay archived rule-v65 on all same 120 answers")
    if baseline_data["snapshot_sha256"] != protocol["old_baseline_snapshot_sha256"]:
        raise ValueError("Archived baseline snapshot hash differs")
    if baseline_data.get("input_sha256") != sha(study / "private-scorer-inputs.json"):
        raise ValueError("Baseline is not bound to the same saved scorer inputs")
    target_summary = read(study / "target-receipt-summary.json")
    if (target_summary.get("protocol_sha256") != sha(study / "protocol.json")
            or target_summary.get("saved_answers") != 120):
        raise ValueError("Target receipt summary is not bound to this complete protocol cohort")
    receipt_verification = read(study / "scorer-receipt-verification.json")
    if (receipt_verification.get("protocol_sha256") != sha(study / "protocol.json")
            or any(receipt_verification.get(key) != 120 for key in (
                "target_answers_verified", "candidate_judgments_verified", "offline_baseline_verified"))
            or receipt_verification.get("same_saved_answers_for_both_scorers") is not True
            or receipt_verification.get("all_candidate_request_payload_fingerprints_verified") is not True):
        raise ValueError("Paired target/scorer request verification is incomplete or mismatched")
    candidates, candidate_hashes, pending = {}, {}, []
    for tid in sorted(inputs):
        path = study / "candidate-scores" / f"{tid}.json"
        if not path.exists():
            pending.append({"test_id": tid, "state": "missing"})
            continue
        record = read(path)
        if record["test_id"] != tid:
            raise ValueError("Candidate score ID mismatch")
        if record["state"] == "dispatched":
            pending.append({"test_id": tid, "state": "dispatched"})
        elif record["state"] not in {"returned", "failed_without_retry", "ambiguous_without_retry"}:
            raise ValueError("Unknown candidate request state")
        if record["state"] == "returned":
            actual = (record.get("provider"), record.get("model"), record.get("reported_model"),
                      record.get("reasoning_effort"), record.get("output_token_limit"), record.get("request_attempts"), record.get("completion_status"))
            if actual != ("openai", "gpt-6-astra", "gpt-6-astra", "max", 8192, 1, "completed"):
                raise ValueError(f"Candidate model/effort/receipt mismatch: {tid}")
            raw = study / "raw-scorer" / f"{tid}.stdout"
            if not raw.exists() or sha(raw) != record["raw_sha256"]:
                raise ValueError(f"Candidate raw receipt hash mismatch: {tid}")
        candidates[tid], candidate_hashes[str(path.relative_to(study))] = record, sha(path)
    if pending:
        raise RuntimeError(f"Not final: {len(pending)} candidate slots missing/in progress; no analysis outputs were written")
    extra = {p.stem for p in (study / "candidate-scores").glob("*.json")} - set(inputs)
    if extra:
        raise ValueError("Unexpected extra candidate score IDs")
    target_receipts, rows = [], []
    for rid, key in sorted(mapping.items()):
        tid, item = key["test_id"], inputs[key["test_id"]]
        response, question = item["response"], item["test"]
        if (item["history_id"], response["response_id"], baseline[tid]["response_id"]) != (key["history_id"], key["response_id"], key["response_id"]):
            raise ValueError("Answer or baseline not bound to same response/history")
        if (public[rid]["question"], public[rid]["reference_behavior"], public[rid]["answer"]) != (question["prompt"], question["expected_behavior"], response["response_text"]):
            raise ValueError("Public review content differs from private saved target answer")
        meta = response["execution_metadata"]
        actual_target = (meta["response_source"], response["model"], meta["reported_model"], meta["requested_reasoning_effort"],
                         meta["requested_output_token_limit"], meta["request_attempts"], meta["completion_status"])
        if actual_target != ("openai", "gpt-6-astra", "gpt-6-astra", "max", 8192, 1, "complete"):
            raise ValueError(f"Target actual request receipt differs: {tid}")
        target_receipts.append(actual_target)
        first, second = (reviewer[rid] for reviewer in reviewers)
        rows.append({**key, "intended_question_dimension": question["dimension"],
                     "reference": combine_reference(first, second),
                     "reviewer_1": {field: first[field] for field in ("question_validity", "reference_validity", "answer_verdict", "failure_type", "failure_type_status", "safe_but_incomplete", "source_message_ids", "reason", "classification_reason")},
                     "reviewer_2": {field: second[field] for field in ("question_validity", "reference_validity", "answer_verdict", "failure_type", "failure_type_status", "safe_but_incomplete", "source_message_ids", "reason", "classification_reason")},
                     "baseline": normalize_prediction(baseline[tid], candidate=False),
                     "candidate": normalize_prediction(candidates.get(tid), candidate=True)})
    if set(Counter(row["history_id"] for row in rows).values()) != {4}:
        raise ValueError("All 30 histories must contribute exactly four scheduled questions")
    validity = rate(sum(row["reference"]["question_agreed_valid"] for row in rows), len(rows))
    joint_validity = rate(sum(row["reference"]["question_agreed_valid"] and row["reference"]["reference_agreed_valid"] for row in rows), len(rows))
    answer_counts = Counter(row["reference"]["answer_consensus_status"] for row in rows)
    type_counts = Counter(row["reference"]["primary_type_consensus_status"] for row in rows if row["reference"]["answer_verdict"] == "fail")
    gold_types = {dim: sum(row["reference"]["primary_failure_type"] == dim for row in rows) for dim in DIMENSIONS}
    reference_histories = len({row["history_id"] for row in rows if row["reference"]["answer_verdict"] is not None})
    summary = {scorer: summarize(rows, scorer) for scorer in ("baseline", "candidate")}
    for scorer in summary:
        summary[scorer]["threshold_evaluation"] = threshold_checks(summary[scorer], joint_validity, protocol, reference_histories)
    schema_sources = {"backend/app/services/ac3_metrics.py": sha(ROOT / "backend/app/services/ac3_metrics.py"),
                      "scripts/prepare_ac3_pilot_threshold_draft.py": sha(ROOT / "scripts/prepare_ac3_pilot_threshold_draft.py")}
    manifest = {name: sha(study / name) for name in ("protocol.json", "sources.json", "blind-review/compact-all.json", "private-review-key.json", "private-scorer-inputs.json", "baseline-scores.json", "target-receipt-summary.json", "scorer-receipt-verification.json")}
    manifest.update(review_hashes)
    provenance = {"input_file_sha256": manifest, "candidate_score_file_sha256": candidate_hashes,
                  "candidate_score_manifest_sha256": canonical_sha(candidate_hashes), "analysis_script_sha256": sha(__file__),
                  "metric_definition_source_sha256": schema_sources,
                  "target": {"provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max", "output_token_limit": 8192, "request_attempts": 1, "verified_answer_receipts": len(target_receipts)},
                  "candidate_judge": {"provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max", "output_token_limit": 8192, "request_attempts": 1, "returned_receipts": sum(c["state"] == "returned" for c in candidates.values()), "failed_or_ambiguous_receipts": sum(c["state"] != "returned" for c in candidates.values())},
                  "baseline": {"evaluator": "rule-based-v65", "execution": "offline replay on the same new Astra MAX saved answers; no model call", "snapshot_sha256": baseline_data["snapshot_sha256"]},
                  "reference_reviewers": declarations, "reference_review_model_provenance": "Independent AI agent declarations retained; not OpenAI API transport receipts and not independently authenticated human review."}
    consensus = {"format": "ac3-astra-max-reference-consensus-v1", "status": "ai_reference_consensus_human_confirmation_pending",
                 "human_confirmed": False, "counts": {"answers": len(rows), "histories": 30, "answer_consensus": dict(answer_counts), "failure_type_consensus": dict(type_counts), "agreed_primary_failure_types": gold_types},
                 "rules": {"answer": "Both reviewers independently agree pass/fail and both judge question and reference valid; type disagreement does not remove the answer label.",
                           "primary_type": "Both independently classify the same single actual failure type; multiple/uncertain/disagreement stays unclassifiable. Intended question dimension is never a gold error type.",
                           "human_status": "New answer labels are AI MAX reference reviews pending explicit human confirmation; historical approvals do not certify these new answers."},
                 "provenance": provenance,
                 "items": [{k: v for k, v in row.items() if k not in {"baseline", "candidate"}} for row in rows]}
    per_gold_type = {}
    for dim in DIMENSIONS:
        selected = [row for row in rows if row["reference"]["primary_failure_type"] == dim]
        per_gold_type[dim] = {"agreed_actual_failures": len(selected), "status": "unmeasured_no_agreed_positive_failures" if not selected else "limited_observed_support",
                             "baseline": summarize(selected, "baseline"), "candidate": summarize(selected, "candidate")}
    paired = Counter()
    for row in rows:
        truth, a, b = row["reference"]["answer_verdict"], row["baseline"]["verdict"], row["candidate"]["verdict"]
        if truth is None:
            paired["reference_unresolved"] += 1
        elif a == "uncertain" or b == "uncertain":
            paired["one_or_both_undecided"] += 1
        else:
            paired["both_correct" if a == b == truth else "candidate_only_correct" if b == truth else "baseline_only_correct" if a == truth else "neither_correct"] += 1
    analysis = {"format": "ac3-astra-max-paired-analysis-v1", "complete": True,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "descriptive_ai_reference_human_confirmation_pending", "human_confirmed": False,
                "cohort": {"scheduled_questions": len(rows), "saved_target_answers": len(inputs), "histories": 30,
                           "candidate_finalized_slots": len(candidates), "target_errors_or_missing": 0, "candidate_request_states": dict(Counter(c["state"] for c in candidates.values())),
                           "answer_consensus": dict(answer_counts), "reference_histories": reference_histories,
                           "question_validity": validity, "joint_question_reference_validity": joint_validity,
                           "primary_type_consensus": dict(type_counts), "agreed_primary_failure_types": gold_types,
                           "gold_primary_type_coverage": summary["candidate"]["metrics"]["gold_primary_type_coverage"]},
                "metric_definitions": METRIC_DEFINITIONS, "baseline": summary["baseline"], "candidate": summary["candidate"],
                "paired_metric_differences": {name: None if summary["baseline"]["metrics"][name]["value"] is None or summary["candidate"]["metrics"][name]["value"] is None else summary["candidate"]["metrics"][name]["value"] - summary["baseline"]["metrics"][name]["value"] for name in METRIC_DEFINITIONS},
                "paired_verdict_correctness": dict(paired), "per_actual_gold_failure_type": per_gold_type,
                "per_intended_question_dimension": {dim: {"notice": "Question-design stratum, not evidence of an actual error type.", "baseline": summarize([r for r in rows if r["intended_question_dimension"] == dim], "baseline"), "candidate": summarize([r for r in rows if r["intended_question_dimension"] == dim], "candidate")} for dim in DIMENSIONS},
                "history_cluster_bootstrap": bootstrap(rows, iterations, seed), "provenance": provenance,
                "limitations": ["All new answer reference labels are independent AI MAX reviews pending human confirmation; numerical threshold checks alone do not establish AC3 acceptance.",
                                "Both reviewers and the candidate judge share the Astra model family; correlated errors remain possible despite independently blinded review.",
                                "Thirty reused, related synthetic histories are a descriptive cohort, not a population-random sample or unseen external benchmark.",
                                "A primary failure type is verified only when both reviewers independently identify the same actual error. Unclassifiable failures remain in answer-level denominators.",
                                "Zero agreed positive failures for a type means sensitivity for that type is unmeasured, not perfect or zero.",
                                "Conditional classification rates can overstate whole-cohort diagnostic performance; all-failure joint coverage and conservative all-detected rates are shown alongside them.",
                                "This comparison isolates scoring on the same saved answers. It is not a target-model improvement claim relative to archived Luna experiments.",
                                "A single target response per question does not establish between-run sampling stability. Cluster intervals keep within-history questions together but do not resolve cohort-selection bias.",
                                "With no observed false positives, a resampling interval can collapse to zero. This does not bound the false-positive risk in unseen cases or establish zero population risk."],
                "items": [{"review_id": row["review_id"], "test_id": row["test_id"], "response_id": row["response_id"], "history_id": row["history_id"], "intended_question_dimension": row["intended_question_dimension"], "reference": row["reference"], "baseline": row["baseline"], "candidate": row["candidate"]} for row in rows]}
    return consensus, analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261102)
    args = parser.parse_args()
    if args.iterations < 100:
        raise ValueError("Use at least 100 cluster bootstrap iterations")
    consensus, analysis = analyze(args.study, iterations=args.iterations, seed=args.seed)
    write(args.study / "reference-consensus.json", consensus)
    write(args.study / "analysis.json", analysis)
    print(json.dumps({"status": analysis["status"], "cohort": analysis["cohort"],
                      "baseline": analysis["baseline"]["metrics"], "candidate": analysis["candidate"]["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
