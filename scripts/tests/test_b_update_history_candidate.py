import unittest
from types import SimpleNamespace
from app.schemas import MemoryStrategy
from scripts.b_update_history_candidate_20261029 import include_update_history

def items(prior_state='SUPERSEDED',prior_reason='superseded',current_eligible=True):
 return [{'record':SimpleNamespace(id='new',lifecycle_state='ACTIVE'),'eligible':current_eligible,'category_match':True,'relevance':3,'reason':''},
         {'record':SimpleNamespace(id='old',lifecycle_state=prior_state),'eligible':False,'category_match':True,'relevance':0,'reason':prior_reason}]

class CandidateTest(unittest.TestCase):
 def test_only_explicit_history_restores_prior(self):
  rows=items();rel=[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')]
  include_update_history(rows,rel,'Explain what changed from the previous database.',MemoryStrategy.STRONG_RULE_BASED)
  self.assertTrue(rows[1]['eligible']);self.assertEqual(rows[1]['relevance'],3)
  for prompt in ['Which database is used now?', 'What is the current database?']:
   rows=items();include_update_history(rows,rel,prompt,MemoryStrategy.STRONG_RULE_BASED);self.assertFalse(rows[1]['eligible'])
 def test_evicted_missing_or_unrelated_not_restored(self):
  rel=[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')]
  for rows,rs in [(items('EVICTED','evicted'),rel),(items(),[]),(items(current_eligible=False),rel)]:
   include_update_history(rows,rs,'What changed from the previous value?',MemoryStrategy.STRONG_RULE_BASED)
   self.assertFalse(rows[1]['eligible'])
 def test_other_strategy_unchanged(self):
  rows=items();rel=[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')]
  include_update_history(rows,rel,'What changed from the previous value?',MemoryStrategy.WEAK_FIRST_HIT)
  self.assertFalse(rows[1]['eligible'])
if __name__=='__main__':unittest.main()
