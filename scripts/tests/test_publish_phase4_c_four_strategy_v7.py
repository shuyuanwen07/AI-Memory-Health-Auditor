from __future__ import annotations

import json
import sys
import tempfile
import unittest
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_phase4_c_four_strategy_v7 as publisher


class PublisherTest(unittest.TestCase):
    def test_partial_collection_uses_usable_denominators_and_never_recommends(self):
        names = publisher.EXPECTED_STRATEGIES
        scores = {}
        for name in names:
            scores[name] = {
                "correct": 2, "usable": 4,
                "repetitions": [{"repetition": 1, "correct": 2, "usable": 4},
                                {"repetition": 2, "correct": 0, "usable": 0},
                                {"repetition": 3, "correct": 0, "usable": 0}],
                "category_results": {"example": {"correct": 2, "usable": 4}},
            }
        pairs = [{"left_strategy": a, "right_strategy": b, "repetition": rep,
                  "both_correct": 1, "left_only_correct": 1, "right_only_correct": 0,
                  "neither_correct": 2, "unresolved": 26}
                 for a, b in combinations(names, 2) for rep in range(1, 4)]
        analysis = {
            "protocol_id": "p", "protocol_sha256": "a" * 64,
            "collection_status": "paused_cost_ceiling", "selected_case_count": 30,
            "coverage": {"target_answers_saved": 16, "usable_grader_decisions": 16},
            "scores": {"per_strategy": scores, "all_pairwise_per_repetition": pairs},
            "decision": {"collection_complete": False, "recommended_strategy": names[0]},
            "cost": {"estimated_usd": 0.4, "usage_based_estimate_usd": 0.39},
            "request_pacing": {"dispatch_count": 32}, "limitations": ["partial"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "C-live.json").write_text('{"private_answer":"not public"}', encoding="utf-8")
            inputs = {"directory": root, "protocol": {"source": {"revision": "source"},
                                                        "analysis": {"selection_rule": "rule"}}}
            output = root / "dashboard.json"
            with patch.object(publisher, "validate_frozen_inputs", return_value=inputs), \
                 patch.object(publisher, "validate_and_analyze", return_value=(analysis, {})):
                publisher.publish(root, root, output)
            result = json.loads(output.read_text())
            self.assertFalse(result["complete_for_decision"])
            self.assertEqual(result["recommended_strategy"], "no_clear_winner")
            self.assertEqual(result["strategies"][0]["accuracy_percent"], 50.0)
            self.assertIsNone(result["strategies"][0]["per_repetition"][1]["accuracy_percent"])
            self.assertEqual(len(result["pairwise"]), 6)
            self.assertEqual(result["pairwise"][0]["total"], 12)
            self.assertEqual(result["pairwise"][0]["difference_pp"], 25.0)
            self.assertNotIn("private_answer", output.read_text())


if __name__ == "__main__":
    unittest.main()
