import copy
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.reconcile_final_review_zip_20261029 import GROUPS, parse_archive, reconcile_bundle
from scripts.tests.test_reconcile_ac2_four_dimension_human import filled
from scripts.tests.test_reconcile_ac2_development_questions import forms


class FinalReviewZipTests(unittest.TestCase):
    def test_reconciles_all_groups_without_human_inference(self):
        source,questions,source_templates,question_templates=filled()
        development_templates,development=forms()
        names=list(GROUPS)
        templates={names[0]:source_templates,names[1]:question_templates}
        returns={names[0]:source,names[1]:questions}
        for name in names[2:]:
            templates[name]=copy.deepcopy(development_templates)
            returns[name]=copy.deepcopy(development)
        returns[names[4]][1]['items'][0]['review']['overall']='uncertain'
        result=reconcile_bundle(templates,returns)
        self.assertEqual(result[names[4]]['overall_consensus'],{'unresolved':1})
        self.assertIn('require separate confirmation',result[names[4]]['provenance'])
        returns[names[3]][0]['items'][0]['source_history_id']='tampered'
        with self.assertRaises(ValueError):reconcile_bundle(templates,returns)

    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'duplicate.zip';name=next(iter(GROUPS))+'/reviewer-1.json'
            with ZipFile(p,'w') as archive:
                archive.writestr(name,json.dumps({}))
                with self.assertWarns(UserWarning):archive.writestr(name,json.dumps({}))
            with self.assertRaises(ValueError):parse_archive(p)

if __name__=='__main__':unittest.main()
