import copy
import unittest
from scripts.reconcile_ac2_development_questions_20261029 import reconcile


def forms():
    base={'source_ledger_sha256':'ledger','items':[{'review_item_id':'Q01','source_history_id':'H1',
          'source_messages':[{'source_id':'M1','text':'original'}],'cited_facts':[{'fact':'original'}],
          'question':'Question?','reference_answer':'Answer',
          'review':{'source_support':'','question_clarity':'','reference_answer_correctness':'','overall':'','notes':''}}]}
    templates=[copy.deepcopy(base),copy.deepcopy(base)]
    for i,template in enumerate(templates,1):template['reviewer_id']=f'reviewer-{i}'
    returns=copy.deepcopy(templates)
    for item in returns:
        item['items'][0]['review'].update(source_support='valid',question_clarity='valid',reference_answer_correctness='valid',overall='valid')
    return templates,returns


class DevelopmentReviewReconciliationTests(unittest.TestCase):
    def test_preserves_disagreement_and_review_provenance(self):
        t,r=forms();r[1]['items'][0]['review']['overall']='uncertain';result=reconcile(t,r)
        self.assertEqual(result['overall_consensus'],{'unresolved':1})
        self.assertEqual(result['rows'][0]['history_id'],'H1')
        self.assertIn('require separate confirmation',result['provenance'])

    def test_rejects_changed_source_and_wrong_reviewer(self):
        for changed in ('history','reviewer','missing'):
            t,r=forms()
            if changed=='history':r[0]['items'][0]['source_history_id']='different'
            if changed=='reviewer':r[1]['reviewer_id']='reviewer-1'
            if changed=='missing':r[0]['items'][0]['review']['source_support']=''
            with self.subTest(changed=changed),self.assertRaises(ValueError):reconcile(t,r)

if __name__=='__main__':unittest.main()
