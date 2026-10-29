import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import prepare_ac3_pilot_threshold_draft as pilot


class PilotThresholdDraftTest(unittest.TestCase):
    def test_real_development_pilot_preserves_abstentions_and_question_units(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'draft.json'
            with patch.object(pilot, 'DEST', output), contextlib.redirect_stdout(io.StringIO()):
                pilot.main()
            data = json.loads(output.read_text())
            self.assertEqual(data['pilot']['total_answers'], 24)
            self.assertEqual(data['pilot']['unique_questions'], 8)
            self.assertEqual(data['pilot']['automatic_abstentions'], 5)
            self.assertEqual((data['metrics']['failure_detection_recall']['numerator'], data['metrics']['failure_detection_recall']['denominator']), (13, 17))
            self.assertEqual((data['metrics']['failure_classification_accuracy']['numerator'], data['metrics']['failure_classification_accuracy']['denominator']), (11, 13))
            self.assertEqual((data['metrics']['false_positive_rate']['numerator'], data['metrics']['false_positive_rate']['denominator']), (0, 6))
            self.assertIn('NOT FROZEN', data['status'])

    def test_refuses_to_overwrite_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'draft.json'
            output.write_text('existing')
            with patch.object(pilot, 'DEST', output):
                with self.assertRaises(FileExistsError):
                    pilot.main()
            self.assertEqual(output.read_text(), 'existing')


if __name__ == '__main__':
    unittest.main()
