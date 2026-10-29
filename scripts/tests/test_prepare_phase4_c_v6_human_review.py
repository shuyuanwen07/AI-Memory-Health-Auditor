"""Offline tests for the v6 blinded human answer-review packet."""
from __future__ import annotations

import csv
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_phase4_c_v6_human_review", ROOT / "scripts/prepare_phase4_c_v6_human_review.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class PreparePhase4CV6HumanReviewTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        subset = []
        for index in range(MODULE.EXPECTED_CASES):
            subset.append({
                "question_id": f"LME-{index:03}",
                "question": f"Synthetic question {index}?",
                "answer": f"Official reference {index}.",
                "answer_session_ids": [f"S-{index:03}"],
                "haystack_session_ids": [f"S-{index:03}", f"F-{index:03}"],
                "haystack_sessions": [
                    [{"role": "user", "content": f"Relevant source fact {index}."}],
                    [{"role": "assistant", "content": f"Filler context {index}."}],
                ],
            })

        reader_runs, receipts, grades = [], [], []
        for repetition in range(1, MODULE.EXPECTED_REPETITIONS + 1):
            for strategy in sorted(MODULE.EXPECTED_STRATEGIES):
                case_results = []
                for case in subset:
                    qid = case["question_id"]
                    response = f"Synthetic target answer for {qid}, trial {repetition}."
                    case_results.append({"case_id": qid, "response_text": response})
                    receipts.append({
                        "repetition": repetition,
                        "strategy": strategy,
                        "question_id": qid,
                        "response": {
                            "response_text": response,
                            "run_id": f"run-{repetition}-{strategy}",
                            "response_id": f"response-{repetition}-{strategy}-{qid}",
                        },
                    })
                    grades.append({
                        "repetition": repetition,
                        "strategy": strategy,
                        "question_id": qid,
                        "autoeval_label": "yes" if strategy == "strong_rule_based" else "no",
                        "reported_model": "fixture-grader",
                        "verdict_usable": True,
                    })
                reader_runs.append({
                    "repetition": repetition,
                    "strategy": strategy,
                    "result": {"conditions": [{"cases": case_results}]},
                })
        run = {
            "protocol_id": MODULE.EXPECTED_PROTOCOL_ID,
            "target_configuration": {
                "strategies": sorted(MODULE.EXPECTED_STRATEGIES),
                "repetitions": MODULE.EXPECTED_REPETITIONS,
            },
            "reader_runs": reader_runs,
            "target_receipts": receipts,
            "grades": grades,
        }
        subset_path = root / "longmemeval-subset.json"
        run_path = root / "C-live.json"
        _write(subset_path, subset)
        _write(run_path, run)
        return run_path, subset_path

    def test_creates_180_shuffled_blind_rows_and_private_key_without_mutating_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path, subset_path = self._fixture(root)
            run_before = run_path.read_bytes()
            subset_before = subset_path.read_bytes()
            output = root / "packet"
            manifest = MODULE.prepare(run_path, subset_path, output, seed=1234)
            with (output / "blind-review.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            key = json.loads((output / "review-key-private.json").read_text(encoding="utf-8"))
            instructions = (output / "BLIND_REVIEW_INSTRUCTIONS.md").read_text(encoding="utf-8")
            public_text = (output / "blind-review.csv").read_text(encoding="utf-8-sig")
            key_mode = stat.S_IMODE((output / "review-key-private.json").stat().st_mode)
            output_json = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            run_after = run_path.read_bytes()
            subset_after = subset_path.read_bytes()

        self.assertEqual(len(rows), 180)
        self.assertEqual(len({row["blind_item_id"] for row in rows}), 180)
        self.assertEqual(len(key["mapping"]), 180)
        self.assertEqual(len({row["question_id"] for row in key["mapping"]}), 30)
        self.assertTrue(all(sum(item["question_id"] == qid for item in key["mapping"]) == 6
                            for qid in {item["question_id"] for item in key["mapping"]}))
        self.assertEqual(set(rows[0]), {
            "blind_item_id", "question", "source_evidence", "benchmark_reference_answer",
            "target_response", "human_judgment", "rationale",
        })
        self.assertNotIn("strategy", rows[0])
        self.assertNotIn("repetition", rows[0])
        self.assertNotIn("automatic_grader_label", rows[0])
        self.assertNotIn("weak_first_hit", public_text)
        self.assertNotIn("strong_rule_based", public_text)
        self.assertNotIn("fixture-grader", public_text)
        self.assertNotIn("question_id", rows[0])
        self.assertIn("Relevant source fact", rows[0]["source_evidence"])
        self.assertNotIn("S-", rows[0]["source_evidence"])
        self.assertIn("not 180 independent histories", instructions)
        self.assertIn("not 180 independent histories", json.dumps(output_json))
        self.assertEqual(key_mode, 0o600)
        self.assertEqual(run_after, run_before)
        self.assertEqual(subset_after, subset_before)
        self.assertEqual(manifest["review_item_count"], 180)

    def test_rejects_incomplete_run_and_preserves_existing_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path, subset_path = self._fixture(root)
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["target_receipts"].pop()
            _write(run_path, run)
            output = root / "packet"
            with self.assertRaisesRegex(ValueError, "all 180 saved v6 target answers"):
                MODULE.prepare(run_path, subset_path, output, seed=1)

            # A valid second attempt must not replace even a pre-existing file.
            run, _ = self._fixture(root)
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                MODULE.prepare(run, subset_path, output, seed=1)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
