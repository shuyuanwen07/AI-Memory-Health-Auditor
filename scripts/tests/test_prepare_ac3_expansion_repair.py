"""Synthetic structure checks do not replace review by two people."""
import copy
import json
import unittest
from scripts.prepare_ac3_expansion_repair import PARENT, CHANGED, build


class ExpandedRevisionTest(unittest.TestCase):
    def test_only_selected_histories_change_and_all_citations_bind(self):
        source_raw=(PARENT/'candidate-inputs.json').read_bytes(); plan_raw=(PARENT/'proposed-fact-plan.json').read_bytes()
        source,plan=build(source_raw,plan_raw)
        old_source=json.loads(source_raw); old_plan=json.loads(plan_raw)
        for old,new in zip(old_source['cases'],source['cases']):
            hid=old['history_id']
            if hid not in CHANGED:
                self.assertEqual(old,new)
                self.assertEqual(old_plan['histories'][hid],plan['histories'][hid])
        self.assertEqual(len(source['cases']),30)
        self.assertEqual(sum(len(c['tests']) for c in source['cases']),120)
        self.assertEqual(len(CHANGED),10)

    def test_tampered_parent_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'differ from v5'):
            build((PARENT/'candidate-inputs.json').read_bytes()+b' ',(PARENT/'proposed-fact-plan.json').read_bytes())

    def test_delta_review_packets_are_empty_and_exactly_changed_histories(self):
        from pathlib import Path
        directory=Path(__file__).resolve().parents[2]/'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v6'
        for slot in (1,2):
            d=json.loads((directory/f'reviewer-{slot}.json').read_text())
            self.assertEqual([c['history_id'] for c in d['cases']],CHANGED)
            self.assertIsNone(d['reviewer_declaration']['completed_by_human'])
            for case in d['cases']:
                self.assertTrue(all(q['review']['question_validity'] is None for q in case['questions']))
                self.assertIsNone(case['fact_review']['decision'])
                self.assertTrue(all(r['review']['decision'] is None for r in case['relationship_checks']))


if __name__ == '__main__': unittest.main()
