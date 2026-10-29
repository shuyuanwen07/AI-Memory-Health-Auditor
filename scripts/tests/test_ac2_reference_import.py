import copy,json,sys,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from import_ac2_reference_reviews import aggregate,verify_outputs,sha,blind
from scripts import run_ac2_reference_generation as generation
class Tests(unittest.TestCase):
 def setUp(self):
  p=Path(__file__).resolve().parents[2]/'output/proposal-delivery';self.folder=p/'ac2-reference-generation-blind-review-2026-10-28-v1'
  with tempfile.TemporaryDirectory() as temp:
   root=p.parent.parent
   generated=Path(temp)/'packets'
   # The frozen protocol preserves its original machine path. Rebase only the
   # path passed to the reader; retain and verify the original content hash.
   original_frozen_source=generation.frozen_source
   def rebased_source(_saved_path, digest):
    return original_frozen_source(p/'ac3-expanded-primary-frozen-2026-10-28.json', digest)
   with patch.object(generation,'frozen_source',side_effect=rebased_source):
    generation.review(SimpleNamespace(protocol=p/'ac2-reference-generation-frozen-2026-10-28-v1.json',output=p/'ac2-reference-generation-output-corrected-2026-10-28-v1.json',output_dir=generated))
   self.original=[blind(json.loads((generated/f'reviewer-{i}.json').read_text())) for i in (1,2)]
  self.reviews=copy.deepcopy(self.original)
  for i,r in enumerate(self.reviews):
   r['reviewer_declaration'].update(reviewer_label=f'R{i+1}',completed_by_human=True,completed_independently=True,used_ai_assistance=False)
   for h in r['histories']:
    for t in h['generated_tests']:t['review'].update(grounded='valid',structurally_executable='valid')
  corrected=json.loads((p/'ac2-reference-generation-output-corrected-2026-10-28-v1.json').read_text());self.gate={(h['history_id'],t['test']['test_id']):t['quality_assessment']['quality_status'] for h in corrected['histories'] for t in h['tests']}
 def test_counts_and_disagreement(self):
  self.reviews[1]['histories'][0]['generated_tests'][0]['review'].update(grounded='invalid',note='test')
  d=aggregate(self.original,self.reviews,self.gate)
  self.assertEqual(d['results']['joint']['denominator'],120);self.assertEqual(d['results']['joint']['valid'],119);self.assertEqual(d['results']['joint']['unresolved'],1)
  self.assertEqual(d['joint_by_product_gate']['rejected']['denominator'],24)
 def test_unconfirmed_and_tampered(self):
  with self.assertRaises(ValueError):aggregate(self.original,self.original,self.gate)
  self.reviews[0]['histories'][0]['generated_tests'][0]['test']['prompt']='changed'
  with self.assertRaises(ValueError):aggregate(self.original,self.reviews,self.gate)
 def test_same_reviewer_and_reason(self):
  self.reviews[1]['reviewer_declaration']['reviewer_label']='R1'
  with self.assertRaises(ValueError):aggregate(self.original,self.reviews,self.gate)
  self.reviews[1]['reviewer_declaration']['reviewer_label']='R2';self.reviews[0]['histories'][0]['generated_tests'][0]['review']['grounded']='invalid'
  with self.assertRaises(ValueError):aggregate(self.original,self.reviews,self.gate)
 def test_raw_correction(self):
  p=self.folder.parent
  files=[p/'ac2-reference-generation-frozen-2026-10-28-v1.json',p/'ac2-reference-generation-started-2026-10-28-v1.json',p/'ac2-reference-generation-output-2026-10-28-v1.json',p/'ac2-reference-generation-output-corrected-2026-10-28-v1.json']
  b=[x.read_bytes() for x in files];v=list(map(json.loads,b));verify_outputs(*v,sha(b[0]),sha(b[2]))
  v[3]['histories'][0]['tests'][0]['test']['prompt']='forged'
  with self.assertRaises(ValueError):verify_outputs(*v,sha(b[0]),sha(b[2]))
if __name__=='__main__':unittest.main()
