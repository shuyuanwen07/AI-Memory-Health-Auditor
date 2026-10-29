import json
import unittest
from scripts.publish_ac3_development_summary import SOURCE, build


class DevelopmentSummaryTests(unittest.TestCase):
    def test_saved_counts_and_scope(self):
        report=build(SOURCE.read_bytes())
        self.assertFalse(report['independent_retest'])
        self.assertFalse(report['formal_acceptance_established'])
        hybrid=report['conditions'][0]['metrics']
        self.assertEqual((hybrid['failure_recall_conservative']['numerator'],hybrid['failure_recall_conservative']['denominator']),(56,80))
        self.assertEqual(hybrid['decided_coverage']['percentage'],73.3)
    def test_inconsistent_numbers_are_rejected(self):
        raw=json.loads(SOURCE.read_bytes());raw['hybrid']['metrics']['decided_coverage']['numerator']=119
        with self.assertRaises(ValueError):build(json.dumps(raw).encode())


if __name__=='__main__':unittest.main()
