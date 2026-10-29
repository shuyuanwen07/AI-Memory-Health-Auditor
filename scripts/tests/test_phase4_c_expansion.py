"""Focused offline checks for the frozen v6 runner and outcome analyzer."""
from __future__ import annotations

import importlib.util
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_phase4_c_expansion as runner
import analyze_phase4_c_expansion as analyzer


def _sha(value: str) -> str:
    return runner.sha256_bytes(value.encode("utf-8"))


def _analysis_fixture():
    subset = []
    for category, count in runner.EXPECTED_CATEGORY_COUNTS.items():
        for index in range(count):
            suffix = "_abs" if category == "abstention" else ""
            subset.append({
                "question_id": f"case-{category}-{index}{suffix}",
                "question_type": "single-session-user" if category == "abstention" else category,
                "question": f"question {category} {index}",
                "answer": f"answer {category} {index}",
                "haystack_session_ids": [f"h-{category}-{index}"],
                "answer_session_ids": [f"a-{category}-{index}"],
            })
    protocol = {
        "id": runner.EXPECTED_PROTOCOL_ID,
        "source": {"revision": "fixture-revision", "source_manifest_sha256": "source-manifest-hash",
                   "oracle_source_sha256": "oracle-hash"},
        "selection": {"batch_size": runner.EXPECTED_BATCH_SIZE, "excluded_prior_release": {}},
        "C": {"judge_model": runner.EXPECTED_MODEL},
        "budget": {"max_estimated_cost_usd": 1.0},
        "analysis": {
            "primary_outcome": "Pinned upstream GPT-6 Luna pass rate on 30 new cases, paired by repetition.",
            "selection_rule": "Recommend Strong if pooled accuracy is higher and it wins at least 2/3 comparisons; otherwise no clear winner.",
        },
        "app_source": {"scripts/run_phase4_c_expansion.py": "runner-v6"},
    }
    inputs = {
        "protocol": protocol,
        "protocol_sha256": "protocol-hash",
        "subset_sha256": "subset-hash",
        "subset": subset,
        "directory": Path("/fixture/v6"),
        "upstream_binding": {"revision": "fixture-revision"},
    }
    prompt_function = lambda category, question, answer, response, abstention=False: (
        f"{category}|{question}|{answer}|{response}|{abstention}"
    )
    def grader_payload(model, prompt):
        return {"model": model, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "max_tokens": 128, "reasoning": {"effort": "none"}}
    hash_contract = runner.canonical_json_sha256
    dependencies = {
        "load_prompt": lambda directory: (prompt_function, {"revision": "fixture-revision"}),
        "build_grader_payload": grader_payload,
        "request_contract_sha256": hash_contract,
    }

    receipts, intents, grades, reader_runs = [], [], [], []
    reps_correct = {
        "weak_first_hit": [12, 12, 12],
        "strong_rule_based": [20, 18, 21],
    }
    batches = runner._iter_batches(subset, runner.EXPECTED_BATCH_SIZE)
    for repetition in range(1, 4):
        for strategy in runner.EXPECTED_STRATEGIES:
            correctness = reps_correct[strategy][repetition - 1]
            case_results = []
            for case_index, case in enumerate(subset):
                qid = case["question_id"]
                text = f"answer for {qid}"
                correct = case_index < correctness
                target_payload = {"model": runner.EXPECTED_MODEL,
                                  "messages": [{"role": "user", "content": qid}],
                                  "provider": {"require_parameters": True, "allow_fallbacks": False}}
                payload_hash = hash_contract(target_payload)
                response_hash = _sha(text)
                receipts.append({
                    "repetition": repetition, "strategy": strategy, "question_id": qid,
                    "response": {"model": runner.EXPECTED_MODEL, "response_text": text,
                                 "execution_metadata": {"latency_ms": 120 + case_index,
                                                        "request_contract": {"payload_sha256": payload_hash}}},
                    "verified_request_payload": target_payload,
                    "request_payload_sha256": payload_hash,
                    "response_sha256": response_hash,
                    "request_contract_attempts": [{"attempt_index": 0,
                                                    "request_contract_sha256": "attempt-contract"}],
                    "input_tokens": 100 + case_index, "output_tokens": 20,
                })
                intents.append({
                    "repetition": repetition, "strategy": strategy, "question_id": qid,
                    "status": "completed", "request_payload_sha256": payload_hash,
                    "response_sha256": response_hash,
                    "attempts": [{"attempt_index": 0, "status": "response", "http_status": 200,
                                  "request_contract_sha256": "attempt-contract"}],
                })
                case_result = {
                    "case_id": qid, "category": case["question_type"], "response_text": text,
                    "execution_metadata": {"latency_ms": 120 + case_index},
                    "lexical_match": case_index % 2 == 0,
                }
                case_results.append(case_result)
                prompt = prompt_function(case["question_type"], case["question"], case["answer"],
                                         text, abstention=qid.endswith("_abs"))
                payload = grader_payload(runner.EXPECTED_MODEL, prompt)
                raw_verdict = "yes" if correct else "no"
                grades.append({
                    "repetition": repetition, "strategy": strategy, "question_id": qid,
                    "target_response_sha256": response_hash,
                    "upstream_prompt_sha256": _sha(prompt),
                    "request_payload": payload,
                    "request_payload_sha256": runner.canonical_json_sha256(payload),
                    "reported_model": runner.EXPECTED_MODEL,
                    "verdict_usable": True, "raw_verdict": raw_verdict,
                    "correct": correct, "finish_reason": "stop", "usage": {"prompt_tokens": 50, "completion_tokens": 1},
                    "attempts": [],
                })
            for batch_index, (_, batch) in enumerate(batches):
                batch_ids = [case["question_id"] for case in batch]
                batch_results = [case_result for case_result in case_results if case_result["case_id"] in batch_ids]
                reader_runs.append({
                    "repetition": repetition, "strategy": strategy, "batch_index": batch_index,
                    "question_ids": batch_ids,
                    "result": {"provider": runner.EXPECTED_PROVIDER, "model": runner.EXPECTED_MODEL,
                               "conditions": [{"strategy": strategy, "cases": batch_results}]},
                })
    run = {
        "format": "proposal-c-expansion-live-run-v1",
        "protocol_id": protocol["id"], "protocol_sha256": inputs["protocol_sha256"],
        "subset_sha256": inputs["subset_sha256"],
        "target_configuration": {
            "case_count": runner.EXPECTED_CASE_COUNT,
            "provider": runner.EXPECTED_PROVIDER,
            "model": runner.EXPECTED_MODEL,
            "strategies": runner.EXPECTED_STRATEGIES,
            "repetitions": runner.EXPECTED_REPETITIONS,
        },
        "source_manifest_sha256": protocol["source"]["source_manifest_sha256"],
        "oracle_source_sha256": protocol["source"]["oracle_source_sha256"],
        "source_revision": protocol["source"]["revision"],
        "upstream_binding": inputs["upstream_binding"],
        "target_receipts": receipts, "target_call_intents": intents,
        "reader_runs": reader_runs, "grades": grades,
        "status": "complete_automatic_collection", "estimated_cost_usd": 0.8,
        "usage_based_cost_estimate_usd": 0.5, "max_cost_usd": 1.0,
        "billing_uncertain": False, "compatibility_limitations": [],
    }
    return inputs, run, dependencies


