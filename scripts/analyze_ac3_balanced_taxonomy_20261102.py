"""Offline paired analysis of the frozen balanced taxonomy diagnostic.

Default/check-ready only reports ledger readiness. Write analysis.json with
--finalize after every planned slot has a terminal record. Never dispatch a
request, infer a reference from an intended injection label, or alter reviews.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import statistics

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1"
ARMS = ("original", "revised")
TYPES = ("accuracy", "freshness", "conflict_resolution", "appropriate_use")
ACTUAL = (*TYPES, "pass", "unclassified_reference_failure", "unresolved_reference")
PREDICTED = (*TYPES, "pass", "unclassified_fail", "uncertain", "error_missing")
TERMINAL = {"returned", "failed_without_retry", "ambiguous_without_retry",
            "not_dispatched_provider_stop", "worker_failed", "failed"}


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * p
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def unique(items, key):
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate {key}")
    return result


def load_runner():
    path = ROOT / "scripts/run_ac3_balanced_taxonomy_20261102.py"
    spec = importlib.util.spec_from_file_location("frozen_taxonomy_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prediction(record):
    if record.get("state") != "returned":
        return "error_missing"
    judgment = record["judgment"]
    if judgment["passed"] is True:
        return "pass"
    if judgment["passed"] is None:
        return "uncertain"
    return judgment["failure_type"] or "unclassified_fail"


def actual_reference(ref):
    if not ref["question_source_valid"] or ref["verdict"] == "uncertain":
        return "unresolved_reference"
    if ref["verdict"] == "pass":
        return "pass"
    return ref["failure_type"] or "unclassified_reference_failure"


def validate_returned(record, memories):
    expected = {"provider": "openai", "requested_model": "gpt-6-astra",
                "reasoning_effort": "max", "output_token_limit": 8192,
                "request_attempts": 1, "reported_model": "gpt-6-astra",
                "completion_status": "completed"}
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError(f"Returned receipt has unverified {key}: {record.get('review_id')}")
    if not isinstance(record.get("http_status"), int) or not 200 <= record["http_status"] < 300:
        raise ValueError("Returned receipt lacks a successful HTTP response")
    judgment = record.get("judgment")
    required = {"passed", "reason", "evidence_memory_ids", "failure_type", "classification_reason"}
    if not isinstance(judgment, dict) or set(judgment) != required:
        raise ValueError("Returned judgment does not match the frozen schema")
    if judgment["passed"] is not None and not isinstance(judgment["passed"], bool):
        raise ValueError("Invalid passed field")
    if judgment["failure_type"] not in (*TYPES, None):
        raise ValueError("Invalid failure type")
    if judgment["passed"] is not False and judgment["failure_type"] is not None:
        raise ValueError("A pass/undecided judgment cannot have a failure category")
    if not all(isinstance(judgment[k], str) for k in ("reason", "classification_reason")):
        raise ValueError("Missing textual judgment reason")
    ids = judgment["evidence_memory_ids"]
    supplied = {m["memory_id"] for m in memories}
    if not isinstance(ids, list) or not all(isinstance(k, str) and k in supplied for k in ids):
        raise ValueError("Judgment evidence is outside the supplied source boundary")
    if judgment["passed"] is not None and not ids:
        raise ValueError("Decided judgment has no evidence")
    if json.loads(record["raw_output_text"]) != judgment:
        raise ValueError("Parsed judgment differs from the retained provider text")


def collect(study=STUDY):
    protocol = read(study / "protocol.json")
    for name, expected in protocol["bound_files_sha256"].items():
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT.resolve()) or sha(path) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    dataset = read(study / "dataset-frozen.json")
    refs = read(study / "reference-consensus.json")
    cases = unique(dataset["items"], "review_id")
    sources = unique(dataset["sources"], "source_id")
    reference = unique(refs["items"], "review_id")
    if len(cases) != 150 or len(sources) != 30 or set(cases) != set(reference):
        raise ValueError("Frozen cases and actual reference identities do not match")
    if Counter(item["source_id"] for item in cases.values()) != Counter({key: 5 for key in sources}):
        raise ValueError("Expected five cases in every one of the thirty source clusters")
    jobs = [(job["arm"], job["review_id"]) for job in protocol["jobs"]]
    expected_jobs = {(arm, rid) for arm in ARMS for rid in cases}
    if len(jobs) != 300 or set(jobs) != expected_jobs:
        raise ValueError("The frozen schedule does not preserve all 300 paired slots")
    model_settings = {"provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max",
                      "output_token_limit": 8192, "provider_attempts": 1}
    if any(protocol.get(k) != v for k, v in model_settings.items()):
        raise ValueError("The paired protocol changed the requested model settings")
    runner = load_runner()
    rubrics = {"original": (study / "original-rubric.txt").read_text(),
               "revised": (study / "development/revised-rubric.txt").read_text()}
    rows, input_hashes, score_hashes, states, pending = [], {}, {}, Counter(), []
    verified = Counter()
    for arm, rid in jobs:
        item, ref = cases[rid], reference[rid]
        if item["source_id"] != ref["source_id"] or ref["verdict"] not in ("pass", "fail", "uncertain"):
            raise ValueError("Reference source binding or verdict is invalid")
        if not isinstance(ref["question_source_valid"], bool) or ref["failure_type"] not in (*TYPES, None):
            raise ValueError("Reference category/source status is invalid")
        path = study / "scores" / arm / (rid + ".json")
        record = read(path) if path.exists() else {"state": "not_recorded"}
        states[(arm, record["state"])] += 1
        if record["state"] not in TERMINAL:
            pending.append({"arm": arm, "review_id": rid, "state": record["state"]})
            continue
        if record.get("arm") != arm or record.get("review_id") != rid:
            raise ValueError("A terminal receipt belongs to a different scheduled slot")
        score_hashes[str(path.relative_to(study))] = sha(path)
        payload, memories = runner.payload_for(item, sources, rubrics[arm])
        expected_shared, expected_payload = digest(payload["input"]), digest(payload)
        input_hashes[(arm, rid)] = expected_shared
        if record.get("shared_input_sha256") is not None:
            if record["shared_input_sha256"] != expected_shared:
                raise ValueError("The actually recorded shared input differs from the frozen case")
            verified[(arm, "shared_input_receipts")] += 1
        if record.get("request_payload_sha256") is not None and record["request_payload_sha256"] != expected_payload:
            raise ValueError("The recorded payload differs from the frozen rubric/settings")
        if record["state"] == "returned":
            if record.get("shared_input_sha256") != expected_shared or record.get("request_payload_sha256") != expected_payload:
                raise ValueError("Returned receipt lacks verifiable request fingerprints")
            validate_returned(record, memories)
            verified[(arm, "returned_max_receipts")] += 1
        raw_hash = record.get("raw_sha256")
        if raw_hash is not None:
            raw_path = study / "raw" / arm / (rid + ".stdout")
            if not raw_path.exists() or sha(raw_path) != raw_hash:
                raise ValueError("Raw journal hash mismatch")
            raw = read(raw_path)
            if raw != {k: v for k, v in record.items() if k != "raw_sha256"}:
                raise ValueError("Terminal score differs from its immutable raw worker output")
            verified[(arm, "raw_journals")] += 1
        rows.append({"review_id": rid, "source_id": item["source_id"], "arm": arm,
                     "actual": actual_reference(ref), "reference_verdict": ref["verdict"],
                     "question_source_valid": ref["question_source_valid"],
                     "prediction": prediction(record), "state": record["state"],
                     "record": record})
    paired_shared = 0
    for rid in cases:
        if all((arm, rid) in input_hashes for arm in ARMS):
            if input_hashes[("original", rid)] != input_hashes[("revised", rid)]:
                raise ValueError("The two arms received different question/answer/memory input")
            paired_shared += 1
    progress = {"format": "ac3-balanced-taxonomy-readiness-v1", "complete": not pending,
                "planned_cases": 150, "planned_slots": 300, "terminal_slots": len(rows),
                "pending_slots": len(pending), "pending": pending,
                "states": {arm: {state: n for (a, state), n in states.items() if a == arm} for arm in ARMS},
                "receipt_verification": {arm: {key: n for (a, key), n in verified.items() if a == arm} for arm in ARMS},
                "planned_pair_shared_input_hash_matches": paired_shared,
                "claim": "Readiness only; no correctness metrics or acceptance claim."}
    return protocol, dataset, refs, rows, score_hashes, progress


def metrics(rows):
    matrix = {actual: {predicted: 0 for predicted in PREDICTED} for actual in ACTUAL}
    for row in rows:
        matrix[row["actual"]][row["prediction"]] += 1
    fail_rows = [r for r in rows if r["actual"] in (*TYPES, "unclassified_reference_failure")]
    pass_rows = [r for r in rows if r["actual"] == "pass"]
    detected = [r for r in fail_rows if r["prediction"] in (*TYPES, "unclassified_fail")]
    correct_type = [r for r in fail_rows if r["actual"] in TYPES and r["prediction"] == r["actual"]]
    fp = sum(r["prediction"] in (*TYPES, "unclassified_fail") for r in pass_rows)
    pass_unknown = sum(r["prediction"] in ("uncertain", "error_missing") for r in pass_rows)
    decided_pass = sum(r["prediction"] == "pass" for r in pass_rows)
    decided = sum(r["prediction"] in (*TYPES, "pass", "unclassified_fail") for r in rows)
    result = {
        "joint_detection_and_correct_category": ratio(len(correct_type), len(fail_rows)),
        "failure_recall": ratio(len(detected), len(fail_rows)),
        "classification_among_detected_failures": ratio(len(correct_type), len(detected)),
        "false_positive_rate_all_reference_passes": ratio(fp, len(pass_rows)),
        "false_positive_rate_decided": ratio(fp, fp + decided_pass),
        "false_positive_rate_lower_bound": ratio(fp, len(pass_rows)),
        "false_positive_rate_upper_bound": ratio(fp + pass_unknown, len(pass_rows)),
        "decided_coverage": ratio(decided, len(rows)),
    }
    per_category = {}
    for category in TYPES:
        actual_rows = [r for r in rows if r["actual"] == category]
        n = len(actual_rows)
        per_category[category] = {
            "joint_detection_and_correct_category": ratio(sum(r["prediction"] == category for r in actual_rows), n),
            "failure_recall": ratio(sum(r["prediction"] in (*TYPES, "unclassified_fail") for r in actual_rows), n),
            "status": "measured" if n else "unmeasured_no_actual_positive_references",
        }
    counts = {"planned_slots": len(rows), "reference_failures": len(fail_rows), "reference_passes": len(pass_rows),
              "reference_unresolved": sum(r["actual"] == "unresolved_reference" for r in rows),
              "reference_failures_without_single_type": sum(r["actual"] == "unclassified_reference_failure" for r in rows),
              "detected_reference_failures": len(detected), "correct_category": len(correct_type),
              "detected_failures_without_predicted_type": sum(r["prediction"] == "unclassified_fail" for r in fail_rows),
              "false_positives": fp, "pass_controls_unresolved_or_error": pass_unknown,
              "returned_undecided": sum(r["prediction"] == "uncertain" for r in rows),
              "errors_or_missing": sum(r["prediction"] == "error_missing" for r in rows),
              "decided_verdicts": decided}
    return {"metrics": result, "per_category": per_category, "counts": counts, "confusion_matrix": matrix}


def threshold_checks(summary, protocol, reference_validity, gate):
    t = protocol["thresholds"]
    definitions = {
        "correct_category_all_reference_failures_min": (summary["metrics"]["joint_detection_and_correct_category"], "min"),
        "failure_detection_min": (summary["metrics"]["failure_recall"], "min"),
        "question_reference_validity_min": (reference_validity, "min"),
        "false_positive_max": (summary["metrics"]["false_positive_rate_all_reference_passes"], "max"),
        "decided_coverage_min": (summary["metrics"]["decided_coverage"], "min"),
    }
    checks = {}
    for name, (measure, direction) in definitions.items():
        value = measure["value"]
        met = value is not None and (value >= t[name] if direction == "min" else value <= t[name])
        checks[name] = {"measure": measure, "threshold": t[name], "direction": direction, "met": met}
    passed = all(c["met"] for c in checks.values())
    return {"checks": checks, "numerical_checks_met": passed, "reference_gate_met": gate,
            "acceptance_status": "ai_reference_numerical_checks_met_human_verification_pending" if passed and gate else "insufficient_reference_evidence" if not gate else "numerical_thresholds_not_all_met",
            "notice": "Point thresholds are separate from confidence intervals, category-specific coverage and human verification."}


def flattened(summary):
    values = {key: value["value"] for key, value in summary["metrics"].items()}
    values.update({"category_" + key: value["joint_detection_and_correct_category"]["value"]
                   for key, value in summary["per_category"].items()})
    return values


def cluster_bootstrap(rows):
    clusters = sorted({row["source_id"] for row in rows})
    grouped = {(arm, source): [r for r in rows if r["arm"] == arm and r["source_id"] == source]
               for arm in ARMS for source in clusters}
    if len(clusters) != 30 or any(len(grouped[(arm, source)]) != 5 for arm in ARMS for source in clusters):
        raise ValueError("Bootstrap must preserve all five paired cases in every history")
    rng = random.Random(20261102)
    draws = {arm: {} for arm in (*ARMS, "revised_minus_original")}
    for _ in range(5000):
        selected = rng.choices(clusters, k=len(clusters))
        values = {arm: flattened(metrics([row for source in selected for row in grouped[(arm, source)]]))
                  for arm in ARMS}
        for arm in ARMS:
            for key, value in values[arm].items():
                if value is not None:
                    draws[arm].setdefault(key, []).append(value)
        for key in values["original"]:
            before, after = values["original"][key], values["revised"][key]
            if before is not None and after is not None:
                draws["revised_minus_original"].setdefault(key, []).append(after - before)
    return {"method": "paired_source_history_cluster_percentile_bootstrap", "iterations": 5000,
            "seed": 20261102, "histories": len(clusters), "level": 0.95,
            "intervals": {arm: {key: {"lower": quantile(v, .025), "upper": quantile(v, .975),
                                      "valid_iterations": len(v), "status": "descriptive"}
                                for key, v in stats.items()} for arm, stats in draws.items()},
            "limitations": ["Keep both arms and all five cases together when resampling each history.",
                            "Selected related synthetic clusters are not a random population sample.",
                            "A zero-event resampling interval can collapse to zero without establishing zero future risk."]}


def paired_counts(rows):
    maps = {arm: unique([r for r in rows if r["arm"] == arm], "review_id") for arm in ARMS}
    result = {"joint_category_verified_success": Counter(), "verdict_verified_correctness": Counter(),
              "identical_prediction": 0, "different_prediction": 0}
    for rid, before in maps["original"].items():
        after = maps["revised"][rid]
        if before["actual"] != after["actual"]:
            raise ValueError("Paired arms have different actual reference labels")
        actual = before["actual"]
        same = before["prediction"] == after["prediction"]
        result["identical_prediction" if same else "different_prediction"] += 1
        for key, eligible, fn in (
            ("joint_category_verified_success", actual in (*TYPES, "unclassified_reference_failure"),
             lambda row: actual in TYPES and row["prediction"] == actual),
            ("verdict_verified_correctness", actual != "unresolved_reference",
             lambda row: row["prediction"] == "pass" if actual == "pass" else row["prediction"] in (*TYPES, "unclassified_fail")),
        ):
            if not eligible:
                continue
            b, a = bool(fn(before)), bool(fn(after))
            result[key]["improved" if a and not b else "worsened" if b and not a else "both_verified_success" if a else "neither_verified_success"] += 1
    for key in ("joint_category_verified_success", "verdict_verified_correctness"):
        result[key] = {name: result[key][name] for name in ("improved", "worsened", "both_verified_success", "neither_verified_success")}
        result[key]["denominator"] = sum(result[key].values())
    result["notice"] = "Changes concern evaluator judgments on identical curated answers; neither verified success includes uncertainty/errors, not only confirmed wrong classifications."
    return result


def resource_usage(rows):
    result = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        usage, latency = [], []
        for row in arm_rows:
            record = row["record"]
            u = record.get("usage")
            if isinstance(u, dict) and all(isinstance(u.get(k), int) for k in ("input_tokens", "output_tokens")):
                usage.append(u)
            try:
                start = datetime.fromisoformat(record["started_utc"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(record["completed_utc"].replace("Z", "+00:00"))
                seconds = (end - start).total_seconds()
                if seconds >= 0:
                    latency.append(seconds)
            except (KeyError, TypeError, ValueError):
                pass
        reasoning = [u["output_tokens_details"]["reasoning_tokens"] for u in usage
                     if isinstance(u.get("output_tokens_details"), dict)
                     and isinstance(u["output_tokens_details"].get("reasoning_tokens"), int)]
        result[arm] = {"usage_receipts": len(usage), "slots_without_usage": len(arm_rows) - len(usage),
                       "input_tokens_observed": sum(u["input_tokens"] for u in usage),
                       "output_tokens_observed": sum(u["output_tokens"] for u in usage),
                       "reasoning_token_receipts": len(reasoning), "reasoning_tokens_observed": sum(reasoning),
                       "reasoning_tokens_are_part_of_output_tokens": True,
                       "latency_receipts": len(latency), "latency_seconds_sum": sum(latency),
                       "latency_seconds_median": statistics.median(latency) if latency else None,
                       "latency_seconds_p95": quantile(latency, .95),
                       "actual_billed_usd": None,
                       "notice": "Observed token usage and per-request elapsed time; missing usage is unknown. Concurrent request latencies are not total wall-clock runtime. Provider billing is not inferred."}
    return result


def human_verification(study):
    """Read explicit approval of references; never infer it from elapsed time."""
    path = study / "human-confirmation.json"
    if not path.exists():
        return None
    receipt = read(path)
    expected = {"status": "user_reported_independent_ai_assisted", "answers": 150,
                "histories": 30, "human_reviewers": 2, "reviewed_each_item": True,
                "completed_independently": True, "used_ai_assistance": True}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("Human confirmation is for a different cohort or review mode")
    bindings = receipt.get("bound_files_sha256")
    required = {str((study / name).relative_to(ROOT)) for name in
                ("protocol.json", "dataset-frozen.json", "reference-consensus.json",
                 "review-max/reviewer-1.json", "review-max/reviewer-2.json")}
    if not isinstance(bindings, dict) or not required.issubset(bindings):
        raise ValueError("Human confirmation does not bind all frozen reference evidence")
    for name, expected_hash in bindings.items():
        source = ROOT / name
        if not source.resolve().is_relative_to(ROOT.resolve()) or sha(source) != expected_hash:
            raise ValueError(f"Human-confirmed source changed: {name}")
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path),
            "status": receipt["status"], "scope": receipt["scope"],
            "reviewers": 2, "completed_independently": True,
            "used_ai_assistance": True,
            "identities_independently_authenticated": receipt.get("identities_independently_authenticated", False),
            "blindness_to_automatic_scores": receipt.get("blindness_to_automatic_scores", "not separately established"),
            "automatic_grader_predictions_human_approved": False}


def analyze(protocol, dataset, refs, rows, score_hashes, progress, study=STUDY):
    if not progress["complete"] or len(rows) != 300:
        raise ValueError("All 300 planned slots must have terminal records before final analysis")
    reference = refs["items"]
    actual_counts = Counter(actual_reference(ref) for ref in reference)
    source_counts = Counter(item["source_id"] for item in dataset["items"])
    valid = sum(ref["question_source_valid"] for ref in reference)
    question_valid = sum(len(ref.get("reviews", [])) == 2 and all(r.get("question_validity") == "valid" for r in ref["reviews"]) for ref in reference)
    gate = bool(refs.get("ready_for_scoring")) and valid == 150 and actual_counts["pass"] >= 30 and all(actual_counts[t] >= 30 for t in TYPES) and len(source_counts) == 30
    summaries = {arm: metrics([r for r in rows if r["arm"] == arm]) for arm in ARMS}
    validity = ratio(valid, 150)
    for arm, summary in summaries.items():
        summary["threshold_evaluation"] = threshold_checks(summary, protocol, validity, gate)
    points = {arm: flattened(summary) for arm, summary in summaries.items()}
    differences = {key: None if points["original"][key] is None or points["revised"][key] is None else points["revised"][key] - points["original"][key] for key in points["original"]}
    source_files = [study / "protocol.json", study / "dataset-frozen.json", study / "reference-consensus.json", study / "ANALYSIS-PLAN.md", study / "original-rubric.txt", study / "development/revised-rubric.txt"]
    verification = human_verification(study)
    if verification:
        source_files.append(study / "human-confirmation.json")
        for summary in summaries.values():
            check = summary["threshold_evaluation"]
            if check["numerical_checks_met"] and gate:
                check["acceptance_status"] = "user_reported_ai_assisted_reference_verified_numerical_checks_met"
            check["human_verification_scope"] = "150 source/answer/category reference judgments only; not the 300 automatic grader predictions."
    return {
        "format": "ac3-balanced-max-paired-analysis-v1", "complete": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "insufficient_reference_evidence" if not gate else "descriptive_ai_assisted_human_confirmed_reference" if verification else "descriptive_ai_reference_human_confirmation_pending",
        "study_kind": "controlled_curated_fault_injection_evaluator_diagnostic",
        "target_model_performance_claim": False, "human_confirmed": bool(verification),
        "human_confirmation_pending": not bool(verification), "human_verification": verification,
        "cohort": {"planned_cases": 150, "histories": 30, "planned_grader_slots": 300,
                   "terminal_slots": len(rows), "reference_gate_met": gate,
                   "actual_reference_counts": dict(actual_counts),
                   "question_validity": ratio(question_valid, 150), "joint_question_reference_validity": validity,
                   "actual_agreed_failure_type_counts": {t: actual_counts[t] for t in TYPES},
                   "sources": dict(source_counts)},
        "metric_definitions": {
            "primary": "Verified detection and correct actual category / all agreed reference failures, including missed, untyped, uncertain and error slots in the denominator.",
            "conditional_classification": "Verified correct actual category / all detected reference failures; supplementary, not a replacement primary denominator.",
            "false_positive_primary": "Observed failing judgments / all agreed reference passes; undecided/error pass controls shown separately with bounds.",
            "decided_coverage": "Valid explicit pass/fail verdicts / all 150 planned slots in each arm.",
            "unclassified_fail": "passed=false with no failure_type is detected but untyped; distinct from passed=null and transport/schema errors.",
            "missing_or_error": "Contributes no verified primary success but is reported separately, not labelled a confirmed incorrect classification."},
        **summaries, "revised_minus_original": differences,
        "paired_counts": paired_counts(rows), "history_cluster_bootstrap": cluster_bootstrap(rows),
        "resource_usage": resource_usage(rows), "execution": progress,
        "provenance": {"input_file_sha256": {str(p.relative_to(ROOT)): sha(p) for p in source_files},
                       "score_file_sha256": score_hashes,
                       "score_manifest_sha256": digest(score_hashes),
                       "analysis_script_sha256": sha(Path(__file__)),
                       "provider": "openai", "model": "gpt-6-astra", "reasoning_effort": "max",
                       "output_token_limit": 8192, "provider_attempts": 1,
                       "reference_review_files_sha256": refs.get("review_files_sha256"),
                       "analysis_timing_notice": "The analysis plan was frozen before calls. Exact analysis implementation is hashed here, not represented as independently registered pre-call code.",
                       "reviewer_provenance_notice": "Original independent MAX AI declarations remain distinct from provider transport receipts and future human verification."},
        "limitations": ["These answers are deliberately curated diagnostic fault injections, not natural target responses or real-world error prevalence.",
                        "The new validation data were withheld from rubric development; actual exposure and pre-call freeze records remain separate audit evidence.",
                        "Reference reviewers and graders share the Astra model family; correlated errors remain possible.",
                        "Thirty synthetic source clusters and five designed cases per cluster are not 150 independent natural histories.",
                        "Unresolved or multiple actual errors are never forced into the intended design category.",
                        "Numerical thresholds do not establish population-wide reliability or statistically clear improvement. Any explicit human verification is bound to its stated reference-only scope.",
                        "User-reported AI-assisted human checks do not independently authenticate reviewer identities or establish blindness to automatic scores.",
                        "A strong baseline, tie, or regression remains a reportable outcome. Zero observed false positives does not establish zero future risk."],
        "items": [{k: v for k, v in row.items() if k != "record"} for row in rows],
    }


def main(finalize=False):
    protocol, dataset, refs, rows, score_hashes, progress = collect()
    if not finalize or not progress["complete"]:
        print(json.dumps(progress, ensure_ascii=False))
        if finalize:
            raise SystemExit("Refusing final analysis: planned slots remain non-terminal")
        return
    report = analyze(protocol, dataset, refs, rows, score_hashes, progress)
    path = STUDY / "analysis.json"
    stage = path.with_suffix(".json.pending")
    stage.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    stage.replace(path)
    print(json.dumps({"analysis": str(path), "complete": True, "reference_gate": report["cohort"]["reference_gate_met"],
                      "primary": {arm: report[arm]["metrics"]["joint_detection_and_correct_category"] for arm in ARMS},
                      "human_confirmation_pending": report["human_confirmation_pending"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true", help="Write analysis only after parent confirms collection is finished")
    parser.add_argument("--check-ready", action="store_true", help="Report readiness only (also the default)")
    main(parser.parse_args().finalize)
