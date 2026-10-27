"""Synthetic validator fixtures only; never independent research annotations."""
import copy,unittest
from scripts.phase4_formal_review import analyse
class FormalReviewTests(unittest.TestCase):
 def setUp(self):
  self.m={'histories':{'H':[{'message_id':'S'}]},'items':{'R':{'kind':'response','study':'A','history':'H','defects':[{'defect_id':'D'}]},'Q':{'kind':'question','history':'H'},'C':{'kind':'candidate','history':'H'},'G':{'kind':'reference','history':'H','candidate_ids':['C']},'E':{'kind':'relationship','history':'H'}}}
  self.k={'material_sha256':['frozen'],'known_result_exposed_reviewer_ids':['exposed'],'items':{'R':{'condition':'A:H:method','known_defect_ids':['D'],'automated':{'passed':False,'failure_type':None,'failure_classification':{'status':'unclassified'}}},'Q':{'dimension':'accuracy'},'E':{'predicted_type':'NONE'}},'question_conditions':{'Q':['A:H:method']}}
  r={'schema_version':'phase4-complete-review-v1','material_sha256':'frozen','reviewer_id':'one','completed_by_human':True,'completed_independently':True,'has_seen_automated_results':False,'used_ai_assistance':False,'additional_missing_facts':{'H':''},'labels':{'R':{'verdict':'fail','failure_dimension':'accuracy','critical_error':'no','source_message_ids':['S'],'defect_ids':['D']},'Q':{'valid':True},'C':{'valid':True},'G':{'valid':True,'coverage':'full','candidate_ids':['C']},'E':{'relationship_type':'UPDATE'}}}
  self.r=[r,copy.deepcopy(r)];self.r[1]['reviewer_id']='two'
 def test_complete_actual_declarations_enable_calculation_not_identity_authentication(self):
  x=analyse(self.m,self.k,self.r);self.assertTrue(x['formal_ready']);self.assertEqual(x['formal_failure_discovery_rates'][0]['failure_discovery_rate'],1);self.assertEqual(x['failure_classification']['joint_detection_classification_recall'],0);self.assertEqual(x['relationship_accuracy_on_declared_pairs'],0)
 def test_duplicate_reviewer_rejected(self):
  self.r[1]['reviewer_id']=' ONE '
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_blank_completion_rejected(self):
  self.r[0]['completed_by_human']=False
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_missing_item_rejected(self):
  del self.r[1]['labels']['Q']
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_invalid_source_rejected(self):
  self.r[0]['labels']['R']['source_message_ids']=['other']
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_invalid_defect_rejected(self):
  self.r[0]['labels']['R']['defect_ids']=['invented']
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_exposure_or_AI_assistance_blocks_formal_gold(self):
  for field in ['has_seen_automated_results','used_ai_assistance']:
   with self.subTest(field=field):
    reviews=copy.deepcopy(self.r);reviews[0][field]=True;self.assertFalse(analyse(self.m,self.k,reviews)['formal_ready'])
 def test_known_prior_exposure_is_not_erased_by_an_unexposed_checkbox(self):
  self.r[0]['reviewer_id']='exposed';self.assertFalse(analyse(self.m,self.k,self.r)['formal_ready'])
 def test_undefined_category_does_not_discard_detection_agreement(self):
  self.r[1]['labels']['R']['failure_dimension']='freshness';x=analyse(self.m,self.k,self.r);self.assertEqual(x['failure_detection']['A']['counts']['tp'],1);self.assertFalse(x['formal_ready'])
 def test_uncertain_answer_cannot_produce_full_discovery(self):
  for r in self.r:r['labels']['R'].update(verdict='uncertain',failure_dimension=None,defect_ids=[])
  x=analyse(self.m,self.k,self.r);self.assertIsNone(x['conditions'][0]['failure_discovery_rate']);self.assertFalse(x['formal_ready'])
 def test_mapping_disagreement_blocks_discovery(self):
  self.r[1]['labels']['R']['defect_ids']=[];x=analyse(self.m,self.k,self.r);self.assertIsNone(x['formal_failure_discovery_rates'][0]['failure_discovery_rate'])
 def test_full_recall_cannot_cite_a_rejected_candidate(self):
  self.r[0]['labels']['C']['valid']=False
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_new_missing_gold_units_require_actual_reconciliation(self):
  self.r[0]['additional_missing_facts']['H']='A source fact is missing.';x=analyse(self.m,self.k,self.r);self.assertIsNone(x['memory_reference_unit_recall']);self.assertFalse(x['formal_ready'])
 def test_packet_tampering_rejected(self):
  self.r[0]['material_sha256']='other'
  with self.assertRaises(ValueError):analyse(self.m,self.k,self.r)
 def test_no_positive_reference_leaves_recall_undefined(self):
  for r in self.r:r['labels']['R'].update(verdict='pass',failure_dimension=None,defect_ids=[])
  x=analyse(self.m,self.k,self.r);self.assertIsNone(x['failure_detection']['A']['recall_decided']);self.assertEqual(x['failure_detection']['A']['precision_decided'],0)

 def test_invalid_question_is_a_measurable_validity_result_not_a_forced_pass(self):
  for r in self.r:r['labels']['Q']['valid']=False
  x=analyse(self.m,self.k,self.r);self.assertTrue(x['formal_ready']);self.assertEqual(x['test_validity'],0);self.assertEqual(x['conditions'][0]['category_coverage'],0)
 def test_zero_precision_and_recall_have_zero_f1(self):
  self.k['items']['R']['automated']['passed']=True
  self.m['items']['R2']=copy.deepcopy(self.m['items']['R']);self.k['items']['R2']=copy.deepcopy(self.k['items']['R']);self.k['items']['R2']['automated']['passed']=False
  for r in self.r:r['labels']['R2']={**copy.deepcopy(r['labels']['R']),'verdict':'pass','failure_dimension':None,'defect_ids':[]}
  self.assertEqual(analyse(self.m,self.k,self.r)['failure_detection']['A']['f1_decided'],0)

class FormalImportPlanTests(unittest.TestCase):
 def setUp(self):
  base=FormalReviewTests();base.setUp();self.m,self.k,self.r=base.m,base.k,base.r;self.k['items']['R'].update(current_run_id='current',current_evaluation_id='CE',source_run_id='source',source_evaluation_id='SE',source_response_id='SR',source_test_id='ST',comparison_id='comparison',inventory_fingerprint_sha256='a'*64)
 def test_import_plan_uses_actual_explicit_mapping_and_named_returns(self):
  from scripts.import_phase4_complete_review import plan_import
  report,ops=plan_import(self.m,self.k,self.r);self.assertTrue(report['formal_ready']);self.assertEqual(len(ops),5);self.assertEqual(ops[-1]['body']['entries'][0]['defect_ids'],['D']);self.assertEqual({o['body']['reviewer_label'] for o in ops[:-1]},{'one','two'})
 def test_import_plan_rejects_AI_assisted_returns(self):
  from scripts.import_phase4_complete_review import plan_import
  self.r[0]['used_ai_assistance']=True
  with self.assertRaises(ValueError):plan_import(self.m,self.k,self.r)
 def test_import_plan_does_not_infer_a_defect_from_a_failure_dimension(self):
  from scripts.import_phase4_complete_review import plan_import
  for r in self.r:r['labels']['R']['defect_ids']=[]
  _,ops=plan_import(self.m,self.k,self.r);self.assertEqual(ops[-1]['body']['entries'][0]['defect_ids'],[])

if __name__=='__main__':unittest.main()
