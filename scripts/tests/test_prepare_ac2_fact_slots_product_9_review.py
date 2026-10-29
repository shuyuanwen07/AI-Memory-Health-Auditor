"""Review packets must preserve omissions and hide automatic decision fields."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'prepare_ac2_fact_slots_product_9_review_20261029.py'

class ReviewPacketTest(unittest.TestCase):
    def test_source_bound_packet_with_failed_histories(self):
        spec = importlib.util.spec_from_file_location('nine_review_packet', SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod.RUN = root / 'run'; mod.RUN.mkdir()
            mod.SOURCE = root / 'sources.json'; mod.OUT = mod.RUN / 'blind-review'
            histories = [{'conversation_id': f'H{i}', 'messages': [{'source_id': 'M1', 'text': 'Original source'}]} for i in range(9)]
            mod.SOURCE.write_text(json.dumps({'conversations': histories}))
            digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            protocol = mod.RUN / 'protocol.json'
            protocol.write_text(json.dumps({'source_sha256': digest(mod.SOURCE)}))
            review = {'tests': [{'prompt': 'What?', 'expected_behavior': 'Answer', 'supporting_memory_ids': ['m'], 'quality_status': 'accepted'}]}
            rows = [{'history_id': 'H0', 'state': 'completed', 'requests': [
                {'path': '/extract', 'state': 'returned', 'response': [{'memory_id': 'm', 'canonical_value': 'Fact', 'source_message_ids': ['M1']}]},
                {'path': '/test-review', 'state': 'returned', 'response': review}]}]
            rows.extend({'history_id': f'H{i}', 'state': 'failed', 'error': 'no suite'} for i in range(1, 9))
            ledger = mod.RUN / 'ledger.json'
            ledger.write_text(json.dumps({'protocol_sha256': digest(protocol), 'histories': rows}))
            (mod.RUN / 'summary.json').write_text(json.dumps({'ledger_sha256': digest(ledger), 'saved_questions': 1, 'histories_with_saved_suite': 1}))
            mod.main()
            packet = json.loads((mod.OUT / 'reviewer-1.json').read_text())
            self.assertEqual(len(packet['items']), 1)
            self.assertEqual(packet['items'][0]['source_messages'], histories[0]['messages'])
            self.assertNotIn('quality_status', packet['items'][0])
            self.assertIsNone(packet['completed_by_human'])
            self.assertEqual(len(json.loads((mod.OUT / 'no-saved-suites.json').read_text())), 8)
            self.assertTrue((mod.OUT / '双人审核-九段复测.zip').is_file())

if __name__ == '__main__':
    unittest.main()