class Phase4CExpansionTests(unittest.TestCase):
    def test_abstention_stratum_and_strict_grader_parser(self):
        self.assertEqual(runner._case_category({"question_id": "case_abs", "question_type": "single-session-user"}), "abstention")
        self.assertEqual(runner._score_from_raw("yes", "stop"), (True, True))
        self.assertEqual(runner._score_from_raw("No.", "stop"), (False, True))
        self.assertEqual(runner._score_from_raw("yes because", "stop"), (None, False))
        self.assertEqual(runner._score_from_raw("yes", "length"), (None, False))

    def test_resume_blocks_ambiguous_provider_dispatch_and_rejects_ceiling_raise(self):
        inputs, _, _ = _analysis_fixture()
        inputs["protocol_sha256"] = "p"
        inputs["subset_sha256"] = "s"
        base = {"protocol_id": runner.EXPECTED_PROTOCOL_ID, "protocol_sha256": "p", "subset_sha256": "s",
                "max_cost_usd": 1.0, "estimated_cost_usd": 0.3,
                "target_receipts": [], "target_call_intents": [], "grades": [], "status": "running"}
        ambiguous = dict(base, target_call_intents=[{
            "repetition": 1, "strategy": "weak_first_hit", "question_id": inputs["subset"][0]["question_id"],
            "status": "unknown", "attempts": [{"status": "pending"}],
        }])
        with self.assertRaises(runner.ResumeBlockedError):
            runner._validate_resume_state(ambiguous, inputs, 1.0)
        with self.assertRaises(runner.FrozenInputError):
            runner._validate_resume_state(base, inputs, 1.01)

    def test_target_routing_environment_and_pre_send_contract_mismatch_are_rejected(self):
        protocol = {"target": {}}
        runner._validate_target_provider_environment(protocol, "")
        with self.assertRaisesRegex(runner.FrozenInputError, "OPENROUTER_PROVIDER"):
            runner._validate_target_provider_environment(protocol, "InjectedRoute")
        bound = {"target": {"provider_options": {"require_parameters": True,
                                                  "allow_fallbacks": False, "only": ["PinnedRoute"]}}}
        runner._validate_target_provider_environment(bound, "PinnedRoute")
        with self.assertRaises(runner.FrozenInputError):
            runner._validate_target_provider_environment(bound, "OtherRoute")

        intent = {"request_payload_sha256": "frozen-payload-hash", "attempts": []}
        report = {"estimated_cost_usd": 0.0, "max_cost_usd": 1.0}
        with self.assertRaisesRegex(runner.FrozenInputError, "blocked before dispatch"):
            runner._execution_attempt_observer(report, intent, lambda: None, 0.01)({
                "phase": "before_send", "attempt_index": 0,
                "request_contract": {"payload_sha256": "injected-payload-hash"},
            })
        self.assertEqual(report["estimated_cost_usd"], 0.0)
        self.assertEqual(intent["attempts"], [])

    def test_protocol_sidecar_is_mandatory_and_fixed_reader_configuration_is_enforced(self):
        preparer_spec = importlib.util.spec_from_file_location(
            "prepare_phase4_c_expansion", ROOT / "scripts/prepare_phase4_c_expansion.py"
        )
        assert preparer_spec and preparer_spec.loader
        preparer = importlib.util.module_from_spec(preparer_spec)
        preparer_spec.loader.exec_module(preparer)
        fixture_spec = importlib.util.spec_from_file_location(
            "prepare_phase4_c_expansion_tests", ROOT / "scripts/tests/test_prepare_phase4_c_expansion.py"
        )
        assert fixture_spec and fixture_spec.loader
        fixture_module = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixture_module)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = fixture_module.PreparePhase4CExpansionTests()
            fixture._fixture(root)
            prior_dir = root / preparer.PRIOR_V5
            prior_subset = prior_dir / "longmemeval-subset.json"
            prior_protocol_path = prior_dir / "protocol.json"
            prior_run_path = prior_dir / "C-live.json"
            prior_protocol = json.loads(prior_protocol_path.read_text(encoding="utf-8"))
            prior_protocol_sha = analyzer.sha256_bytes(prior_protocol_path.read_bytes())
            prior_subset_sha = analyzer.sha256_bytes(prior_subset.read_bytes())
            prior_analysis_path = prior_dir / "analysis.json"
            prior_analysis = {"source": {
                "run_sha256": analyzer.sha256_bytes(prior_run_path.read_bytes()),
                "protocol_sha256": prior_protocol_sha,
                "subset_sha256": prior_subset_sha,
            }}
            prior_analysis_path.write_text(json.dumps(prior_analysis), encoding="utf-8")

            test_paths = list((ROOT / "scripts/tests").glob("test_*phase4_c_expansion*.py"))
            (root / "scripts/tests").mkdir(parents=True, exist_ok=True)
            for source_path in test_paths:
                destination = root / "scripts/tests" / source_path.name
                destination.write_bytes(source_path.read_bytes())

            directory = root / "artifacts/v6"
            preparer.prepare(root, directory)
            runner.validate_frozen_inputs(root, directory)
            frozen_analysis = (root / preparer.PRIOR_V5 / "analysis.json").read_bytes()
            (root / preparer.PRIOR_V5 / "analysis.json").write_bytes(frozen_analysis + b" ")
            with self.assertRaisesRegex(runner.FrozenInputError, "v5 analysis file has changed"):
                runner.validate_frozen_inputs(root, directory)
            (root / preparer.PRIOR_V5 / "analysis.json").write_bytes(frozen_analysis)

            sidecar = directory / "protocol.sha256"
            sidecar.unlink()
            with self.assertRaisesRegex(runner.FrozenInputError, "requires its protocol.sha256"):
                runner.validate_frozen_inputs(root, directory)
            sidecar.write_text(analyzer.sha256_bytes((directory / "protocol.json").read_bytes()) + "  protocol.json\n")

            protocol_path = directory / "protocol.json"
            frozen_protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            mutations = [
                ("temperature", 0.25),
                ("random_seed", 43),
                ("target_memory_capacity", 49),
                ("reader_configuration", "weak"),
                ("target_memory_profile", {**frozen_protocol["target"]["target_memory_profile"],
                                            "output_token_limit": 1024}),
            ]
            for key, changed_value in mutations:
                protocol = json.loads(json.dumps(frozen_protocol))
                protocol["target"][key] = changed_value
                protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                sidecar.write_text(analyzer.sha256_bytes(protocol_path.read_bytes()) + "  protocol.json\n")
                with self.assertRaisesRegex(runner.FrozenInputError, "differs from the frozen experiment condition"):
                    runner.validate_frozen_inputs(root, directory)

    def test_analyzer_reconciles_30_case_paired_scores_and_reports_tradeoffs(self):
        inputs, run, dependencies = _analysis_fixture()
        result = analyzer.validate_and_analyze(inputs, run, dependencies)
        self.assertEqual(result["scores"]["pooled"]["weak_first_hit"]["correct"], 36)
        self.assertEqual(result["scores"]["pooled"]["weak_first_hit"]["expected"], 90)
        self.assertEqual(result["scores"]["pooled"]["strong_rule_based"]["correct"], 59)
        self.assertEqual(result["decision"]["recommended_strategy"], "strong_rule_based")
        self.assertEqual(result["decision"]["strong_wins_of_three_repetition_comparisons"], 3)
        self.assertTrue(result["decision"]["collection_complete_for_predeclared_rule"])
        self.assertIn("category_level", result["scores"])
        self.assertIn("lexical_proxy_separate", result["scores"])
        self.assertIn("target_latency_ms_mean_and_median", result["operational_tradeoffs"])
        self.assertEqual(result["operational_tradeoffs"]["target_token_usage"]["weak_first_hit"]["grader_input_sum"], 4500)
        self.assertEqual(result["operational_tradeoffs"]["provider_request_failures"]["target_answers_missing"], 0)

        incomplete_run = copy.deepcopy(run)
        incomplete_run["grades"][-1]["verdict_usable"] = False
        incomplete_run["grades"][-1]["correct"] = None
        incomplete = analyzer.validate_and_analyze(inputs, incomplete_run, dependencies)
        self.assertEqual(incomplete["decision"]["recommended_strategy"], "no_clear_winner")
        self.assertFalse(incomplete["decision"]["collection_complete_for_predeclared_rule"])
        self.assertFalse(incomplete["decision"]["rule_passed"])

    def test_analyzer_rejects_corrupted_answer_hash_and_summary_keeps_44_case_secondary(self):
        inputs, run, dependencies = _analysis_fixture()
        run["target_receipts"][0]["response_sha256"] = "bad-hash"
        with self.assertRaisesRegex(runner.FrozenInputError, "target answer"):
            analyzer.validate_and_analyze(inputs, run, dependencies)

        inputs, run, dependencies = _analysis_fixture()
        v6 = analyzer.validate_and_analyze(inputs, run, dependencies)
        v6["source_code_sha256"] = {"scripts/run_phase4_c_expansion.py": "new-runner"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            v5_dir = root / "artifacts/local/phase4-c-openrouter-20261027-v5"
            v5_dir.mkdir(parents=True)
            old_run = v5_dir / "C-live.json"
            old_run.write_text("{\"status\":\"complete\"}\n", encoding="utf-8")
            old_run_sha = analyzer.sha256_bytes(old_run.read_bytes())
            old_subset = v5_dir / "longmemeval-subset.json"
            old_subset.write_text("[]\n", encoding="utf-8")
            old_subset_sha = analyzer.sha256_bytes(old_subset.read_bytes())
            v5_protocol = {"id": "v5", "app_source": {"scripts/run_phase4_c.py": "old"},
                           "source_files": {"benchmark_subset_sha256": old_subset_sha}}
            v5_protocol_path = v5_dir / "protocol.json"
            v5_protocol_path.write_text(json.dumps(v5_protocol), encoding="utf-8")
            v5_protocol_sha = analyzer.sha256_bytes(v5_protocol_path.read_bytes())
            v5 = {
                "source": {"upstream_source_revision": "fixture-revision", "run_sha256": old_run_sha,
                           "protocol_sha256": v5_protocol_sha, "subset_sha256": old_subset_sha},
                "collection": {"billing_estimate_usd_excluding_unknown_failed_attempt_billing": 0.08,
                               "failed_attempt_billing_uncertain": True},
                "scores": {
                    "aggregate": {
                        "weak_first_hit": {"correct": 12, "total": 42, "accuracy_percent": 28.57},
                        "strong_rule_based": {"correct": 35, "total": 42, "accuracy_percent": 83.33},
                    },
                    "per_repetition": [
                        {"repetition": rep, "strategy": strategy, "correct": correct, "total": 14,
                         "accuracy_percent": round(correct * 100 / 14, 2)}
                        for rep, weak, strong in ((1, 4, 12), (2, 4, 11), (3, 4, 12))
                        for strategy, correct in (("weak_first_hit", weak), ("strong_rule_based", strong))
                    ],
                },
            }
            (v5_dir / "analysis.json").write_text(json.dumps(v5), encoding="utf-8")
            v6["preserved_v5_binding"] = {
                "prior_v5_analysis_path": str((v5_dir / "analysis.json").relative_to(root)),
                "prior_v5_analysis_sha256": analyzer.sha256_bytes((v5_dir / "analysis.json").read_bytes()),
                "prior_v5_analysis_source_run_sha256": old_run_sha,
                "prior_v5_run_sha256": old_run_sha,
                "prior_v5_run_path": str(old_run.relative_to(root)),
                "prior_v5_protocol_path": str(v5_protocol_path.relative_to(root)),
                "prior_v5_subset_path": str(old_subset.relative_to(root)),
                "prior_v5_protocol_sha256": v5_protocol_sha,
                "prior_v5_subset_sha256": old_subset_sha,
            }
            summary = analyzer.build_comparison_summary(root, v6)
            (v5_dir / "analysis.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(runner.FrozenInputError, "analysis used for the 44-case"):
                analyzer.build_comparison_summary(root, v6)
        self.assertEqual(summary["combined_44_case_secondary"]["cases_per_repetition"], 44)
        self.assertEqual(summary["combined_44_case_secondary"]["pooled_expected_answers_per_strategy"], 132)
        self.assertEqual(summary["combined_44_case_secondary"]["pooled_scores"]["weak_first_hit"]["total"], 132)
        self.assertTrue(summary["combined_44_case_secondary"]["source_paths_only_in_v5_snapshot"])


if __name__ == "__main__":
    unittest.main()
