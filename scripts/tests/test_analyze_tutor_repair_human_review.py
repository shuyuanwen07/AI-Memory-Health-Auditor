import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import analyze_tutor_repair_human_review as analysis


class TutorHumanReviewAnalysisTest(unittest.TestCase):
    def test_real_packet_reconciles_and_keeps_automatic_abstentions_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'summary.json'
            with patch.object(analysis, 'OUTPUT', output), contextlib.redirect_stdout(io.StringIO()):
                analysis.main()
            data = json.loads(output.read_text())
            self.assertEqual([row['pass'] for row in data['conditions']], [1, 1, 5])
            self.assertEqual(data['paired_original_to_target'], {'both_pass': 1, 'target_only_pass': 4, 'original_only_pass': 0, 'both_fail': 3})
            self.assertEqual(data['automatic_vs_human'], {'decided_agree': 19, 'decided_disagree': 0, 'automatic_uncertain_human_pass': 1, 'automatic_uncertain_human_fail': 4})

    def test_rejects_a_review_key_changed_after_freezing(self):
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / 'packet'
            shutil.copytree(analysis.PACKET, packet)
            key = packet / 'review-key-private.json'
            data = json.loads(key.read_text())
            data['rows'][0]['condition'] = 'changed'
            key.write_text(json.dumps(data))
            with patch.object(analysis, 'PACKET', packet), patch.object(analysis, 'OUTPUT', Path(directory) / 'summary.json'):
                with self.assertRaisesRegex(ValueError, 'frozen hash'):
                    analysis.main()


if __name__ == '__main__':
    unittest.main()
