"""Offline integrity, scoring, budget, and dispatch-pacing checks for v7."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_phase4_c_four_arm_v7 as analyzer
import prepare_phase4_c_four_arm_v7 as preparer
import run_phase4_c_four_arm_v7 as runner


def _make_analysis_fixture():
    subset = []
    for category, count in runner.EXPECTED_CATEGORY_COUNTS.items():
        for i in range(count):
            is_abs = category == "abstention"
            subset.append({
                "question_id": f"case-{category}-{i}{'_abs' if is_abs else ''}",
                "question_type": "single-session-user" if is_abs else category,
                "question": f"question {category} {i}", "answer": f"answer {category} {i}",
                "haystack_session_ids": [f"h-{category}-{i}"],
                "answer_session_ids": [f"a-{category}-{i}"],
            })
    binding = {"source_sha256": "fixture-source"}
    protocol = {
        "id": runner.EXPECTED_PROTOCOL_ID,
        "source": {"revision": "fixture", "source_manifest_sha256": "manifest",
                   "oracle_source_sha256": "oracle"},
        "scorer": {"model": runner.EXPECTED_MODEL},
        "execution": {"openrouter_minimum_start_to_start_seconds": 4.0,
                      "initial_cooldown_seconds": 65.0},
        "selection": {"v6_lineage": {"protocol_sha256": "p6", "subset_sha256": "s6"}},
        "analysis": {"selection_rule": "Unique highest pooled strict pass rate and 2 of 3 repetition wins against each competitor; otherwise no clear winner."},
        "app_source": {},
    }
    inputs = {"protocol": protocol, "protocol_sha256": "protocol", "subset_sha256": "subset",
              "subset": subset, "directory": Path("/fixture/v7"), "upstream_binding": binding}
    prompt_fn = lambda category, question, answer, response, abstention=False: (
        f"{category}|{question}|{answer}|{response}|{abstention}"
    )
    grader_fn = lambda model, prompt: {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "n": 1, "temperature": 0, "max_tokens": 128, "reasoning_effort": "none",
    }
    deps = {"load_prompt": lambda _: (prompt_fn, binding),
            "build_grader_payload": grader_fn,
            "request_contract_sha256": runner.canonical_json_sha256}
    target_receipts, intents, grades, reader_runs = [], [], [], []
    expected_correct = {"weak_first_hit": 10, "strong_rule_based": 20,
                        "scope_aware": 30, "temporal_importance": 25}
    dispatch_times = []
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for rep in range(1, 4):
        for strategy in runner.EXPECTED_ORDER_BY_REPETITION[str(rep)]:
            case_results = []
            for index, case in enumerate(subset):
                qid = case["question_id"]
                answer = f"target response {rep} {strategy} {qid}"
                response_sha = runner.sha256_bytes(answer.encode())
                payload = {"model": runner.EXPECTED_MODEL, "provider": {"require_parameters": True}}
                payload_sha = runner.canonical_json_sha256(payload)
                key = (rep, strategy, qid)
                target_receipts.append({
                    "repetition": rep, "strategy": strategy, "question_id": qid,
                    "response": {"model": runner.EXPECTED_MODEL, "response_text": answer},
                    "response_sha256": response_sha, "verified_request_payload": payload,
                    "request_payload_sha256": payload_sha, "request_contract_attempts": [],
                })
                intents.append({"repetition": rep, "strategy": strategy, "question_id": qid,
                                "status": "completed", "request_payload_sha256": payload_sha,
                                "response_sha256": response_sha, "attempts": []})
                case_result = {"case_id": qid, "category": case["question_type"], "response_text": answer}
                case_results.append(case_result)
                prompt = prompt_fn(case["question_type"], case["question"], case["answer"], answer,
                                   abstention=qid.endswith("_abs"))
                grader_payload = grader_fn(runner.EXPECTED_MODEL, prompt)
                correct = index < expected_correct[strategy]
                grades.append({
                    "repetition": rep, "strategy": strategy, "question_id": qid,
                    "target_response_sha256": response_sha,
                    "upstream_prompt_sha256": runner.sha256_bytes(prompt.encode()),
                    "request_payload": grader_payload,
                    "request_payload_sha256": runner.canonical_json_sha256(grader_payload),
                    "verdict_usable": True, "raw_verdict": "yes" if correct else "no",
                    "correct": correct, "finish_reason": "stop",
                })
            for batch_index, start_index in enumerate((0, 15)):
                batch = case_results[start_index:start_index + 15]
                reader_runs.append({"repetition": rep, "strategy": strategy,
                                    "batch_index": batch_index,
                                    "result": {"conditions": [{"strategy": strategy, "cases": batch}]}})
    for i in range(720):
        dispatch_times.append((started + timedelta(seconds=65 + 4 * i)).isoformat(timespec="microseconds"))
    run = {
        "format": "proposal-c-four-arm-live-run-v1",
        "protocol_id": protocol["id"], "protocol_sha256": inputs["protocol_sha256"],
        "subset_sha256": inputs["subset_sha256"],
        "target_configuration": {"provider": runner.EXPECTED_PROVIDER, "model": runner.EXPECTED_MODEL,
                                 "strategies": runner.EXPECTED_STRATEGIES,
                                 "repetitions": runner.EXPECTED_REPETITIONS,
                                 "case_count": runner.EXPECTED_CASE_COUNT},
        "source_manifest_sha256": "manifest", "oracle_source_sha256": "oracle",
        "source_revision": "fixture", "upstream_binding": binding,
        "target_receipts": target_receipts, "target_call_intents": intents,
        "reader_runs": reader_runs, "grades": grades,
        "status": "complete_automatic_collection", "estimated_cost_usd": 0.36,
        "usage_based_cost_estimate_usd": 0.35, "max_cost_usd": 0.40,
        "provider_dispatch_starts_utc": dispatch_times,
        "pacing_sessions": [{"session_id": "fixture", "started_at_utc": started.isoformat(),
                             "request_starts_utc": dispatch_times}],
        "compatibility_limitations": [],
    }
    return inputs, run, deps


class FourArmV7Tests(unittest.TestCase):
    def test_preparer_freezes_same_subset_and_fixed_four_arm_design_without_calls(self):
        output = ROOT / "artifacts/local" / f"v7-test-{next(tempfile._get_candidate_names())}"
        try:
            result = preparer.prepare(ROOT, output)
            self.assertEqual(result["case_count"], 30)
            self.assertEqual(result["planned_target_requests"], 360)
            self.assertEqual(result["planned_grader_requests"], 360)
            self.assertEqual(result["planned_provider_requests_total"], 720)
            self.assertEqual(result["max_estimated_cost_usd"], 0.40)
            self.assertEqual(result["model_calls_made"], 0)
            self.assertEqual((output / "longmemeval-subset.json").read_bytes(),
                             (ROOT / preparer.V6_DIR / "longmemeval-subset.json").read_bytes())
            validated = runner.validate_frozen_inputs(ROOT, output)
            self.assertEqual(validated["protocol_sha256"], result["protocol_sha256"])
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_four_arm_analyzer_uses_frozen_denominator_and_recommends_only_complete_winner(self):
        inputs, run, deps = _make_analysis_fixture()
        analysis, summary = analyzer.validate_and_analyze(inputs, run, deps)
        self.assertEqual(summary["recommendation"], "scope_aware")
        self.assertEqual(analysis["coverage"]["target_answers_expected"], 360)
        self.assertEqual(analysis["coverage"]["usable_grader_decisions"], 360)
        self.assertEqual(analysis["scores"]["per_strategy"]["scope_aware"]["strict_pass_rate_percent"], 100.0)
        self.assertEqual(len(analysis["scores"]["all_pairwise_per_repetition"]), 18)
        self.assertTrue(analysis["request_pacing"]["verified"])
        partial = copy.deepcopy(run)
        partial["status"] = "paused_cost_ceiling"
        analysis_partial, summary_partial = analyzer.validate_and_analyze(inputs, partial, deps)
        self.assertFalse(analysis_partial["coverage"]["complete_for_winner_rule"])
        self.assertEqual(summary_partial["recommendation"], "no_clear_winner")

    def test_paced_post_enforces_initial_cooldown_and_start_spacing(self):
        class Clock:
            now = 0.0
            starts = []
            @classmethod
            def monotonic(cls):
                return cls.now
            @classmethod
            def sleep(cls, seconds):
                cls.now += seconds

        class FakeHttpx:
            @staticmethod
            def post(*args, **kwargs):
                Clock.starts.append(Clock.now)
                Clock.now += 0.25
                return "ok"

        report = {}
        with patch.object(runner.time, "monotonic", Clock.monotonic), patch.object(runner.time, "sleep", Clock.sleep):
            original, paced = runner._paced_post(FakeHttpx, report, lambda: None)
            self.assertEqual(paced("https://openrouter.ai/api/v1/chat/completions"), "ok")
            self.assertEqual(paced("https://openrouter.ai/api/v1/chat/completions"), "ok")
        self.assertEqual(Clock.starts[0], 65.0)
        self.assertGreaterEqual(Clock.starts[1] - Clock.starts[0], 4.0)
        self.assertEqual(len(report["pacing_sessions"][0]["request_starts_utc"]), 2)

    def test_resume_rejects_budget_raise_and_cost_reservation_pauses_before_dispatch(self):
        inputs, _, _ = _make_analysis_fixture()
        report = {"format": "proposal-c-four-arm-live-run-v1", "protocol_id": runner.EXPECTED_PROTOCOL_ID,
                  "protocol_sha256": "protocol", "subset_sha256": "subset", "max_cost_usd": 0.40,
                  "estimated_cost_usd": 0.20, "usage_based_cost_estimate_usd": 0.2,
                  "target_configuration": {"provider": runner.EXPECTED_PROVIDER, "model": runner.EXPECTED_MODEL,
                                           "strategies": runner.EXPECTED_STRATEGIES,
                                           "repetitions": 3, "case_count": 30},
                  "target_receipts": [], "target_call_intents": [], "grades": [], "status": "running"}
        runner._validate_resume_state(report, inputs, 0.40)
        with self.assertRaises(runner.FrozenInputError):
            runner._validate_resume_state(report, inputs, 0.41)
        budget = {"estimated_cost_usd": 0.399, "max_cost_usd": 0.40, "status": "running"}
        with self.assertRaises(RuntimeError):
            runner._ensure_cost(budget, 0.002, "grader")
        self.assertEqual(budget["status"], "paused_cost_ceiling")


if __name__ == "__main__":
    unittest.main()
