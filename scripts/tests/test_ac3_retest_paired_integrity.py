"""Synthetic paired outcomes; these are not experiment results."""
import copy
import hashlib
import unittest
from scripts.ac3_retest_paired_integrity import validate_paired_records


class PairIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.ids = ['test-1', 'test-2']; self.old='a'*64; self.new='b'*64
        self.answers=[{'test_id':'test-1','status':'answered','answer':'synthetic'},
                      {'test_id':'test-2','status':'target_error','answer':None}]
        digest=hashlib.sha256(b'synthetic').hexdigest()
        self.old_rows=[{'test_id':'test-1','target_answer_sha256':digest,'evaluator_version_sha256':self.old,'verdict':'fail','failure_type':None},
                       {'test_id':'test-2','target_answer_sha256':None,'evaluator_version_sha256':self.old,'verdict':'error','failure_type':None}]
        self.new_rows=copy.deepcopy(self.old_rows)
        for row in self.new_rows: row['evaluator_version_sha256']=self.new
        self.new_rows[0].update(verdict='uncertain',failure_type=None)

    def validate(self):
        return validate_paired_records(self.ids,self.answers,self.old_rows,self.new_rows,self.old,self.new)

    def test_pair_and_abstention(self):
        result=self.validate(); self.assertTrue(result['answer_pairing_verified']); self.assertEqual(result['target_errors'],1)

    def test_reject_different_answer_or_omission(self):
        self.new_rows[0]['target_answer_sha256']='c'*64
        with self.assertRaises(ValueError): self.validate()
        self.new_rows.pop()
        with self.assertRaises(ValueError): self.validate()

    def test_reject_fictitious_score_on_target_error(self):
        self.new_rows[1]['verdict']='pass'
        with self.assertRaises(ValueError): self.validate()

    def test_reject_category_on_nonfailure_or_unknown_category(self):
        self.new_rows[0]['failure_type']='accuracy'
        with self.assertRaises(ValueError): self.validate()
        self.new_rows[0].update(verdict='fail', failure_type='invented')
        with self.assertRaises(ValueError): self.validate()
        self.new_rows[0]['failure_type']='accuracy'
        self.assertTrue(self.validate()['answer_pairing_verified'])
