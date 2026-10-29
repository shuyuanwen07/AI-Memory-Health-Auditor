"""Verify the source-bound AC1 retrospective counts and reject changed evidence."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from scripts.publish_ac1_retrospective_adjudicated import build, INTAKE, PACKET, RECON


class Ac1RetrospectiveTest(unittest.TestCase):
    def test_confirmed_adjudication_retains_distinct_counts_and_limits(self):
        result = build()
        self.assertEqual(result['candidate_valid'], {'numerator': 27, 'denominator': 27, 'agreed_original': 21, 'later_adjudicated': 6})
        self.assertEqual(result['reference_coverage'], {'full': 18, 'partial': 6, 'total': 24})
        self.assertTrue(any('not known to be exhaustive' in x for x in result['limitations']))
        self.assertTrue(any('do not establish AC1 acceptance' in x for x in result['limitations']))

    def test_changed_reconciliation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            recon = Path(directory) / 'reconciliation.json'
            shutil.copyfile(RECON, recon)
            data = json.loads(recon.read_text())
            data['items'][0]['item_id'] = 'tampered'
            recon.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'exact reviewed reconciliation'):
                build(INTAKE, PACKET, recon)


if __name__ == '__main__': unittest.main()
