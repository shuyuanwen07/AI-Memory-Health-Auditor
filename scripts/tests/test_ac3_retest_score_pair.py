import unittest
from scripts.ac3_retest_score_pair import score_saved_answers


class ScorePairTests(unittest.TestCase):
    def test_same_answer_mutation_isolation_and_missing_answer(self):
        items=[{'test_id':'q1','reference':{'fact':'Tuesday'}},{'test_id':'q2'}]
        answers=[{'test_id':'q1','status':'answered','answer':'Tuesday'},
                 {'test_id':'q2','status':'target_error','answer':None}]
        observed=[]
        def old(item, answer):
            item['reference']['fact']='changed locally'
            observed.append(answer)
            return {'verdict':'fail','failure_type':'accuracy'}
        def new(item, answer):
            self.assertEqual(item['reference']['fact'],'Tuesday')
            observed.append(answer)
            return {'verdict':'pass','failure_type':None}
        result=score_saved_answers(items,answers,'a'*64,'b'*64,old,new)
        self.assertEqual(observed,['Tuesday','Tuesday'])
        self.assertEqual(result['old'][0]['target_answer_sha256'],result['new'][0]['target_answer_sha256'])
        self.assertEqual(result['old'][1]['verdict'],'error')
        self.assertEqual(result['new'][1]['verdict'],'error')
        self.assertEqual(items[0]['reference']['fact'],'Tuesday')

    def test_scoring_errors_preserved_and_invalid_versions_rejected_before_call(self):
        calls=[]
        def fail(item, answer):
            calls.append(item['test_id'])
            raise RuntimeError('fixture')
        items=[{'test_id':'q1'}]
        answers=[{'test_id':'q1','status':'answered','answer':'response'}]
        with self.assertRaises(ValueError):
            score_saved_answers(items,answers,'a'*64,'a'*64,fail,fail)
        self.assertEqual(calls,[])
        result=score_saved_answers(items,answers,'a'*64,'b'*64,fail,lambda *_:{'verdict':'uncertain'})
        self.assertEqual(result['old'][0]['error_type'],'RuntimeError')
        self.assertEqual(result['new'][0]['error_type'],'SkippedAfterPriorScoringError')
        self.assertEqual(result['halted_at']['scorer'],'old')

    def test_later_items_are_not_scored_after_provider_error(self):
        items=[{'test_id':'q1'},{'test_id':'q2'}]
        answers=[{'test_id':q['test_id'],'status':'answered','answer':'x'} for q in items]
        calls=[]
        def old(item,answer):calls.append(('old',item['test_id']));return {'verdict':'pass'}
        def new(item,answer):calls.append(('new',item['test_id']));raise RuntimeError('unknown outcome')
        result=score_saved_answers(items,answers,'a'*64,'b'*64,old,new)
        self.assertEqual(calls,[('old','q1'),('new','q1')])
        self.assertEqual(result['old'][1]['error_type'],'SkippedAfterPriorScoringError')
        self.assertEqual(result['new'][1]['error_type'],'SkippedAfterPriorScoringError')


if __name__ == '__main__':
    unittest.main()
