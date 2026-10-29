"""Contract tests for preparing a frozen LongMemEval candidate C release."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from scripts.longmemeval_grading import build_openrouter_grader_payload

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_phase4_c_candidate", ROOT / "scripts/prepare_phase4_c_candidate.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write(path: Path, value) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, separators=(",", ":")).encode()
    path.write_bytes(data)
    return data


class PreparePhase4CCandidateTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        release = root / MODULE.RELEASE
        upstream = root / MODULE.UPSTREAM
        (root / "backend/app").mkdir(parents=True)
        (root / "backend/app/example.py").write_text("# fixture\n", encoding="utf-8")
        (root / "scripts").mkdir()
        (root / "scripts/run_phase4_c.py").write_text("# fixture\n", encoding="utf-8")
        (root / "scripts/longmemeval_grading.py").write_text("# fixture\n", encoding="utf-8")
        (root / "scripts/prepare_phase4_c_candidate.py").write_text("# fixture\n", encoding="utf-8")
        categories = sorted(MODULE.CATEGORIES)
        all_cases = [{"question_id": f"Q{index:03}", "question_type": categories[index % len(categories)],
                      "question": "synthetic fixture", "answer": "fixture answer",
                      "haystack_session_ids": [f"S{index:03}"]}
                     for index in range(500)]
        oracle_path = release / "source/longmemeval_oracle.json"
        raw = _write(oracle_path, all_cases)
        source_manifest = {"source": "fixture", "license": "MIT per fixture dataset card",
                           "files": [{"file": str(oracle_path.relative_to(root)), "commit": "revision",
                                      "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]}
        _write(release / "source-manifest.json", source_manifest)

        records = []
        for index in range(14):
            case = all_cases[index]
            file_path = release / f"prepared/candidate-held-out/{case['question_id']}-oracle.json"
            item_bytes = _write(file_path, [case])
            records.append({"split": "candidate-held-out", "category": case["question_type"],
                            "question_id": case["question_id"],
                            "evidence_session_ids": case["haystack_session_ids"],
                            "files": [{"mode": "oracle", "file": str(file_path.relative_to(root)),
                                       "bytes": len(item_bytes), "sha256": hashlib.sha256(item_bytes).hexdigest()}]})
        _write(release / "prepared-release.json", {
            "selection": "No answer or target output used for selection.", "records": records,
        })
        _write(release / "execution-manifest.json", {
            "candidate_held_out_executions": 0, "semantic_scores": 0, "human_labels": 0,
        })
        source = upstream / "evaluate_qa.py"
        upstream_bytes = b"def get_anscheck_prompt(task, question, answer, response, abstention):\n    return question\n"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(upstream_bytes)
        _write(upstream / "source-binding.json", {"source_sha256": hashlib.sha256(upstream_bytes).hexdigest()})
        (upstream / "LICENSE").write_text("MIT", encoding="utf-8")

    def test_freezes_only_verified_preexecution_candidate_cases_without_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            result = MODULE.prepare(root, root / "artifacts/candidate")
            protocol = json.loads((root / "artifacts/candidate/protocol.json").read_text())
            subset = json.loads((root / "artifacts/candidate/longmemeval-subset.json").read_text())
        self.assertEqual(len(subset), 14)
        self.assertEqual(protocol["source"]["oracle_record_count"], 500)
        self.assertEqual(protocol["target"]["planned_target_requests"], 84)
        self.assertEqual(result["planned_scorer_requests"], 84)
        self.assertEqual(result["model_calls_made"], 0)

    def test_scorer_payload_leaves_openrouter_endpoint_routing_unconstrained(self) -> None:
        payload = build_openrouter_grader_payload("openai/gpt-6-luna", "Answer yes or no.")
        self.assertEqual(payload["model"], "openai/gpt-6-luna")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertNotIn("provider", payload)

    def test_partial_run_amendment_records_failed_attempts_before_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            prior_path = root / "artifacts/phase4-c-v3/C-live.json"
            prior_path.parent.mkdir(parents=True)
            prior_path.write_text(json.dumps({
                "status": "failed",
                "error_type": "AttributeError",
                "protocol_sha256": "prior-protocol-hash",
                "target_receipts": [{} for _ in range(14)],
                "grades": [{"verdict_usable": True,
                            "attempts": [{"attempt": 1, "http_status": 200}],
                            "raw_verdict": "yes"},
                           {"verdict_usable": False,
                            "attempts": [{"attempt": 1, "http_status": 404},
                                         {"attempt": 2, "http_status": 200}],
                            "error_response": "provider routing 404"}],
            }))
            result = MODULE.prepare(root, root / "artifacts/phase4-c-v4", prior_path)
            protocol = json.loads((root / "artifacts/phase4-c-v4/protocol.json").read_text())
        amendment = protocol["protocol_amendment"]
        self.assertEqual(amendment["target_responses_before_amendment"], 14)
        self.assertEqual(amendment["usable_grades_before_amendment"], 1)
        self.assertEqual(amendment["unusable_grades_before_amendment"], 1)
        self.assertIn("unified_scorer_control", amendment["kind"])
        self.assertEqual(result["model_calls_made"], 0)

    def test_refuses_to_relabel_an_executed_holdout_as_unused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            execution_path = root / MODULE.RELEASE / "execution-manifest.json"
            execution_path.write_text(json.dumps({"candidate_held_out_executions": 1,
                                                  "semantic_scores": 0, "human_labels": 0}))
            with self.assertRaisesRegex(ValueError, "outcomes already exist"):
                MODULE.prepare(root, root / "artifacts/candidate")

    def test_refuses_source_bytes_that_do_not_match_the_frozen_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            source = root / MODULE.RELEASE / "source/longmemeval_oracle.json"
            source.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match its manifest"):
                MODULE.prepare(root, root / "artifacts/candidate")


if __name__ == "__main__":
    unittest.main()
