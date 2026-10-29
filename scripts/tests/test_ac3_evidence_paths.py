import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts.ac3_evidence_paths import resolve_evidence_path,resolve_frozen_source,pilot_audits_equivalent


class EvidencePathTests(unittest.TestCase):
 def test_maps_only_configured_host_output_and_rejects_escape(self):
  with tempfile.TemporaryDirectory() as root:
   output=Path(root)/'output'; output.mkdir(); (output/'v').mkdir(); (output/'v'/'e.json').write_text('{}')
   env={'AC3_HOST_PROJECT_ROOT':'/host/project','AC3_OUTPUT_ROOT':str(output)}
   with patch.dict(os.environ,env):
    self.assertEqual(resolve_evidence_path('/host/project/output/v/e.json'),output/'v'/'e.json')
    self.assertEqual(resolve_evidence_path(output/'v'/'e.json'),output/'v'/'e.json')
    with self.assertRaises(ValueError): resolve_evidence_path('/host/project/secret.json')
    with self.assertRaises(ValueError): resolve_evidence_path('/host/project/output/../secret.json')
    with self.assertRaises(ValueError): resolve_evidence_path('/different/project/output/v/e.json')
    (output/'link').symlink_to(output/'v',target_is_directory=True)
    with self.assertRaises(ValueError): resolve_evidence_path('/host/project/output/link/e.json')
 def test_remaps_only_readonly_scripts_or_output(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root); (root/'scripts').mkdir(); (root/'output').mkdir()
   (root/'scripts'/'check.py').write_text('pass')
   env={'AC3_HOST_PROJECT_ROOT':'/host/project','AC3_OUTPUT_ROOT':str(root/'output')}
   with patch.dict(os.environ,env):
    self.assertEqual(resolve_frozen_source('/host/project/scripts/check.py',root),root/'scripts'/'check.py')
    with self.assertRaises(ValueError): resolve_frozen_source('/host/project/.env',root)
 def test_pilot_report_paths_can_be_rebased_but_hashes_cannot_change(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root); (root/'output').mkdir(); (root/'scripts').mkdir()
   with patch.dict(os.environ,{'AC3_HOST_PROJECT_ROOT':'/host/project','AC3_OUTPUT_ROOT':str(root/'output')}):
    a={'format':'pilot','sources':{'evidence':{'path':'/host/project/output/x.json','sha256':'abc'}}}
    b={'format':'pilot','sources':{'evidence':{'path':str(root/'output/x.json'),'sha256':'abc'}}}
    self.assertTrue(pilot_audits_equivalent(a,b))
    b['sources']['evidence']['sha256']='changed'
    self.assertFalse(pilot_audits_equivalent(a,b))

if __name__=='__main__': unittest.main()
