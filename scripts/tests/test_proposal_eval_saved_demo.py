"""Contract tests for saved exploratory presentation evidence."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.proposal_eval_saved_demo import analyse


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SavedDemoAnalysisTests(unittest.TestCase):
    def test_existing_saved_demo_reconciles_and_keeps_human_limits(self) -> None:
        root = Path(__file__).resolve().parents[2]
        result = analyse(root / "experiments/presentation-demo-20261023/result")
        self.assertEqual(result["answers_and_evaluations"], 48)
        self.assertEqual(result["repetitions_per_strategy"], 3)
        self.assertEqual(result["target_model"], "openai/gpt-6-luna")
        self.assertTrue(result["same_question_content_and_evidence_across_runs"])
        self.assertTrue(result["run_local_test_ids_are_recreated"])
        self.assertEqual(result["strategies"]["strong_rule_based"]["answers_passed"], 13)
        self.assertEqual(result["strategies"]["strong_rule_based"]["pending_judgments"], 7)
        self.assertEqual(result["strategies"]["strong_rule_based"]["app_reported_overall_mean_percent"], 75.0)
        self.assertEqual(result["strategies"]["weak_first_hit"]["answers_passed"], 3)
        self.assertEqual(result["strategies"]["strong_rule_based"]["by_dimension"]["conflict_resolution"]["score_percent"], 0.0)
        self.assertIn("not formal Experiment B", result["scope"])

    def test_rejects_changed_report_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = {"experiment_id": "E1", "scope": "presentation_synthetic_engineering_demo_not_research_gold",
                      "research_evidence": False}
            report_path = directory / "presentation-demo-report.json"
            report_path.write_text(json.dumps(report))
            (directory / "SUMMARY.json").write_text(json.dumps({
                "experiment_id": "E1", "total_answers": 48, "total_evaluations": 48,
            }))
            (directory / "verification.json").write_text(json.dumps({"status": "passed", "report_sha256": "wrong"}))
            with (directory / "experiment.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["experiment_id", "record_type"])
                writer.writeheader()
            (directory / "frozen-test-suite.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "does not match"):
                analyse(directory)


if __name__ == "__main__":
    unittest.main()
