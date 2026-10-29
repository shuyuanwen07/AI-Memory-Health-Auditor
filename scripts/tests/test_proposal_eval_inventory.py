"""Tests for the non-destructive proposal evidence inventory."""
from pathlib import Path
import tempfile
import unittest

from scripts.proposal_eval_inventory import EXPECTED_PATHS, inventory


class ProposalEvidenceInventoryTests(unittest.TestCase):
    def test_missing_originals_are_reported_without_inference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = inventory(Path(temporary))
        records = {row["key"]: row for row in result["records"]}
        for key in ("latest_a_run", "latest_b_run", "latest_c_run"):
            self.assertEqual(records[key]["state"], "missing")
        self.assertFalse(result["summary"]["latest_a_b_c_originals_present"])
        self.assertFalse(result["summary"]["archived_phase4_abc_originals_present"])

    def test_archived_phase4_c_and_separate_candidate_c_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key in ("latest_a_run", "latest_b_run", "phase4_archived_c_run", "latest_c_run"):
                path = root / EXPECTED_PATHS[key]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(key, encoding="utf-8")
            result = inventory(root)
        self.assertTrue(result["summary"]["archived_phase4_abc_originals_present"])
        self.assertTrue(result["summary"]["separate_candidate_c_v5_present"])
        records = {row["key"]: row for row in result["records"]}
        self.assertNotEqual(records["phase4_archived_c_run"]["path"], records["latest_c_run"]["path"])

    def test_small_local_file_is_hashed_and_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = EXPECTED_PATHS["owner_a_validation"]
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text("fixture\n", encoding="utf-8")
            result = inventory(root)
        row = next(row for row in result["records"] if row["key"] == "owner_a_validation")
        self.assertEqual(row["state"], "file")
        self.assertEqual(row["bytes"], 8)
        self.assertEqual(len(row["sha256"]), 64)

    def test_user_supplied_phase4_archive_material_return_and_audit_are_hash_inventoried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key in ("user_supplied_phase4_review_archive", "user_supplied_phase4_review_material",
                        "user_supplied_phase4_review_return", "assisted_human_return_audit"):
                path = root / EXPECTED_PATHS[key]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(key, encoding="utf-8")
            result = inventory(root)
        records = {row["key"]: row for row in result["records"]}
        for key in ("user_supplied_phase4_review_archive", "user_supplied_phase4_review_material",
                    "user_supplied_phase4_review_return", "assisted_human_return_audit"):
            self.assertEqual(records[key]["state"], "file")
            self.assertEqual(len(records[key]["sha256"]), 64)

    def test_longmemeval_source_and_execution_receipts_are_inventoried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            keys = ("longmemeval_official_source_manifest", "longmemeval_official_execution_manifest",
                    "longmemeval_oracle_blind_review_condition_key", "user_supplied_review2_return",
                    "user_supplied_review2_material", "user_supplied_chongtai_recheck40_archive",
                    "review_followup_intake_manifest", "phase4_review_recheck_analysis_2026_10_28", "candidate_c_protocol",
                    "candidate_c_subset", "candidate_c_v2_partial_run", "candidate_c_v3_partial_run",
                    "candidate_c_v4_partial_run", "candidate_c_v4_interruption_receipt",
                    "candidate_c_v5_protocol", "candidate_c_v5_subset", "candidate_c_v5_raw_run",
                    "candidate_c_v5_analysis")
            for key in keys:
                path = root / EXPECTED_PATHS[key]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(key, encoding="utf-8")
            result = inventory(root)
        records = {row["key"]: row for row in result["records"]}
        for key in keys:
            self.assertEqual(records[key]["state"], "file")
            self.assertEqual(len(records[key]["sha256"]), 64)

    def test_current_source_demo_and_review_packet_are_inventoried(self) -> None:
        keys = (
            "current_source_presentation_demo_readme",
            "current_source_presentation_demo_report",
            "current_source_presentation_demo_manifest",
            "current_source_presentation_demo_bundle",
            "current_source_presentation_demo_csv",
            "current_source_presentation_demo_verification",
            "current_source_presentation_review_csv",
            "current_source_presentation_review_instructions",
            "current_source_presentation_review_key_private",
            "current_source_presentation_review_manifest",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key in keys:
                path = root / EXPECTED_PATHS[key]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(key, encoding="utf-8")
            result = inventory(root)
        records = {row["key"]: row for row in result["records"]}
        for key in keys:
            self.assertEqual(records[key]["state"], "file")
            self.assertEqual(len(records[key]["sha256"]), 64)

    def test_current_source_tutor_repair_and_blind_review_packet_are_inventoried(self) -> None:
        keys = (
            "current_source_tutor_repair_readme",
            "current_source_tutor_repair_manifest",
            "current_source_tutor_repair_bundle",
            "current_source_tutor_review_csv",
            "current_source_tutor_review_instructions",
            "current_source_tutor_review_key_private",
            "current_source_tutor_review_manifest",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key in keys:
                path = root / EXPECTED_PATHS[key]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(key, encoding="utf-8")
            result = inventory(root)
        records = {row["key"]: row for row in result["records"]}
        for key in keys:
            self.assertEqual(records[key]["state"], "file")
            self.assertEqual(len(records[key]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
