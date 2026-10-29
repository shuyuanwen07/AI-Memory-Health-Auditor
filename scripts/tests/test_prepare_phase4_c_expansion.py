"""Tests for the offline, content-minimising LongMemEval v6 selection freeze."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_phase4_c_expansion", ROOT / "scripts/prepare_phase4_c_expansion.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write(path: Path, value) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(data)
    return data


class PreparePhase4CExpansionTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        release = root / MODULE.RELEASE
        upstream = root / MODULE.UPSTREAM
        (root / "backend/app").mkdir(parents=True)
        (root / "backend/app/example.py").write_text("# fixture\n", encoding="utf-8")
        (root / "scripts").mkdir()
        for name in ("run_phase4_c_expansion.py", "analyze_phase4_c_expansion.py", "longmemeval_grading.py",
                     "prepare_phase4_c_expansion.py"):
            (root / "scripts" / name).write_text("# fixture\n", encoding="utf-8")
        (root / "scripts/tests").mkdir(parents=True)
        for name in ("test_phase4_c_expansion.py", "test_prepare_phase4_c_expansion.py"):
            (root / "scripts/tests" / name).write_text("# fixture\n", encoding="utf-8")

        categories = list(MODULE.CATEGORY_TARGETS)
        assigned = [category for category in categories for _ in range(4)]
        assigned.extend(categories[index % len(categories)] for index in range(500 - len(assigned)))
        # Keep exactly 30 abstention IDs, including four in the prior 28-case release.
        abstention_indices = {0, 1, 2, 3, *range(28, 54)}
        all_cases = []
        for index in range(500):
            category = assigned[index]
            question_id = f"Q{index:03}"
            if index in abstention_indices:
                question_id += "_abs"
                category = "abstention"
                question_type = "single-session-user"
            else:
                question_type = category
            all_cases.append({
                "question_id": question_id,
                "question_type": question_type,
                "question": f"synthetic question {index}",
                "answer": f"private fixture answer {index}",
                "haystack_session_ids": [f"H{index:03}"],
                "answer_session_ids": [f"A{index:03}"],
                "haystack_sessions": [[{"role": "user", "content": f"fixture source {index}"}]],
            })

        oracle_path = release / "source/longmemeval_oracle.json"
        source_bytes = _write(oracle_path, all_cases)
        source_manifest = {
            "source": "official cleaned LongMemEval fixture",
            "license": "MIT per fixture dataset card",
            "files": [{"file": str(oracle_path.relative_to(root)), "commit": "fixture-revision",
                       "bytes": len(source_bytes), "sha256": hashlib.sha256(source_bytes).hexdigest()}],
        }
        _write(release / "source-manifest.json", source_manifest)

        prepared_rows = []
        seen = set()
        for split in ("development", "candidate-held-out"):
            per_category = {category: 0 for category in categories}
            for record in all_cases:
                category = MODULE._category(record)
                if per_category[category] >= 2:
                    continue
                index = int(record["question_id"].split("_")[0][1:])
                if index in seen:
                    continue
                seen.add(index)
                case_path = release / f"prepared/{split}/{record['question_id']}-oracle.json"
                case_bytes = _write(case_path, [record])
                sessions = sorted(set(record["haystack_session_ids"] + record["answer_session_ids"]))
                prepared_rows.append({
                    "split": split, "category": category, "question_id": record["question_id"],
                    "evidence_session_ids": sessions,
                    "files": [{"mode": "oracle", "file": str(case_path.relative_to(root)),
                               "bytes": len(case_bytes), "sha256": hashlib.sha256(case_bytes).hexdigest()}],
                })
                per_category[category] += 1
                if all(count == 2 for count in per_category.values()):
                    break

        _write(release / "prepared-release.json", {
            "selection": "Two per category per split, no answer or target output used for selection.",
            "records": prepared_rows,
        })
        _write(release / "execution-manifest.json", {
            "candidate_held_out_executions": 0, "semantic_scores": 0, "human_labels": 0,
        })

        prior = root / MODULE.PRIOR_V5
        heldout_rows = [r for r in prepared_rows if r["split"] == "candidate-held-out"]
        prior_cases = [record for record in all_cases if record["question_id"] in
                       {r["question_id"] for r in heldout_rows}]
        subset_path = prior / "longmemeval-subset.json"
        subset_bytes = _write(subset_path, prior_cases)
        _write(prior / "protocol.json", {
            "status": "old retained protocol",
            "selection": {"case_count": 14},
            "source_files": {"benchmark_subset_sha256": hashlib.sha256(subset_bytes).hexdigest()},
        })
        prior_run_bytes = _write(prior / "C-live.json", {"status": "complete_automatic_collection"})
        _write(prior / "analysis.json", {"source": {
            "run_sha256": hashlib.sha256(prior_run_bytes).hexdigest(),
        }})

        evaluator = upstream / "evaluate_qa.py"
        evaluator_bytes = b"def get_anscheck_prompt(task, question, answer, response, abstention):\n    return question\n"
        evaluator.parent.mkdir(parents=True, exist_ok=True)
        evaluator.write_bytes(evaluator_bytes)
        _write(upstream / "source-binding.json", {
            "source_sha256": hashlib.sha256(evaluator_bytes).hexdigest(),
        })
        (upstream / "LICENSE").write_text("MIT", encoding="utf-8")

    def test_freezes_30_new_source_disjoint_records_without_calls_or_protocol_text_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            result = MODULE.prepare(root, root / "artifacts/v6")
            directory = root / "artifacts/v6"
            subset = json.loads((directory / "longmemeval-subset.json").read_text())
            protocol = json.loads((directory / "protocol.json").read_text())
            prior = json.loads((root / MODULE.RELEASE / "prepared-release.json").read_text())
            run_bytes_before = (root / MODULE.PRIOR_V5 / "C-live.json").read_bytes()
            run_bytes_after = (root / MODULE.PRIOR_V5 / "C-live.json").read_bytes()
            prior_analysis = json.loads((root / MODULE.PRIOR_V5 / "analysis.json").read_text())
            previous = protocol["selection"]["excluded_prior_release"]
            protocol_text = (directory / "protocol.json").read_text()
            subset_mode = stat.S_IMODE((directory / "longmemeval-subset.json").stat().st_mode)

        self.assertEqual(result["model_calls_made"], 0)
        self.assertNotIn("synthetic question", json.dumps(result))
        self.assertNotIn("private fixture answer", json.dumps(result))
        self.assertEqual(result["case_count"], 30)
        self.assertEqual(result["planned_target_requests"], 180)
        self.assertEqual(result["planned_scorer_requests"], 180)
        self.assertEqual(protocol["id"], MODULE.PROTOCOL_ID)
        self.assertEqual(protocol["selection"]["case_count"], 30)
        self.assertEqual(protocol["selection"]["batch_size"], 15)
        self.assertEqual(protocol["selection"]["strata"], MODULE.CATEGORY_TARGETS)
        self.assertEqual(protocol["budget"]["max_estimated_cost_usd"], 1.00)
        self.assertEqual(protocol["execution"]["batch_case_counts"], [15, 15])
        self.assertIn("2/3", protocol["analysis"]["selection_rule"])
        self.assertEqual(protocol["analyzer_sha256"], protocol["app_source"]["scripts/analyze_phase4_c_expansion.py"])
        self.assertIn("scripts/tests/test_prepare_phase4_c_expansion.py", protocol["app_source"])
        self.assertIn("scripts/tests/test_phase4_c_expansion.py", protocol["app_source"])
        self.assertEqual(previous["prior_v5_analysis_source_run_sha256"],
                         previous["prior_v5_run_sha256"])
        self.assertEqual(previous["prior_v5_analysis_source_run_sha256"],
                         prior_analysis["source"]["run_sha256"])
        self.assertEqual(len(previous["prior_v5_analysis_sha256"]), 64)
        self.assertEqual(len(subset), 30)
        self.assertEqual(len({case["question_id"] for case in subset}), 30)

        prior_ids = {row["question_id"] for row in prior["records"]}
        prior_sessions = {session for row in prior["records"]
                          for session in row["evidence_session_ids"]}
        self.assertFalse(prior_ids.intersection(case["question_id"] for case in subset))
        new_sessions = set()
        for case in subset:
            sessions = set(case["haystack_session_ids"] + case["answer_session_ids"])
            self.assertFalse(new_sessions.intersection(sessions))
            new_sessions.update(sessions)
        self.assertEqual(len(new_sessions), 60)
        self.assertFalse(prior_sessions.intersection(new_sessions))

        selection_rows = protocol["selection"]["selected_cases"]
        self.assertEqual(len(selection_rows), 30)
        for row in selection_rows:
            self.assertEqual(set(row), {"question_id", "category", "record_sha256", "evidence_session_ids"})
            self.assertNotIn("question", row)
            self.assertNotIn("answer", row)
        self.assertNotIn("synthetic question", protocol_text)
        self.assertNotIn("private fixture answer", protocol_text)
        self.assertEqual(subset_mode, 0o600)
        self.assertEqual(run_bytes_after, run_bytes_before)

    def test_selection_is_deterministic_and_refuses_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            selected1, counts1 = MODULE.select_records(
                json.loads((root / MODULE.RELEASE / "source/longmemeval_oracle.json").read_text()),
                {row["question_id"] for row in json.loads((root / MODULE.RELEASE / "prepared-release.json").read_text())["records"]},
                set(),
            )
            selected2, counts2 = MODULE.select_records(
                json.loads((root / MODULE.RELEASE / "source/longmemeval_oracle.json").read_text()),
                {row["question_id"] for row in json.loads((root / MODULE.RELEASE / "prepared-release.json").read_text())["records"]},
                set(),
            )
            self.assertEqual([r["question_id"] for r in selected1], [r["question_id"] for r in selected2])
            self.assertEqual(counts1, counts2)
            destination = root / "artifacts/v6"
            destination.mkdir(parents=True)
            (destination / "keep.txt").write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                MODULE.prepare(root, destination)
            self.assertEqual((destination / "keep.txt").read_text(), "preserve")

    def test_refuses_source_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            (root / MODULE.RELEASE / "source/longmemeval_oracle.json").write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match its byte count and SHA-256"):
                MODULE.prepare(root, root / "artifacts/v6")

    def test_refuses_v5_analysis_bound_to_a_different_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            analysis_path = root / MODULE.PRIOR_V5 / "analysis.json"
            analysis_path.write_text(json.dumps({"source": {"run_sha256": "wrong-run-hash"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not bind the exact frozen C-live run hash"):
                MODULE.prepare(root, root / "artifacts/v6")

    def test_refuses_prepared_session_metadata_that_disagrees_with_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fixture(root)
            path = root / MODULE.RELEASE / "prepared-release.json"
            prepared = json.loads(path.read_text())
            prepared["records"][1]["evidence_session_ids"] = prepared["records"][0]["evidence_session_ids"]
            path.write_text(json.dumps(prepared), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence-session binding differs"):
                MODULE.prepare(root, root / "artifacts/v6")


if __name__ == "__main__":
    unittest.main()
