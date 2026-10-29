import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_ac1_ac2_confirmation import build, sha


class ConfirmedSuggestionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name); self.intake = root / 'intake'; self.intake.mkdir(); self.packet = root / 'packet.json'
        def item(criterion, kind, decision, number):
            return {'criterion': criterion, 'item_id': f'{kind}{number}', 'source': {'task': {'kind': kind, 'secret': 'private text'}}, 'human_final_decision': decision}
        self.items = ([item('AC1', 'candidate', {'valid': True}, i) for i in range(6)]
                      + [item('AC1', 'reference', {'coverage': 'partial'}, i) for i in range(3)]
                      + [item('AC2', 'question', {'valid': 'uncertain'}, i) for i in range(13)])
        facts = [{'history': str(i), 'adjudicated_value': '', 'human_final_decision': {'additional_missing_facts': ''}} for i in range(3)]
        original = {'format': 'ac1-ac2-human-adjudication-v1', '待裁定项目': [{**x, 'human_final_decision': {}} for x in self.items],
                    '遗漏事实差异': [{**x, 'adjudicated_value': None, 'human_final_decision': {}} for x in facts]}
        self.packet.write_text(json.dumps(original))
        doc = {'format': original['format'], '待裁定项目': self.items, '遗漏事实差异': facts,
               'ai_adjudication_declaration': {'source_sha256': sha(self.packet), 'completed_by_human': False, 'human_confirmation_completed': False,
                                               'used_ai_assistance': True, 'has_seen_both_reviewer_judgments': True}}
        self.ai = self.intake / 'received-ai-suggestions.json'; self.ai.write_text(json.dumps(doc))
        self.summary = self.intake / 'intake-summary.json'; self.summary.write_text(json.dumps({'source_hashes': {'received_file': sha(self.ai), 'original_packet': sha(self.packet)}}))
        self.confirmation = self.intake / 'human-confirmation-record.json'
        self.confirmation.write_text(json.dumps({'format': 'ac1-ac2-human-confirmation-v1', 'user_statement': '已逐项人工核对并认可',
          'applies_to_file_sha256': sha(self.ai), 'prior_intake_summary_sha256': sha(self.summary), 'source_packet_sha256': sha(self.packet),
          'counts': {'items': 22, 'candidate_valid_true': 6, 'reference_partial': 3, 'original_question_uncertain': 13, 'additional_missing_fact_empty': 3}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_and_privacy(self):
        result = build(self.intake, self.packet)
        self.assertEqual(result['ac2_question_uncertain'], 13)
        self.assertTrue(result['human_confirmation_user_reported'])
        self.assertFalse(result['independent_blind_adjudication'])
        self.assertNotIn('private text', json.dumps(result))

    def test_tampered_ai_or_missing_confirmation_fails(self):
        self.ai.write_text('{}')
        with self.assertRaises(ValueError):
            build(self.intake, self.packet)
        self.confirmation.write_text('{}')
        with self.assertRaises(ValueError):
            build(self.intake, self.packet)


if __name__ == '__main__':
    unittest.main()
