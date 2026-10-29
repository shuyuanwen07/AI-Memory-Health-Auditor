import hashlib
import unittest
from unittest.mock import patch
from scripts.ac3_retest_paired_metrics import compare, paired_history_bootstrap


class PairedMetricsTests(unittest.TestCase):
    def test_errors_and_abstentions_are_not_counted_as_passes(self):
        ids=['a','b','c']; histories={'a':'h1','b':'h1','c':'h2'}
        answers=[{'test_id':'a','status':'answered','answer':'one'},
                 {'test_id':'b','status':'answered','answer':'two'},
                 {'test_id':'c','status':'target_error','answer':None}]
        def score(version, verdicts):
            return [{'test_id':i,'target_answer_sha256':hashlib.sha256(a['answer'].encode()).hexdigest() if a['answer'] else None,
                     'evaluator_version_sha256':version,'verdict':v,'failure_type':None}
                    for i,a,v in zip(ids,answers,verdicts)]
        fail={'verdict':'fail','failure_dimension':'accuracy'}; passed={'verdict':'pass','failure_dimension':None}
        reviews=[{'a':fail,'b':passed,'c':passed},{'a':fail,'b':passed,'c':passed}]
        result=compare(ids,histories,answers,score('a'*64,['error','pass','error']),
                       score('b'*64,['fail','uncertain','error']),'a'*64,'b'*64,reviews)
        self.assertEqual(result['integrity']['target_errors'],1)
        self.assertEqual(result['old']['scoring_errors'],1)
        self.assertEqual(result['old']['evidence_sufficiency'],'insufficient')
        self.assertFalse(result['old']['sample_checks']['human_failures_at_least_30'])
        self.assertEqual(result['old']['history_bootstrap']['status'],'insufficient_histories')
        self.assertEqual(result['old']['analysis']['metrics']['failure_recall_conservative']['value'],0)
        self.assertEqual(result['new']['analysis']['automatic']['category_missing'],1)
        self.assertEqual(result['new']['analysis']['automatic']['abstain_reference_pass'],1)
        self.assertEqual(result['paired_verdict_correctness']['one_or_both_scorers_undecided'],2)
        self.assertEqual(result['paired_verdict_correctness']['target_error'],1)

    def test_paired_correctness_keeps_disagreement_separate(self):
        ids=['a','b']; answers=[{'test_id':i,'status':'answered','answer':i} for i in ids]
        def score(version, verdicts):
            return [{'test_id':i,'target_answer_sha256':hashlib.sha256(i.encode()).hexdigest(),
                     'evaluator_version_sha256':version,'verdict':v,'failure_type':None}
                    for i,v in zip(ids,verdicts)]
        passed={'verdict':'pass','failure_dimension':None}; fail={'verdict':'fail','failure_dimension':'accuracy'}
        result=compare(ids,{'a':'h1','b':'h2'},answers,score('a'*64,['fail','pass']),
                       score('b'*64,['pass','fail']),'a'*64,'b'*64,
                       [{'a':passed,'b':passed},{'a':passed,'b':fail}])
        self.assertEqual(result['paired_verdict_correctness']['new_only_correct'],1)
        self.assertEqual(result['paired_verdict_correctness']['human_unresolved'],1)

    def test_missing_review_or_history_rejected(self):
        with self.assertRaises(ValueError):
            compare([],{},[],[],[],'a'*64,'b'*64,[])

    @patch('scripts.ac3_retest_paired_metrics.history_bootstrap',return_value={'status':'synthetic'})
    def test_missing_target_answers_cannot_create_sufficient_coverage(self, _bootstrap):
        ids=[f'q{i}' for i in range(120)]
        histories={ident:f'h{i//4}' for i,ident in enumerate(ids)}
        answers=[{'test_id':ident,'status':'answered' if i<60 else 'target_error',
                  'answer':ident if i<60 else None} for i,ident in enumerate(ids)]
        human={ident:{'verdict':'pass' if i%2==0 else 'fail',
                      'failure_dimension':None if i%2==0 else 'accuracy'} for i,ident in enumerate(ids)}
        def scores(version):
            return [{'test_id':ident,'target_answer_sha256':hashlib.sha256(ident.encode()).hexdigest() if i<60 else None,
                     'evaluator_version_sha256':version,'verdict':human[ident]['verdict'] if i<60 else 'error',
                     'failure_type':'accuracy' if i<60 and i%2 else None} for i,ident in enumerate(ids)]
        output=compare(ids,histories,answers,scores('a'*64),scores('b'*64),'a'*64,'b'*64,[human,human])
        checks=output['new']['sample_checks']
        self.assertTrue(checks['human_passes_at_least_30'] and checks['human_failures_at_least_30'])
        self.assertTrue(checks['decided_coverage_at_least_80_percent'])
        self.assertFalse(checks['scheduled_coverage_at_least_80_percent'])
        self.assertFalse(checks['all_frozen_histories_have_agreed_reference'])
        self.assertEqual(output['new']['scheduled_decided_coverage']['value'],.5)
        self.assertEqual(output['new']['evidence_sufficiency'],'insufficient')

    def test_paired_bootstrap_uses_same_histories_and_is_reproducible(self):
        ids=[str(i) for i in range(6)]
        answers=[{'test_id':i,'status':'answered','answer':i} for i in ids]
        def score(version, verdict):
            return [{'test_id':i,'target_answer_sha256':hashlib.sha256(i.encode()).hexdigest(),
                     'evaluator_version_sha256':version,'verdict':verdict,'failure_type':None} for i in ids]
        review={i:{'verdict':'fail','failure_dimension':'accuracy'} for i in ids}
        args=(ids,{i:f'h{i}' for i in ids},answers,score('a'*64,'pass'),score('b'*64,'fail'),
              'a'*64,'b'*64,[review,review])
        result=paired_history_bootstrap(*args,iterations=100,seed=9)
        self.assertEqual(result,paired_history_bootstrap(*args,iterations=100,seed=9))
        self.assertEqual(result['intervals']['failure_recall_conservative']['lower'],1)
        self.assertIsNone(result['intervals']['false_positive_rate_decided']['lower'])
