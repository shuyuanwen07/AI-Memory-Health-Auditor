import json
import unittest
from scripts import review_ac2_uncertain_with_context as review


class FollowupTest(unittest.TestCase):
    def inputs(self):
        return [p.read_bytes() for p in (review.ADJ, review.BASELINE, review.CONTEXT)]

    def test_each_uncertain_case_is_accounted_for_without_forging_human_review(self):
        result=review.build(*self.inputs())
        self.assertEqual(result['counts'], {'invalid':24,'uncertain':75})
        self.assertEqual(len(result['cases']),99)
        self.assertEqual(len({(c['history_id'],c['test_id']) for c in result['cases']}),99)
        self.assertTrue(all(c['human_adjudication']=='uncertain' for c in result['cases']))
        self.assertIn('AI-only',result['mixed_supplemental_summary']['qualification'])
        self.assertIn('silence',result['user_authorization']['note'])

    def test_changed_context_or_adjudication_is_rejected(self):
        adj,base,ctx=self.inputs()
        changed=json.loads(ctx);changed['input_sha256']='0'*64
        with self.assertRaises(ValueError):
            review.build(adj,base,json.dumps(changed).encode())
        changed=json.loads(adj);changed['histories'][0]['cases'][0]['question']='changed'
        with self.assertRaises(ValueError):
            review.build(json.dumps(changed).encode(),base,ctx)


if __name__=='__main__':unittest.main()
