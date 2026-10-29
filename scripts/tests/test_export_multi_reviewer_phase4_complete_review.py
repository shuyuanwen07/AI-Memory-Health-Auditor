"""Synthetic, offline tests for the explicit Phase 4 reviewer export."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import export_multi_reviewer_phase4_complete_review as exporter
import phase4_formal_review
import reconcile_multi_reviewer_json as reconcile


def _dump(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root: Path):
    history = [{"message_id": "H1S1", "role": "user", "content": "The project is in Brisbane."}]
    defects = [{"defect_id": "D1", "dimension": "accuracy", "source_message_ids": ["H1S1"]}]
    material = {
        "schema_version": "phase4-complete-material-v1",
        "histories": {"H1": history},
        "items": {
            "Q1": {"kind": "question", "history": "H1", "question": "Where?", "proposed_reference": "Brisbane."},
            "RA": {"kind": "response", "study": "A", "history": "H1", "question": "Where?", "answer": "Brisbane.", "question_id": "Q1", "defects": defects},
            "RB": {"kind": "response", "study": "B", "history": "H1", "question": "Where?", "answer": "Brisbane.", "question_id": "Q1", "defects": []},
            "C1": {"kind": "candidate", "history": "H1", "text": "The project is in Brisbane.", "proposed_source_ids": ["H1S1"]},
            "G1": {"kind": "reference", "history": "H1", "text": "The project is in Brisbane.", "source_ids": ["H1S1"], "candidate_ids": ["C1"]},
            "E1": {"kind": "relationship", "history": "H1", "from_text": "New fact", "to_text": "Old fact"},
        },
        "reference_unit_definition": "unit",
        "relationship_unit_definition": "pair",
        "critical_error_definition": "wrong fact",
    }
    material_path = root / "source-material.json"
    _dump(material_path, material)
    template_reviews = {
        "Q1": {"valid": None, "note": ""},
        "RA": {"verdict": None, "failure_dimension": None, "critical_error": None, "source_message_ids": [], "defect_ids": None, "note": ""},
        "RB": {"verdict": None, "failure_dimension": None, "critical_error": None, "source_message_ids": [], "note": ""},
        "C1": {"valid": None, "note": ""},
        "G1": {"valid": None, "coverage": None, "candidate_ids": [], "note": ""},
        "E1": {"relationship_type": None, "note": ""},
    }
    tasks = {
        "Q1": {"kind": "question", "history": "H1", "question": "Where?", "proposed_reference": "Brisbane."},
        "RA": {"kind": "response", "history": "H1", "study": "A", "question": "Where?", "answer": "Brisbane.", "question_id": "Q1"},
        "RB": {"kind": "response", "history": "H1", "study": "B", "question": "Where?", "answer": "Brisbane.", "question_id": "Q1"},
        "C1": {"kind": "candidate", "history": "H1", "text": "The project is in Brisbane.", "proposed_source_ids": ["H1S1"]},
        "G1": {"kind": "reference", "history": "H1", "text": "The project is in Brisbane.", "source_ids": ["H1S1"], "candidate_ids": ["C1"]},
        "E1": {"kind": "relationship", "history": "H1", "from_text": "New fact", "to_text": "Old fact"},
    }
    master = {
        "format": "synthetic-master-v1", "generated_date": "2026-10-28", "title_zh": "master",
        "reviewer_declaration": {"reviewer_label": None, "completed_at": None, "completed_by_human": None,
                                 "used_ai_assistance": None, "has_seen_automated_or_aggregate_results": None,
                                 "completed_independently": None, "note": ""},
        "manual_confirmations_zh": [{"confirmation_id": "M1", "review": {"confirmed": None}}],
        "source_files_preserved": ["source-material.json"], "summary": {"items": 6},
        "label_definitions_zh": {"answer_judgment": {"Pass": "正确"}},
        "evidence_catalog": {},
        "queues": [{
            "queue_id": exporter.QUEUE_ID, "title": "A/B", "status": "待审核", "review_count": len(tasks),
            "review_instruction": "master instruction", "source_material_sha256": _sha(material_path),
            "source_histories": {"H1": history}, "reference_unit_definition": "unit",
            "relationship_unit_definition": "pair", "critical_error_definition": "wrong fact",
            "items": [{"item_id": item_id, "task": tasks[item_id], "review": template_reviews[item_id]}
                      for item_id in tasks],
        }],
    }
    template = copy.deepcopy(master)
    template["title_zh"] = "review copy"
    template["reviewer_slot"] = 1
    template["read_me_zh"] = ["instructions"]
    template["reviewer_declaration"].setdefault("completed_by_human", None)
    template["label_definitions_zh"]["formal_ab_fields"] = dict(reconcile.FORMAL_AB_FIELDS)
    template.pop("source_files_preserved")
    queue = template["queues"][0]
    queue.pop("source_packet", None)
    queue["review_instruction"] = reconcile.FORMAL_AB_REVIEW_INSTRUCTION
    queue["frozen_defect_inventory_by_history"] = {"H1": defects}
    queue["additional_missing_facts"] = {"H1": None}
    for item in queue["items"]:
        item["source_history_zh"] = history

    returned = copy.deepcopy(template)
    returned["reviewer_declaration"].update({
        "reviewer_label": "Reviewer X", "completed_at": "2026-10-28T10:00:00+11:00",
        "completed_by_human": True, "used_ai_assistance": True,
        "has_seen_automated_or_aggregate_results": True, "completed_independently": True,
        "note": "self-reported declaration",
    })
    returned["manual_confirmations_zh"][0]["review"]["confirmed"] = True
    queue_return = returned["queues"][0]
    queue_return["additional_missing_facts"]["H1"] = ""
    labels = {
        "Q1": {"valid": True, "note": "Q note"},
        "RA": {"verdict": "pass", "failure_dimension": None, "critical_error": "no", "source_message_ids": ["H1S1"], "defect_ids": [], "note": "A note"},
        "RB": {"verdict": "pass", "failure_dimension": None, "critical_error": "no", "source_message_ids": ["H1S1"], "note": "B note"},
        "C1": {"valid": True, "note": "C note"},
        "G1": {"valid": True, "coverage": "full", "candidate_ids": ["C1"], "note": "G note"},
        "E1": {"relationship_type": "UPDATE", "note": "E note"},
    }
    for item in queue_return["items"]:
        item["review"] = labels[item["item_id"]]

    master_path, template_path, return_path = root / "master.json", root / "reviewer-1.json", root / "return.json"
    manifest_path, phase4_material_path, phase4_key_path = root / "manifest.json", root / "phase4-material.json", root / "phase4-key.json"
    _dump(master_path, master)
    _dump(template_path, template)
    _dump(return_path, returned)
    fingerprint = exporter._material_fingerprint(material)
    _dump(phase4_material_path, material)
    _dump(phase4_key_path, {"material_sha256": [fingerprint]})
    _dump(manifest_path, {"format": "multi-reviewer-json-v1", "master_sha256": _sha(master_path),
                          "reviewer_copies": [{"file": template_path.name, "sha256": _sha(template_path)}]})
    return (master_path, manifest_path, template_path, return_path, material_path,
            phase4_material_path, phase4_key_path, root / "export.json")


class Phase4ExportTests(unittest.TestCase):
    def _export(self, paths):
        return exporter.export(*paths)

    def test_maps_all_fields_and_declarations_verbatim_then_runs_official_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = _fixture(Path(temporary))
            originals = [_sha(path) for path in paths[:-1]]
            result = self._export(paths)
            exported = json.loads(paths[-1].read_text())
            material = json.loads(paths[5].read_text())
            key = json.loads(paths[6].read_text())
            phase4_formal_review.validate(material, key, exported)
            self.assertEqual(result["label_count"], 6)
            self.assertEqual(exported["reviewer_id"], "Reviewer X")
            self.assertTrue(exported["completed_by_human"])
            self.assertTrue(exported["completed_independently"])
            self.assertTrue(exported["used_ai_assistance"])
            self.assertTrue(exported["has_seen_automated_results"])
            self.assertEqual(exported["additional_missing_facts"], {"H1": ""})
            self.assertEqual(exported["labels"]["RA"]["defect_ids"], [])
            self.assertEqual(exported["labels"]["G1"]["candidate_ids"], ["C1"])
            sidecar = json.loads(Path(result["provenance"]).read_text())
            self.assertEqual(sidecar["manual_confirmations_zh_as_returned"][0]["review"]["confirmed"], True)
            self.assertFalse(any("authenticates" in note for note in sidecar["limits"]))
            self.assertEqual(originals, [_sha(path) for path in paths[:-1]])
            self.assertEqual(os.stat(paths[-1]).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(Path(result["provenance"])).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                self._export(paths)

    def test_refuses_false_independence_without_rewriting_the_declaration(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = list(_fixture(Path(temporary)))
            returned = json.loads(paths[3].read_text())
            returned["reviewer_declaration"]["completed_independently"] = False
            _dump(paths[3], returned)
            with self.assertRaisesRegex(exporter.ExportError, "未改写声明"):
                self._export(paths)
            self.assertFalse(paths[7].exists())

    def test_refuses_unresolved_additional_facts_and_mutated_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = list(_fixture(Path(temporary)))
            returned = json.loads(paths[3].read_text())
            returned["queues"][0]["additional_missing_facts"]["H1"] = None
            _dump(paths[3], returned)
            with self.assertRaisesRegex(exporter.ExportError, "additional_missing_facts"):
                self._export(paths)
            self.assertFalse(paths[7].exists())


if __name__ == "__main__":
    unittest.main()
