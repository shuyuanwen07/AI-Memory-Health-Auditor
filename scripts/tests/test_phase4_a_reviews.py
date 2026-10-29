import copy,unittest
from scripts.analyse_phase4_a_reviews import analyse
class AReviewTests(unittest.TestCase):
 def setUp(self):
  self.m={'material_sha256':['frozen'],'item_ids':['A1'],'items':[{'item_id':'A1','source_messages':[{'message_id':'S1'}],'frozen_defects':[{'defect_id':'D1'}]}]};self.k={'A1':{'scenario_id':'H1','condition_label':'direct','evaluation':{'passed':None}}}
  r={'reviewer_id':'one','material_sha256':'frozen','independently_completed':True,'has_seen_automated_A_results':False,'labels':[{'item_id':'A1','verdict':'fail','failure_dimension':'accuracy','source_message_ids':['S1'],'defect_ids':['D1']}]};self.r=[r,copy.deepcopy(r)];self.r[1]['reviewer_id']='two'
 def test_uncertain_automation_does_not_detect_human_failure(self):
  g=analyse(self.m,self.k,self.r)['conditions'][0];self.assertEqual(g['failure_detection_recall_all_resolved_human_failures'],0);self.assertEqual(g['failure_discovery_rate'],1);self.assertEqual(g['auditor_detected_failure_discovery_rate'],0)
 def test_detected_failure_counts_in_both_discovery_measures(self):
  self.k['A1']['evaluation']['passed']=False
  g=analyse(self.m,self.k,self.r)['conditions'][0];self.assertEqual(g['failure_discovery_rate'],1);self.assertEqual(g['auditor_detected_failure_discovery_rate'],1)
 def test_disagreement_leaves_discovery_unmeasured(self):
  self.r[1]['labels'][0]['defect_ids']=[]
  self.assertIsNone(analyse(self.m,self.k,self.r)['conditions'][0]['failure_discovery_rate'])
 def test_duplicate_reviewer_rejected(self):
  self.r[1]['reviewer_id']=' ONE '
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_missing_mapping_rejected(self):
  self.r[0]['labels'][0]['defect_ids']=None
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_invalid_source_rejected(self):
  self.r[0]['labels'][0]['source_message_ids']=['S2']
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_exposure_is_disclosed_not_blind(self):
  self.r[0]['has_seen_automated_A_results']=True
  self.assertFalse(analyse(self.m,self.k,self.r)['blind_review_declared'])
if __name__=='__main__':unittest.main()
