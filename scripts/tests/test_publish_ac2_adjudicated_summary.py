"""Verify actual evidence bindings; no new human judgments are created."""
import json
import unittest
import zipfile
from scripts import publish_ac2_adjudicated_summary as tool


class AdjudicationSummaryTest(unittest.TestCase):
    def inputs(self):
        summary = tool._read(tool.SUMMARY)
        reviews = [tool._read(tool.DIR / f'ac2-generation-review-intake-2026-10-28/reviewer-{i}-user-confirmed.json') for i in (1,2)]
        with zipfile.ZipFile(tool.ZIP) as archive:
            original = archive.read(tool.MEMBER)
        return summary, reviews, original, tool._read(tool.USER_COPY), tool._read(tool.CONFIRM)

    def test_user_confirmed_uncertainty_remains_unresolved(self):
        result = tool.build(*self.inputs())
        self.assertEqual(result['results']['grounded'], {'valid':109,'invalid':11,'unresolved':0,'denominator':120})
        self.assertEqual(result['results']['structurally_executable'], {'valid':8,'invalid':13,'unresolved':99,'denominator':120})
        self.assertEqual(result['adjudication_counts']['structural_uncertain'],99)
        self.assertIn('not independent blind',result['provenance'])

    def test_changed_confirmation_or_decision_is_rejected(self):
        summary,reviews,original,confirmed,confirmation = self.inputs()
        changed = json.loads(confirmed)
        changed['histories'][0]['cases'][0]['adjudication']['structurally_executable'] = 'valid'
        with self.assertRaises(ValueError):
            tool.build(summary,reviews,original,json.dumps(changed).encode(),confirmation)
        bad=json.loads(confirmation);bad['user_responses']['ac2']='not confirmed'
        with self.assertRaises(ValueError):
            tool.build(summary,reviews,original,confirmed,json.dumps(bad).encode())


if __name__ == '__main__':
    unittest.main()
