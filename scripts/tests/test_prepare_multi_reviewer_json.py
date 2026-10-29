import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_multi_reviewer_json as packets


class MultiReviewerPacketTest(unittest.TestCase):
    def test_v7_review_hides_conditions_and_preserves_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subset = [{"question_id": f"q{n}", "question": f"Question {n}", "answer": "Answer",
                       "question_date": "2026-01-02", "haystack_dates": ["2026-01-01"],
                       "haystack_session_ids": [f"s{n}"], "answer_session_ids": [f"s{n}"],
                       "haystack_sessions": [[{"role": "user", "content": "Source fact"}]]}
                      for n in range(30)]
            (root / "longmemeval-subset.json").write_text(json.dumps(subset), encoding="utf-8")
            protocol = {"id": packets.V7_PROTOCOL_ID,
                        "target": {"memory_strategies": sorted(packets.STRATEGIES), "repetitions_per_strategy": 3}}
            (root / "protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
            answer = "Saved target answer"
            import hashlib
            receipt = {"repetition": 1, "strategy": "scope_aware", "question_id": "q0",
                       "response": {"response_text": answer},
                       "response_sha256": hashlib.sha256(answer.encode()).hexdigest()}
            run = {"protocol_id": packets.V7_PROTOCOL_ID, "protocol_sha256": packets.digest(root / "protocol.json"),
                   "subset_sha256": packets.digest(root / "longmemeval-subset.json"),
                   "target_configuration": {"strategies": sorted(packets.STRATEGIES), "repetitions": 3},
                   "target_receipts": [receipt]}
            (root / "C-live.json").write_text(json.dumps(run), encoding="utf-8")
            master = {"queues": [], "summary": {"counts_by_queue": {}}, "evidence_catalog": {}}
            result, private = packets.add_v7(master, root)
            item = result["queues"][0]["items"][0]
            self.assertEqual(item["target_response"], answer)
            self.assertNotIn("strategy", item)
            self.assertNotIn("repetition", item)
            self.assertEqual(item["question_date"], "2026-01-02")
            self.assertEqual(private["mapping"][0]["strategy"], "scope_aware")
            self.assertIn("Source fact", json.dumps(result["evidence_catalog"]))
            self.assertIn("2026-01-01", json.dumps(result["evidence_catalog"]))
            run["target_receipts"].append(receipt)
            (root / "C-live.json").write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaises(ValueError):
                packets.add_v7({"queues": [], "summary": {"counts_by_queue": {}}, "evidence_catalog": {}}, root)

    def test_review_copies_are_separate_and_never_overwrite(self):
        master = {"queues": [{"queue_id": "proposal_ab_formal_review_216", "source_histories": {},
                   "items": [{"item_id": "x", "evidence_refs": ["E-x"],
                   "review": {"answer_judgment": None, "rationale": ""}}]}],
                  "summary": {"counts_by_queue": {}}, "evidence_catalog": {"E-x": {"text": "source"}},
                  "reviewer_declaration": {"reviewer_label": None}, "label_definitions_zh": {}, "read_me_zh": []}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "master.json"
            material = root / "material.json"
            material.write_text('{"items":{}}', encoding="utf-8")
            master["queues"][0]["source_material_sha256"] = packets.digest(material)
            source.write_text(json.dumps(master), encoding="utf-8")
            output = root / "packets"
            with patch.object(packets, "MASTER", source), patch.object(packets, "FORMAL_MATERIAL", material), \
                 patch.object(packets, "enrich_existing_benchmark_dates"):
                packets.prepare(output, None, 2)
                a = json.loads((output / "reviewer-1.json").read_text())
                b = json.loads((output / "reviewer-2.json").read_text())
                self.assertEqual((output / "reviewer-1.json").read_bytes(),
                                 (output / "templates/reviewer-1.json").read_bytes())
                self.assertEqual(a["queues"][0]["items"][0]["source_evidence_zh"], [{"text": "source"}])
                self.assertEqual(a["queues"], b["queues"])
                self.assertNotEqual(a["reviewer_slot"], b["reviewer_slot"])
                with self.assertRaises(FileExistsError):
                    packets.prepare(output, None, 2)


if __name__ == "__main__":
    unittest.main()
