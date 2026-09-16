"""Offline contract checks for the deterministic paper-artifact generator."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "generate_paper_artifacts.py"
SPEC = importlib.util.spec_from_file_location("paper_artifacts", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PaperArtifactTests(unittest.TestCase):
    def test_all_visuals_and_manifest_are_stable_for_complete_export(self) -> None:
        rows = [
            ["condition", "EXP-1", "Weak", "", "", "overall_mean", "45", ""],
            ["condition", "EXP-1", "Strong", "", "", "overall_mean", "70", ""],
            ["dimension", "EXP-1", "Weak", "", "freshness", "mean_percentage", "25", ""],
            ["dimension", "EXP-1", "Strong", "", "freshness", "mean_percentage", "75", ""],
            ["failure", "EXP-1", "", "RUN-1", "freshness", "detected_failure", "FAIL", "old value used"],
            ["failure", "EXP-1", "", "RUN-2", "accuracy", "detected_failure", "FAIL", "incorrect recall"],
            ["failure", "EXP-1", "", "RUN-2", "freshness", "detected_failure", "FAIL", "old value used"],
        ]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source, output = directory / "input.csv", directory / "out"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["record_type", "experiment_id", "condition", "run_id", "dimension", "metric", "value", "detail"])
                writer.writerows(rows)
            original_argv = MODULE.sys.argv
            try:
                MODULE.sys.argv = [str(SCRIPT), str(source), str(output)]
                MODULE.main()
            finally:
                MODULE.sys.argv = original_argv
            expected = {"condition_overall_means.csv", "condition_overall_means.svg", "dimension_comparison.csv", "dimension_comparison.svg", "failure_distribution.csv", "failure_distribution.svg", "paper_artifacts_manifest.json"}
            self.assertEqual({path.name for path in output.iterdir()}, expected)
            manifest = json.loads((output / "paper_artifacts_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["input"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest["row_counts"], {"input_rows": 7, "overall_rows": 2, "dimension_rows": 2, "failure_rows": 2})
            self.assertIn("No statistical significance", manifest["analysis_boundary"])
            self.assertEqual([item["filename"] for item in manifest["artifacts"]], sorted(expected - {"paper_artifacts_manifest.json"}))
            self.assertIn("freshness,2,", (output / "failure_distribution.csv").read_text(encoding="utf-8"))

    def test_absent_optional_rows_do_not_create_empty_charts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source, output = directory / "input.csv", directory / "out"
            source.write_text("record_type,experiment_id,condition,run_id,dimension,metric,value,detail\ncondition,E,Weak,,,overall_mean,50,\n", encoding="utf-8")
            original_argv = MODULE.sys.argv
            try:
                MODULE.sys.argv = [str(SCRIPT), str(source), str(output)]
                MODULE.main()
            finally:
                MODULE.sys.argv = original_argv
            self.assertFalse((output / "dimension_comparison.svg").exists())
            self.assertFalse((output / "failure_distribution.svg").exists())


if __name__ == "__main__":
    unittest.main()
