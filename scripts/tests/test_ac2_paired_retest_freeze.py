import io
import unittest
import zipfile
from unittest.mock import patch
from scripts.ac2_paired_retest_freeze import prepare, sha


class PairedFreezeTests(unittest.TestCase):
    def setUp(self):
        self.source=b'{"cases":[{"history_id":"synthetic"}]}'
        self.baseline=b'VERSION = "rule-based-v35"'
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('app/test_generator/rule_based.py',self.baseline)
        self.archive=stream.getvalue(); self.candidate=b'VERSION = "rule-based-v36"'

    def call(self):
        return prepare(self.source,b'{}',[b'first',b'second'],self.archive,self.candidate,b'validator','a'*64)

    @patch('scripts.ac2_paired_retest_freeze.inspect',return_value={'all_items_valid_in_both_reviews':True})
    def test_binds_both_versions_without_running(self, _inspect):
        with patch('scripts.ac2_paired_retest_freeze.BASELINE_SOURCE_SHA',sha(self.baseline)):
            result=self.call()
        self.assertEqual(result['candidate_generator_sha256'],sha(self.candidate))
        self.assertFalse(result['questions_generated'])
        self.assertFalse(result['generation_supported'])

    @patch('scripts.ac2_paired_retest_freeze.inspect',return_value={'all_items_valid_in_both_reviews':False})
    def test_unreviewed_sources_are_rejected(self, _inspect):
        with self.assertRaises(ValueError): self.call()

    @patch('scripts.ac2_paired_retest_freeze.inspect',return_value={'all_items_valid_in_both_reviews':True})
    def test_changed_baseline_is_rejected(self, _inspect):
        with self.assertRaises(ValueError): self.call()
