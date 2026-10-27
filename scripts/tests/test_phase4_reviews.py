import copy,unittest
from scripts.analyse_phase4_reviews import analyse
class Phase4ReviewTests(unittest.TestCase):
 def setUp(self):
  self.manifest={'response_items':['BL1'],'question_items':['H-Q1'],'extraction_items':['H-X'],'question_source':[{'item_id':'H-Q1','source_messages':[{'message_id':'S1'}]}]}
  self.key={'BL1':{'scenario_id':'H','automated':{'passed':None}}}
  r={'reviewer_id':'A','independently_completed':True,'response_labels':[{'item_id':'BL1','verdict':'fail','failure_dimension':'accuracy','source_message_ids':['S1']}],'question_labels':[{'item_id':'H-Q1','valid':True}],'extraction_labels':[{'item_id':'H-X'}]}
  self.returns=[r,copy.deepcopy(r)];self.returns[1]['reviewer_id']='B'
 def test_uncertain_prediction_is_not_a_detected_failure(self):
  report=analyse(self.manifest,self.key,self.returns)
  self.assertEqual(report['failure_recall_all_agreed_human_failures'],0)
  self.assertIsNone(report['failure_recall_decided'])
 def test_duplicate_identity_rejected(self):
  self.returns[1]['reviewer_id']=' a '
  with self.assertRaises(ValueError):analyse(self.manifest,self.key,self.returns)
 def test_incomplete_declaration_rejected(self):
  self.returns[0]['independently_completed']=False
  with self.assertRaises(ValueError):analyse(self.manifest,self.key,self.returns)
 def test_disagreement_not_majority_gold(self):
  self.returns[1]['response_labels'][0].update(verdict='pass',failure_dimension=None)
  r=analyse(self.manifest,self.key,self.returns)
  self.assertEqual(r['unresolved_disagreements'],['BL1']);self.assertIsNone(r['failure_recall_all_agreed_human_failures'])
 def test_duplicate_items_rejected(self):
  self.returns[0]['response_labels']*=2
  with self.assertRaises(ValueError):analyse(self.manifest,self.key,self.returns)
 def test_invalid_source_rejected(self):
  self.returns[0]['response_labels'][0]['source_message_ids']=['WRONG']
  with self.assertRaises(ValueError):analyse(self.manifest,self.key,self.returns)
if __name__=='__main__':unittest.main()
