import copy
import json
import unittest
from scripts.prepare_v7_focused_reviews import ROOT, TEMPLATES, make, merge, queue, reconcile_returns, strategy_summary
from scripts.publish_four_strategy_human_summary import build


class FocusedV7ReviewTests(unittest.TestCase):
    def test_synthetic_return_merges_without_changing_other_queues(self):
        returned=make(1)
        for row in returned['queue']['items']:
            row['review']={'answer_judgment':'Uncertain','rationale':'Synthetic fixture'}
        returned['reviewer_declaration'].update(reviewer_label='SYNTHETIC',completed_by_human=True,
            used_ai_assistance=False,has_seen_automated_or_aggregate_results=False,completed_independently=True)
        merged=merge(1,returned)
        self.assertEqual(len(queue(merged)['items']),360)
        self.assertEqual(queue(merged)['items'][0]['review']['answer_judgment'],'Uncertain')
        self.assertEqual(len(merged['queues']),9)
        prior=json.loads((TEMPLATES/'reviewer-1-with-previous-progress.json').read_text())
        self.assertEqual([q for q in merged['queues'] if q['queue_id']!='four_strategy_v7_answers'],
                         [q for q in prior['queues'] if q['queue_id']!='four_strategy_v7_answers'])

    def test_modified_evidence_or_blank_judgments_are_rejected(self):
        returned=make(2)
        changed=copy.deepcopy(returned)
        changed['queue']['items'][0]['target_response']='tampered'
        with self.assertRaises(ValueError):merge(2,changed)
        with self.assertRaises(ValueError):merge(2,returned)

    def test_two_synthetic_returns_preserve_uncertainty_and_disagreement(self):
        docs=[make(1),make(2)]
        for n,doc in enumerate(docs):
            doc['reviewer_declaration'].update(reviewer_label=f'SYNTHETIC-{n}',completed_by_human=True,
                used_ai_assistance=False,has_seen_automated_or_aggregate_results=False,completed_independently=True)
            for item in doc['queue']['items']:
                item['review']={'answer_judgment':'Pass','rationale':'Synthetic fixture'}
        docs[1]['queue']['items'][0]['review']['answer_judgment']='Fail'
        docs[0]['queue']['items'][1]['review']['answer_judgment']='Uncertain'
        _,result=reconcile_returns(*[json.dumps(doc,ensure_ascii=False).encode() for doc in docs])
        self.assertEqual(result['counts'],{'agreed_pass':358,'agreed_fail':0,'uncertain':1,'disagreement':1})
        self.assertFalse(result['adjudicated'])
        self.assertFalse(result['automatic_scores_replaced'])
        grouped=strategy_summary(*[json.dumps(doc,ensure_ascii=False).encode() for doc in docs],
            TEMPLATES/'PRIVATE-v7-identity-key.json',ROOT/'artifacts/local/phase4-c-openrouter-20261028-v7-four-arm')
        self.assertEqual(len(grouped['strategies']),4)
        self.assertTrue(all(x['total']==90 and x['distinct_questions']==30 for x in grouped['strategies'].values()))
        self.assertEqual(sum(x['disagreement'] for x in grouped['strategies'].values()),1)
        self.assertEqual(sum(x['uncertain'] for x in grouped['strategies'].values()),1)
        public=build(*[json.dumps(doc,ensure_ascii=False).encode() for doc in docs])
        self.assertNotIn('reviewer_label',str(public))
        self.assertNotIn('SYNTHETIC',str(public))
        self.assertFalse(public['automatic_scores_replaced'])


if __name__=='__main__':unittest.main()
