"""Synthetic, offline checks for private reviewer JSON reconciliation."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import reconcile_multi_reviewer_json as reconcile_tool
import prepare_multi_reviewer_json as packet_preparer


def _dump(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packet_fixture(root: Path):
    transcript = [{"message_id": "H1S1", "role": "user", "content": "I live in Brisbane."}]
    material = {"items": {"a1": {"kind": "response", "study": "A", "history": "H1", "defects": ["D1"]}}}
    material_path = root / "formal-material.json"
    _dump(material_path, material)
    declaration = {"reviewer_label": None, "completed_at": None, "completed_by_human": None,
                   "used_ai_assistance": None, "has_seen_automated_or_aggregate_results": None,
                   "completed_independently": None}
    master = {
        "format": "synthetic-master-v1", "title_zh": "master", "generated_date": "2026-10-28",
        "reviewer_declaration": copy.deepcopy(declaration), "manual_confirmations_zh": [],
        "source_files_preserved": ["source.json"], "summary": {"total_item_records_for_review": 4},
        "label_definitions_zh": {"answer_judgment": {"Pass": "正确", "Fail": "错误", "Uncertain": "不确定"}},
        "manual_confirmations_zh": [{"confirmation_id": "permission", "review": {"confirmed": None}}],
        "evidence_catalog": {"E-H1": [{"source_transcript": 1, "messages": transcript}]},
        "queues": [
            {"queue_id": "proposal_ab_formal_review_216", "title": "合成 A/B", "status": "待人工审核",
             "review_count": 1, "review_instruction": "master A/B instruction",
             "source_material_sha256": _sha(material_path), "source_packet": "source.json",
             "source_histories": {"H1": transcript},
             "items": [{"item_id": "Q-001", "task": {"kind": "question", "history": "H1"},
                        "question": "问题 A", "evidence_refs": ["E-H1"],
                        "review": {"valid": None, "note": ""}},
                       {"item_id": "G-001", "task": {"kind": "reference", "history": "H1"},
                        "text": "Brisbane", "source_ids": ["H1S1"], "candidate_ids": [],
                        "evidence_refs": ["E-H1"],
                        "review": {"valid": None, "coverage": None, "candidate_ids": [], "note": ""}}]},
            {"queue_id": "proposal_c_v6_review_180", "title": "合成答案审核", "status": "待人工审核",
             "review_count": 3, "review_instruction": "选择 Pass、Fail 或 Uncertain。",
             "source_packet": "source.json", "source_histories": {"H1": transcript},
             "items": [{
                 "item_id": f"C-{i:03d}", "question": f"问题 {i}", "reference_answer": f"参考答案 {i}",
                 "target_response": f"系统答案 {i}", "evidence_refs": ["E-H1"],
                 "task": {"kind": "response", "history": "H1", "question_id": f"Q-{i:03d}"},
                 "review": {"answer_judgment": None, "rationale": ""},
             } for i in range(1, 4)]},
        ],
    }
    inventory = {"H1": ["D1"]}
    templates = []
    for slot in (1, 2):
        doc = copy.deepcopy(master)
        doc["title_zh"] = f"副本 {slot}"
        doc["reviewer_slot"] = slot
        doc["read_me_zh"] = ["只改 review、declaration、manual confirmations 和 additional missing facts。"]
        doc["reviewer_declaration"].setdefault("completed_by_human", None)
        doc["填写示例_zh"] = {"note": "示例，不是结论"}
        doc["label_definitions_zh"]["formal_ab_fields"] = dict(reconcile_tool.FORMAL_AB_FIELDS)
        doc.pop("source_files_preserved")
        for queue in doc["queues"]:
            queue.pop("source_packet", None)
            for item in queue["items"]:
                refs = item.get("evidence_refs", [])
                if refs:
                    item["source_evidence_zh"] = [copy.deepcopy(doc["evidence_catalog"][ref]) for ref in refs]
                history = (item.get("task") or {}).get("history")
                if history:
                    item["source_history_zh"] = copy.deepcopy(queue["source_histories"][history])
            if queue["queue_id"] == "proposal_ab_formal_review_216":
                queue["review_instruction"] = reconcile_tool.FORMAL_AB_REVIEW_INSTRUCTION
                queue["frozen_defect_inventory_by_history"] = copy.deepcopy(inventory)
                queue["additional_missing_facts"] = {"H1": None}
        templates.append(doc)
    p_master = root / "master.json"
    p_a, p_b = root / "reviewer-1.json", root / "reviewer-2.json"
    _dump(p_master, master)
    _dump(p_a, templates[0])
    _dump(p_b, templates[1])
    manifest = {"format": "multi-reviewer-json-v1", "master_sha256": _sha(p_master),
                "reviewer_copies": [{"file": p_a.name, "sha256": _sha(p_a)},
                                    {"file": p_b.name, "sha256": _sha(p_b)}]}
    p_manifest = root / "manifest.json"
    _dump(p_manifest, manifest)
    returns = [copy.deepcopy(templates[0]), copy.deepcopy(templates[1])]
    returns[0]["reviewer_declaration"].update({"reviewer_label": "self-label-A", "completed_at": "date-A",
                                               "completed_by_human": True, "used_ai_assistance": False,
                                               "has_seen_automated_or_aggregate_results": True,
                                               "completed_independently": True})
    returns[1]["reviewer_declaration"].update({"reviewer_label": "self-label-B", "completed_at": "date-B",
                                               "completed_by_human": True, "used_ai_assistance": True,
                                               "has_seen_automated_or_aggregate_results": True,
                                               "completed_independently": False})
    returns[0]["manual_confirmations_zh"][0]["review"]["confirmed"] = True
    returns[1]["manual_confirmations_zh"][0]["review"]["confirmed"] = False
    returns[0]["queues"][0]["additional_missing_facts"]["H1"] = "遗漏事实及来源 H1S2"
    returns[1]["queues"][0]["additional_missing_facts"]["H1"] = ""
    returns[0]["queues"][0]["items"][0]["review"]["valid"] = True
    returns[1]["queues"][0]["items"][0]["review"]["valid"] = True
    for returned in returns:
        returned["queues"][0]["items"][1]["review"].update(
            {"valid": True, "coverage": "none", "candidate_ids": []})
    reviews_a = [
        {"answer_judgment": "Pass", "rationale": "supported"},
        {"answer_judgment": "Fail", "rationale": "wrong"},
        {"answer_judgment": "Uncertain", "rationale": "ambiguous"},
    ]
    reviews_b = [
        {"answer_judgment": "Pass", "rationale": "supported"},
        {"answer_judgment": "Pass", "rationale": "I disagree"},
        {"answer_judgment": None, "rationale": "not assessed"},
    ]
    for i, item in enumerate(returns[0]["queues"][1]["items"]):
        item["review"] = reviews_a[i]
    for i, item in enumerate(returns[1]["queues"][1]["items"]):
        item["review"] = reviews_b[i]
    p_return_a, p_return_b = root / "return-a.json", root / "return-b.json"
    _dump(p_return_a, returns[0])
    _dump(p_return_b, returns[1])
    return p_master, p_manifest, p_a, p_return_a, p_b, p_return_b, material_path


class MultiReviewerReconcileTests(unittest.TestCase):
    def _reconcile(self, paths, output):
        return reconcile_tool.reconcile(*paths[:6], output, formal_material_path=paths[6])

    def test_counts_actual_declarations_and_keeps_disagreements_unresolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _packet_fixture(root)
            output = root / "private-adjudication.json"
            original_hashes = [_sha(path) for path in paths]
            result = self._reconcile(paths, output)
            field = result["queues"]["proposal_c_v6_review_180"]["primary_judgments_by_field"]["answer_judgment"]
            self.assertEqual(field["expected_pairs"], 3)
            self.assertEqual(field["reviewer_a"], {"complete": 2, "missing": 0, "uncertain": 1})
            self.assertEqual(field["reviewer_b"], {"complete": 2, "missing": 1, "uncertain": 0})
            self.assertEqual((field["agreed"], field["disagreed"], field["unresolved_pairs"]), (1, 1, 1))
            self.assertEqual(result["counts"]["unresolved_item_count"], 2)
            unresolved = {row["item_id"] for row in result["unresolved_items"]}
            self.assertEqual(unresolved, {"C-002", "C-003"})
            self.assertTrue(all(row["adjudicated_value"] is None for row in result["items"]))
            self.assertFalse(result["provenance_limits"]["identity_authenticated"])
            self.assertFalse(result["provenance_limits"]["reviewer_independence_authenticated"])
            self.assertEqual(result["reviewer_declarations"]["reviewer_slot_1"]["values"]["used_ai_assistance"], False)
            self.assertEqual(result["reviewer_declarations"]["reviewer_slot_1"]["values"]["completed_by_human"], True)
            self.assertTrue(result["manual_confirmations_by_reviewer"]["reviewer_slot_1"][0]["review"]["confirmed"])
            self.assertEqual(result["additional_missing_facts_by_queue"]["proposal_ab_formal_review_216"][0]["comparison"], "disagreed")
            reference_fields = result["queues"]["proposal_ab_formal_review_216"]["primary_judgments_by_field"]
            self.assertEqual(reference_fields["candidate_ids"]["reviewer_a"]["complete"], 1)
            self.assertEqual(reference_fields["candidate_ids"]["agreed"], 1)
            self.assertIsNone(result["additional_missing_facts_by_queue"]["proposal_ab_formal_review_216"][0]["adjudicated_value"])
            self.assertEqual(original_hashes, [_sha(path) for path in paths])
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                self._reconcile(paths, output)

    def test_rejects_changed_return_evidence_or_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = list(_packet_fixture(root))
            returned = reconcile_tool.read_json(paths[3])
            returned["queues"][0]["items"][0]["question"] = "被修改的问题"
            _dump(paths[3], returned)
            with self.assertRaisesRegex(reconcile_tool.ReconciliationError, "来源证据、item 身份"):
                self._reconcile(paths, root / "must-not-exist.json")
            self.assertFalse((root / "must-not-exist.json").exists())

    def test_rejects_mutated_blank_template_against_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = list(_packet_fixture(root))
            template = reconcile_tool.read_json(paths[2])
            template["queues"][0]["items"][0]["evidence_refs"] = []
            _dump(paths[2], template)
            with self.assertRaisesRegex(reconcile_tool.ReconciliationError, "模板与 manifest 哈希不符"):
                self._reconcile(paths, root / "must-not-exist.json")

    def test_rejects_changed_frozen_defect_inventory_even_if_manifest_is_rewritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = list(_packet_fixture(root))
            template = reconcile_tool.read_json(paths[2])
            template["queues"][0]["frozen_defect_inventory_by_history"]["H1"] = ["invented"]
            _dump(paths[2], template)
            returned = reconcile_tool.read_json(paths[3])
            returned["queues"][0]["frozen_defect_inventory_by_history"]["H1"] = ["invented"]
            _dump(paths[3], returned)
            manifest = reconcile_tool.read_json(paths[1])
            for copied in manifest["reviewer_copies"]:
                if copied["file"] == paths[2].name:
                    copied["sha256"] = _sha(paths[2])
            _dump(paths[1], manifest)
            with self.assertRaisesRegex(reconcile_tool.ReconciliationError, "frozen_defect_inventory_by_history"):
                self._reconcile(paths, root / "must-not-exist.json")

    def test_empty_reference_links_are_complete_but_uncertain_coverage_stays_uncertain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = list(_packet_fixture(root))
            for return_path in (paths[3], paths[5]):
                returned = reconcile_tool.read_json(return_path)
                reference = returned["queues"][0]["items"][1]["review"]
                reference["coverage"] = "uncertain"
                reference["candidate_ids"] = []
                _dump(return_path, returned)
            result = self._reconcile(paths, root / "private-adjudication.json")
            fields = result["queues"]["proposal_ab_formal_review_216"]["primary_judgments_by_field"]
            self.assertEqual(fields["candidate_ids"]["reviewer_a"]["complete"], 1)
            self.assertEqual(fields["candidate_ids"]["agreed"], 1)
            self.assertEqual(fields["coverage"]["reviewer_a"]["uncertain"], 1)
            unresolved = {row["item_id"] for row in result["unresolved_items"]}
            self.assertIn("G-001", unresolved)
            self.assertEqual(result["queues"]["proposal_ab_formal_review_216"]["item_counts"]["pair_unresolved"], 1)

    def test_v7_validation_binds_session_dates_and_question_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = {
                "question_id": "q-1", "question": "When did the trip happen?", "answer": "In June.",
                "question_date": "2025-06-20", "haystack_session_ids": ["s-1", "s-2"],
                "answer_session_ids": ["s-2"], "haystack_dates": ["2025-06-01", "2025-06-12"],
                "haystack_sessions": [
                    [{"message_id": "m-1", "role": "user", "content": "Old detail."}],
                    [{"message_id": "m-2", "role": "user", "content": "Trip is in June."}],
                ],
            }
            subset_path = root / "longmemeval-subset.json"
            _dump(subset_path, [case])
            protocol_path = root / "protocol.json"
            _dump(protocol_path, {"id": "synthetic-v7"})
            response = "It was in June."
            response_sha = hashlib.sha256(response.encode()).hexdigest()
            run_path = root / "C-live.json"
            _dump(run_path, {"protocol_id": "synthetic-v7", "protocol_sha256": _sha(protocol_path),
                             "subset_sha256": _sha(subset_path),
                             "target_receipts": [{"repetition": 1, "strategy": "scope_aware",
                                                  "question_id": "q-1", "response_sha256": response_sha,
                                                  "response": {"response_text": response}}]})
            evidence = packet_preparer.evidence_for(case)
            evidence_bytes = reconcile_tool.canonical(evidence).encode("utf-8")
            evidence_ref = "E-" + hashlib.sha256(evidence_bytes).hexdigest()[:16]
            item = {"item_id": "V7-001", "question": case["question"], "question_date": case["question_date"],
                    "reference_answer": case["answer"], "target_response": response,
                    "evidence_refs": [evidence_ref], "source_evidence_zh": [evidence],
                    "review": {"answer_judgment": None, "rationale": ""}}
            queue = {"queue_id": "four_strategy_v7_answers", "items": [item]}
            catalog = {evidence_ref: evidence}
            key_path = root / "private-key.json"
            _dump(key_path, {"source_run_sha256": _sha(run_path), "protocol_sha256": _sha(protocol_path),
                             "subset_sha256": _sha(subset_path), "mapping": [{
                                 "item_id": "V7-001", "repetition": 1, "strategy": "scope_aware",
                                 "question_id": "q-1", "response_sha256": response_sha}]})
            valid = reconcile_tool._validate_v7_queue({"four_strategy_v7_answers": queue}, key_path, root, catalog)
            self.assertEqual(valid["V7-001"]["question_id"], "q-1")
            self.assertEqual(item["source_evidence_zh"][0][0]["session_date"], "2025-06-12")

            tampered = copy.deepcopy(queue)
            tampered["items"][0]["question_date"] = "2025-06-21"
            with self.assertRaisesRegex(reconcile_tool.ReconciliationError, "问题、参考答案或模型回答"):
                reconcile_tool._validate_v7_queue({"four_strategy_v7_answers": tampered}, key_path, root, catalog)
            tampered_evidence = copy.deepcopy(queue)
            tampered_evidence["items"][0]["source_evidence_zh"][0][0]["session_date"] = "2025-06-13"
            with self.assertRaisesRegex(reconcile_tool.ReconciliationError, "展示的来源转录"):
                reconcile_tool._validate_v7_queue({"four_strategy_v7_answers": tampered_evidence}, key_path, root, catalog)

            template_queue = {"queue_id": "four_strategy_v7_answers", "items": [{
                "item_id": "V7-001", "review": {"answer_judgment": None, "rationale": ""}}]}
            accepted_return = {"queue_id": "four_strategy_v7_answers", "items": [{
                "item_id": "V7-001", "review": {"answer_judgment": "Uncertain", "rationale": "source is ambiguous"}}]}
            reconcile_tool._validate_v7_return_labels(template_queue, accepted_return, "reviewer")
            invalid_return = copy.deepcopy(accepted_return)
            invalid_return["items"][0]["review"]["answer_judgment"] = "mostly correct"
            with self.assertRaisesRegex(reconcile_tool.ReconciliationError, "answer_judgment"):
                reconcile_tool._validate_v7_return_labels(template_queue, invalid_return, "reviewer")


if __name__ == "__main__":
    unittest.main()
