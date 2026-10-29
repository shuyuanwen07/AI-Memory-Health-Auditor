import contextlib
import io
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import prepare_ac3_prospective_inputs as inputs


class ProspectiveInputsTest(unittest.TestCase):
    def test_candidates_are_unique_blank_and_bound_to_source(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'packet'
            with patch.object(inputs, 'DEST', dest), contextlib.redirect_stdout(io.StringIO()):
                inputs.main()
            raw = (dest / 'candidate-inputs.json').read_bytes()
            data, readiness = json.loads(raw), json.loads((dest / 'readiness.json').read_text())
            self.assertEqual(readiness['input_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(len(data['cases']), 8)
            ids = [q['test_id'] for c in data['cases'] for q in c['tests']]
            self.assertEqual(len(ids), 32)
            self.assertEqual(len(set(ids)), 32)
            self.assertFalse(readiness['target_outputs_exist'])
            self.assertFalse(readiness['automatic_evaluation_results_exist'])
            self.assertIsNone(readiness['frozen_thresholds'])
            for slot in (1, 2):
                copy = json.loads((dest / f'grounding-reviewer-{slot}.json').read_text())
                self.assertEqual(copy['input_sha256'], readiness['input_sha256'])
                questions = [q for c in copy['cases'] for q in c['questions']]
                self.assertEqual(len(questions), 32)
                self.assertTrue(all(q['review']['question_validity'] is None for q in questions))


if __name__ == '__main__':
    unittest.main()
