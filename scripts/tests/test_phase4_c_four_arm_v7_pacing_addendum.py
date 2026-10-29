"""Offline tests for hash-bound, non-decisional v7 pacing addenda."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "tests"))

import analyze_phase4_c_four_arm_v7_unverified_pacing as exception_analyzer
import publish_phase4_c_four_strategy_v7 as publisher
from phase4_c_four_arm_v7_pacing_addendum import (
    PacingAddendumError,
    build_addendum,
    verify_addendum,
)
from test_phase4_c_four_arm_v7 import _make_analysis_fixture


def _dump(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _one_short_interval(run):
    adjusted = list(run["provider_dispatch_starts_utc"])
    parsed = [datetime.fromisoformat(value) for value in adjusted]
    # Preserve all raw entries except the deliberately short UTC observation.
    parsed[6] = parsed[5] + timedelta(seconds=3.869336)
    adjusted[6] = parsed[6].isoformat(timespec="microseconds")
    run["provider_dispatch_starts_utc"] = adjusted
    run["pacing_sessions"][0]["request_starts_utc"] = list(adjusted)
    return run


class PacingAddendumTests(unittest.TestCase):
    def test_addendum_preserves_source_timestamps_and_rejects_tampering(self):
        inputs, run, _ = _make_analysis_fixture()
        run = _one_short_interval(run)
        source = {"run": "1" * 64, "protocol": "2" * 64, "subset": "3" * 64}
        addendum = build_addendum(run, inputs["protocol"], source,
                                  created_at_utc="2026-10-28T05:00:00+00:00", tool_sha256="4" * 64)
        self.assertEqual(addendum["status"], "utc_timing_unverifiable")
        self.assertEqual(addendum["cause_assessment"], "unknown")
        self.assertEqual(addendum["compliance_claim"], "unverifiable_from_saved_utc_timestamps")
        self.assertEqual(addendum["observations"]["raw_timestamp_record"]["provider_dispatch_starts_utc"],
                         run["provider_dispatch_starts_utc"])
        self.assertEqual(addendum["observations"]["violations"][0]["from_dispatch_index"], 6)
        self.assertEqual(addendum["observations"]["violations"][0]["to_dispatch_index"], 7)
        verified = verify_addendum(addendum, run, inputs["protocol"], source)
        self.assertEqual(verified["dispatch_count"], 720)
        tampered = copy.deepcopy(addendum)
        tampered["observations"]["raw_timestamp_record"]["provider_dispatch_starts_utc"][6] = "changed"
        with self.assertRaises(PacingAddendumError):
            verify_addendum(tampered, run, inputs["protocol"], source)

    def test_no_running_or_clean_collection_can_use_anomaly_addendum(self):
        inputs, run, _ = _make_analysis_fixture()
        source = {"run": "1" * 64, "protocol": "2" * 64, "subset": "3" * 64}
        with self.assertRaisesRegex(PacingAddendumError, "still running"):
            build_addendum({**run, "status": "running"}, inputs["protocol"], source)
        with self.assertRaisesRegex(PacingAddendumError, "No UTC pacing anomaly"):
            build_addendum(run, inputs["protocol"], source)

    def test_wrapper_reuses_pinned_analysis_but_suppresses_winner(self):
        inputs, run, dependencies = _make_analysis_fixture()
        run = _one_short_interval(run)
        source = {"run": "a" * 64, "protocol": "b" * 64, "subset": "c" * 64}
        addendum = build_addendum(run, inputs["protocol"], source, tool_sha256="d" * 64)
        analysis, summary = exception_analyzer.analyze_validated_run(
            inputs, run, addendum, source, "e" * 64, dependencies)
        self.assertTrue(analysis["decision"]["collection_complete"])
        self.assertTrue(analysis["coverage"]["collection_complete"])
        self.assertFalse(analysis["coverage"]["complete_for_winner_rule"])
        self.assertFalse(analysis["decision"]["decision_eligible"])
        self.assertFalse(analysis["request_pacing"]["verified"])
        self.assertEqual(analysis["decision"]["recommended_strategy"], "no_clear_winner")
        self.assertEqual(summary["recommendation"], "no_clear_winner")
        self.assertFalse(summary["complete_for_decision"])
        self.assertTrue(summary["collection_complete"])
        self.assertEqual(analysis["scores"]["per_strategy"]["scope_aware"]["strict_pass_rate_percent"], 100.0)

    def test_publisher_consumes_validated_bundle_without_strict_pacing_rerun(self):
        inputs, run, dependencies = _make_analysis_fixture()
        run_dir = inputs["directory"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "frozen-run"
            run_dir.mkdir()
            protocol = copy.deepcopy(inputs["protocol"])
            pinned_path = ROOT / "scripts/analyze_phase4_c_four_arm_v7.py"
            protocol["analyzer_sha256"] = _sha(pinned_path)
            protocol_path, subset_path, run_path = (run_dir / name for name in
                                                     ("protocol.json", "longmemeval-subset.json", "C-live.json"))
            _dump(protocol_path, protocol)
            _dump(subset_path, inputs["subset"])
            protocol_sha, subset_sha = _sha(protocol_path), _sha(subset_path)
            run["protocol_sha256"], run["subset_sha256"] = protocol_sha, subset_sha
            _one_short_interval(run)
            _dump(run_path, run)
            bound_inputs = {**inputs, "root": root, "directory": run_dir,
                            "protocol": protocol, "protocol_sha256": protocol_sha,
                            "subset_sha256": subset_sha}
            source = {"run": _sha(run_path), "protocol": protocol_sha, "subset": subset_sha}
            addendum = build_addendum(run, protocol, source, tool_sha256="f" * 64)
            postrun = root / "postrun"
            postrun.mkdir()
            addendum_path = postrun / "pacing-addendum.json"
            _dump(addendum_path, addendum)
            result_dir = postrun / "analysis"
            with patch.object(exception_analyzer, "validate_frozen_inputs", return_value=bound_inputs):
                exception_analyzer.analyze_directory(root, run_dir, addendum_path, result_dir, dependencies)

            dashboard = root / "dashboard.json"
            with patch.object(publisher, "validate_frozen_inputs", return_value=bound_inputs), \
                    patch.object(publisher, "validate_and_analyze", side_effect=AssertionError("strict analyzer reran")):
                published = publisher.publish(root, run_dir, dashboard, result_dir)
            report = json.loads(dashboard.read_text())
            self.assertTrue(report["collection_complete"])
            self.assertFalse(report["complete_for_decision"])
            self.assertEqual(report["pacing_status"], "utc_timing_unverifiable")
            self.assertEqual(report["recommended_strategy"], "no_clear_winner")
            self.assertEqual(report["total_target_answers"], 360)
            self.assertEqual(report["total_usable_grades"], 360)
            self.assertEqual(published["complete"], False)


if __name__ == "__main__":
    unittest.main()
