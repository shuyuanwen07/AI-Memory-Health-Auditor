"""Synthetic offline tests for baseline-to-combined review progress transfer."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "tests"))

import prepare_multi_reviewer_json as packet_preparer
import reconcile_multi_reviewer_json as validator
import transfer_multi_reviewer_progress as transfer_tool
from test_reconcile_multi_reviewer_json import _dump, _packet_fixture, _sha


BASELINE_REVIEW_SCHEMAS = {
    "proposal_c_archived_review_84": {"answer_judgment": None, "rationale": ""},
    "proposal_c_v5_review_84": {"answer_judgment": None, "rationale": ""},
    "current_source_repair_24": {"question_validity": None, "answer_verdict": None, "rationale": ""},
    "current_source_six_run_48": {"answer_verdict": None, "rationale": ""},
    "earlier_repair_loop_36": {"question_validity": None, "answer_correctness": None, "rationale": ""},
    "current_source_intake_candidates_14": {"decision": None, "rationale": ""},
}


def _prepare_transfer_fixture(root: Path):
    paths = list(_packet_fixture(root))
    master_path, baseline_manifest_path, baseline_template_a, baseline_return_a, baseline_template_b, baseline_return_b, material_path = paths
    master = validator.read_json(master_path)
    template_a = validator.read_json(baseline_template_a)
    template_b = validator.read_json(baseline_template_b)
    return_a = validator.read_json(baseline_return_a)
    return_b = validator.read_json(baseline_return_b)
    history = master["queues"][0]["source_histories"]["H1"]
    for queue_id, review in BASELINE_REVIEW_SCHEMAS.items():
        master_queue = {"queue_id": queue_id, "title": f"Synthetic {queue_id}", "status": "待审核",
                        "review_count": 1, "source_packet": "source.json", "source_histories": {"H1": history},
                        "items": [{"item_id": f"{queue_id}-1", "task": {"kind": "response", "history": "H1"},
                                   "question": "Q", "evidence_refs": ["E-H1"], "review": copy.deepcopy(review)}]}
        master["queues"].append(master_queue)
        for doc in (template_a, template_b):
            reviewer_queue = copy.deepcopy(master_queue)
            reviewer_queue.pop("source_packet")
            reviewer_queue["items"][0]["source_evidence_zh"] = [copy.deepcopy(doc["evidence_catalog"]["E-H1"])]
            reviewer_queue["items"][0]["source_history_zh"] = copy.deepcopy(history)
            doc["queues"].append(reviewer_queue)
        for returned in (return_a, return_b):
            reviewer_queue = copy.deepcopy(master_queue)
            reviewer_queue.pop("source_packet")
            reviewer_queue["items"][0]["source_evidence_zh"] = [copy.deepcopy(template_a["evidence_catalog"]["E-H1"])]
            reviewer_queue["items"][0]["source_history_zh"] = copy.deepcopy(history)
            returned["queues"].append(reviewer_queue)

    # Add two explicitly authorized manual confirmation areas and fill them in the baseline return.
    confirmations = [
        {"confirmation_id": "member_contributions", "prompt": "Record actual contribution evidence.",
         "members": [{"member_slot": "member_1", "actual_contributions": [], "evidence_references": [],
                      "confirmed": None, "confirmed_at": None}]},
        {"confirmation_id": "novice_observations", "prompt": "Record observed usability sessions.",
         "observations": [{"participant_code": None, "task": None, "outcome": None,
                           "difficulties": [], "unsuccessful_steps": [], "consent_record": None,
                           "observed_at": None, "notes": ""}]},
    ]
    master["manual_confirmations_zh"].extend(copy.deepcopy(confirmations))
    for doc in (template_a, template_b):
        doc["manual_confirmations_zh"].extend(copy.deepcopy(confirmations))
    for returned in (return_a, return_b):
        returned["manual_confirmations_zh"].extend(copy.deepcopy(confirmations))
    return_a["manual_confirmations_zh"][1]["members"][0].update(
        {"actual_contributions": ["Implemented extraction checks"], "evidence_references": ["commit:abc"],
         "confirmed": True, "confirmed_at": "2026-10-28"})
    return_a["manual_confirmations_zh"][2]["observations"] = [
        {"participant_code": "P01", "task": "Create an audit", "outcome": "completed",
         "difficulties": ["Needed help finding the result"], "unsuccessful_steps": [],
         "consent_record": "C01", "observed_at": "2026-10-28", "notes": "Observed live."}]
    # Fill all six added baseline queues with recognizable values.
    for index, queue_id in enumerate(BASELINE_REVIEW_SCHEMAS):
        return_a["queues"][-len(BASELINE_REVIEW_SCHEMAS) + index]["items"][0]["review"] = {
            **copy.deepcopy(BASELINE_REVIEW_SCHEMAS[queue_id]), "rationale": f"reviewed {queue_id}"}
        review = return_a["queues"][-len(BASELINE_REVIEW_SCHEMAS) + index]["items"][0]["review"]
        first_non_rationale = next((field for field in review if field != "rationale"), None)
        if first_non_rationale:
            review[first_non_rationale] = "Pass" if first_non_rationale not in {"question_validity", "decision"} else True
    return_a["queues"][0]["additional_missing_facts"]["H1"] = "Extra fact with source H1S2"

    for doc in (template_a, template_b):
        counts = {row["queue_id"]: len(row["items"]) for row in doc["queues"]}
        doc["summary"] = {"counts_by_queue": counts, "total_item_records_for_review": sum(counts.values()),
                          "evidence_catalog_entries": len(doc["evidence_catalog"])}
    for returned in (return_a, return_b):
        counts = {row["queue_id"]: len(row["items"]) for row in returned["queues"]}
        returned["summary"] = {"counts_by_queue": counts, "total_item_records_for_review": sum(counts.values()),
                               "evidence_catalog_entries": len(returned["evidence_catalog"])}

    _dump(master_path, master)
    _dump(baseline_template_a, template_a)
    _dump(baseline_template_b, template_b)
    _dump(baseline_return_a, return_a)
    _dump(baseline_return_b, return_b)
    manifest = validator.read_json(baseline_manifest_path)
    manifest["master_sha256"] = _sha(master_path)
    for row in manifest["reviewer_copies"]:
        path = baseline_template_a if row["file"] == baseline_template_a.name else baseline_template_b
        row["sha256"] = _sha(path)
    _dump(baseline_manifest_path, manifest)

    # Minimal immutable v7 source with one correctly bound answer.
    v7_dir = root / "v7"
    v7_dir.mkdir()
    case = {"question_id": "q-v7", "question": "When was it?", "answer": "In June.",
            "question_date": "2025-06-20", "haystack_session_ids": ["s-v7"],
            "answer_session_ids": ["s-v7"], "haystack_dates": ["2025-06-12"],
            "haystack_sessions": [[{"message_id": "m-v7", "role": "user", "content": "It happened in June."}]]}
    subset_path, protocol_path, run_path = (v7_dir / name for name in
                                             ("longmemeval-subset.json", "protocol.json", "C-live.json"))
    _dump(subset_path, [case])
    _dump(protocol_path, {"id": "synthetic-v7"})
    answer = "It took place in June."
    response_sha = hashlib.sha256(answer.encode()).hexdigest()
    run = {"protocol_id": "synthetic-v7", "protocol_sha256": _sha(protocol_path),
           "subset_sha256": _sha(subset_path), "target_receipts": [{"repetition": 1,
               "strategy": "scope_aware", "question_id": "q-v7", "response_sha256": response_sha,
               "response": {"response_text": answer}}]}
    _dump(run_path, run)
    identity_key = {"source_run_sha256": _sha(run_path), "protocol_sha256": _sha(protocol_path),
                    "subset_sha256": _sha(subset_path), "mapping": [{"item_id": "V7-001", "question_id": "q-v7",
                        "strategy": "scope_aware", "repetition": 1, "response_sha256": response_sha}]}
    private_key_path = root / "PRIVATE-v7-identity-key.json"
    _dump(private_key_path, identity_key)

    combined_template = copy.deepcopy(template_a)
    evidence = packet_preparer.evidence_for(case)
    evidence_ref = "E-" + hashlib.sha256(validator.canonical(evidence).encode()).hexdigest()[:16]
    combined_template["evidence_catalog"][evidence_ref] = evidence
    combined_template["queues"].append({"queue_id": "four_strategy_v7_answers",
        "title": "四策略补充实验：答案审核", "status": "待人工审核", "review_count": 1,
        "review_instruction": "对照来源和参考答案，将 answer_judgment 填为 Pass、Fail 或 Uncertain，并在 rationale 写明依据。",
        "scope_note": "已保存 1/360 条答案，最多来自同一批 30 段历史的重复运行；不显示策略、轮次和自动分数。",
        "label_choices": ["Pass", "Fail", "Uncertain"],
        "items": [{"item_id": "V7-001", "question": case["question"], "question_date": case["question_date"],
                   "reference_answer": case["answer"], "target_response": answer,
                   "evidence_refs": [evidence_ref], "source_evidence_zh": [evidence],
                   "review": {"answer_judgment": None, "rationale": ""}}]})
    counts = {row["queue_id"]: len(row["items"]) for row in combined_template["queues"]}
    combined_template["summary"] = {"counts_by_queue": counts, "total_item_records_for_review": sum(counts.values()),
                                     "evidence_catalog_entries": len(combined_template["evidence_catalog"])}
    combined_template_path = root / "combined-template" / "templates" / "reviewer-1.json"
    combined_template_path.parent.mkdir(parents=True)
    _dump(combined_template_path, combined_template)
    combined_manifest_path = root / "combined-template" / "manifest.json"
    combined_manifest = {"format": "multi-reviewer-json-v1", "master_sha256": _sha(master_path),
                        "reviewer_copies": [{"file": combined_template_path.name,
                                             "sha256": _sha(combined_template_path)}]}
    _dump(combined_manifest_path, combined_manifest)
    # The transfer tool validates enrichment deterministically; synthetic fixture uses the raw small master.
    return {"master": master_path, "baseline_manifest": baseline_manifest_path,
            "baseline_template": baseline_template_a, "baseline_return": baseline_return_a,
            "combined_manifest": combined_manifest_path, "combined_template": combined_template_path,
            "private_key": private_key_path, "v7_dir": v7_dir, "formal_material": material_path,
            "master_data": master, "output_dir": root}


class ProgressTransferTests(unittest.TestCase):
    def _transfer(self, fixture, output):
        with patch.object(validator, "_master_with_frozen_benchmark_enrichment",
                          side_effect=lambda master: copy.deepcopy(master)):
            return transfer_tool.transfer(fixture["master"], fixture["baseline_manifest"],
                fixture["baseline_template"], fixture["baseline_return"], fixture["combined_manifest"],
                fixture["combined_template"], fixture["private_key"], fixture["v7_dir"],
                fixture["formal_material"], output)

    def test_copies_baseline_progress_and_keeps_new_v7_judgments_blank(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _prepare_transfer_fixture(root)
            source_paths = [fixture[key] for key in ("master", "baseline_manifest", "baseline_template", "baseline_return",
                                                      "combined_manifest", "combined_template", "private_key",
                                                      "formal_material")]
            source_paths += [fixture["v7_dir"] / name for name in ("C-live.json", "protocol.json", "longmemeval-subset.json")]
            source_hashes = [_sha(path) for path in source_paths]
            original = validator.read_json(fixture["baseline_return"])
            output = root / "continued-review.json"
            result = self._transfer(fixture, output)
            continued = validator.read_json(output)
            queues = validator._queue_map(continued, "continued")
            old_queues = validator._queue_map(original, "baseline")
            self.assertEqual(continued["reviewer_slot"], 1)
            self.assertEqual(continued["reviewer_declaration"], original["reviewer_declaration"])
            self.assertEqual(continued["manual_confirmations_zh"], original["manual_confirmations_zh"])
            self.assertEqual(queues["proposal_ab_formal_review_216"]["additional_missing_facts"],
                             old_queues["proposal_ab_formal_review_216"]["additional_missing_facts"])
            for queue_id in transfer_tool.BASELINE_QUEUES:
                actual_items = validator._item_map(queues[queue_id], queue_id)
                old_items = validator._item_map(old_queues[queue_id], queue_id)
                self.assertEqual({key: value["review"] for key, value in actual_items.items()},
                                 {key: value["review"] for key, value in old_items.items()})
            v7_item = queues["four_strategy_v7_answers"]["items"][0]
            self.assertEqual(v7_item["review"], {"answer_judgment": None, "rationale": ""})
            self.assertEqual(result["v7_review_decisions_copied"], 0)
            self.assertEqual(source_hashes, [_sha(path) for path in source_paths])
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            sidecar = Path(result["provenance"])
            provenance = validator.read_json(sidecar)
            self.assertEqual(provenance["reviewer_slot"], 1)
            self.assertTrue(provenance["v7_decisions_left_as_template"])
            self.assertEqual(os.stat(sidecar).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                self._transfer(fixture, output)

    def test_rejects_returned_baseline_source_mutation_and_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _prepare_transfer_fixture(root)
            altered = validator.read_json(fixture["baseline_return"])
            altered["queues"][0]["items"][0]["question"] = "changed source"
            _dump(fixture["baseline_return"], altered)
            output = root / "must-not-exist.json"
            with self.assertRaisesRegex(validator.ReconciliationError, "来源证据、item 身份"):
                self._transfer(fixture, output)
            self.assertFalse(output.exists())

    def test_rejects_changed_v7_source_even_if_template_manifest_is_rehashed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = _prepare_transfer_fixture(root)
            combined = validator.read_json(fixture["combined_template"])
            combined["queues"][-1]["items"][0]["question_date"] = "2025-06-21"
            _dump(fixture["combined_template"], combined)
            manifest = validator.read_json(fixture["combined_manifest"])
            manifest["reviewer_copies"][0]["sha256"] = _sha(fixture["combined_template"])
            _dump(fixture["combined_manifest"], manifest)
            with self.assertRaisesRegex(validator.ReconciliationError, "问题、参考答案或模型回答"):
                self._transfer(fixture, root / "must-not-exist.json")


if __name__ == "__main__":
    unittest.main()
