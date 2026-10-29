import json
import unittest
from scripts import publish_ac2_ai_followup_summary as publisher


class PublishTest(unittest.TestCase):
    def inputs(self):
        return [p.read_bytes() for p in (publisher.source.ADJ,publisher.source.BASELINE,publisher.source.CONTEXT,
                                         publisher.source.OUTPUT,publisher.CONFIRMATION)]

    def test_retains_original_and_discloses_human_confirmed_ai_followup(self):
        result=publisher.build_summary(*self.inputs())
        self.assertEqual(result['status'],'human_confirmed_ai_followup')
        self.assertEqual(result['original_human_adjudicated_structural']['unresolved'],99)
        self.assertEqual(result['mixed_structural'],{'valid':8,'invalid':37,'unresolved':75,'denominator':120})
        self.assertIn('not independent blind',result['limitations'][0])
        self.assertNotIn('cases',result)

    def test_missing_confirmation_and_changed_followup_are_rejected(self):
        adj,baseline,ctx,followup,confirmation=self.inputs()
        changed=json.loads(confirmation);changed['reviewed_file_sha256']='0'*64
        with self.assertRaises(ValueError):publisher.build_summary(adj,baseline,ctx,followup,json.dumps(changed).encode())
        changed=json.loads(followup);changed['counts']['invalid']=99
        with self.assertRaises(ValueError):publisher.build_summary(adj,baseline,ctx,json.dumps(changed).encode(),confirmation)


if __name__=='__main__':unittest.main()
