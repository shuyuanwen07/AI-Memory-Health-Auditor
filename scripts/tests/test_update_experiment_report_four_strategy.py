import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_experiment_report_four_strategy as report


class ReportUpdateTest(unittest.TestCase):
    def test_uses_dashboard_counts_and_is_idempotent(self):
        rows = []
        for name in report.EXPECTED:
            reps = [{"repetition": n, "correct": n, "total": 10} for n in (1, 2, 3)]
            rows.append({"id": name, "label": report.LABELS[name], "correct": 6,
                         "total": 30, "per_repetition": reps})
        data = {"format": "phase4-c-four-strategy-v7", "strategies": rows,
                "collection_status": "partial", "total_target_answers": 120,
                "total_usable_grades": 120, "complete_for_decision": False,
                "recommended_strategy": report.EXPECTED[0], "estimated_cost_usd": 0.2,
                "protocol_sha256": "a" * 64, "run_sha256": "b" * 64}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "report.md"
            source = root / "dashboard.json"
            target.write_text("# Report\n\n### Proposal acceptance criteria\n", encoding="utf-8")
            source.write_text(json.dumps(data), encoding="utf-8")
            report.update(target, source)
            first = target.read_text(encoding="utf-8")
            report.update(target, source)
            self.assertEqual(first, target.read_text(encoding="utf-8"))
            self.assertEqual(first.count(report.BEGIN), 1)
            self.assertIn("6/30 (20.0%)", first)
            self.assertIn("winner decision was withheld", first)
            for label in report.LABELS.values():
                self.assertIn(label, first)


if __name__ == "__main__":
    unittest.main()
