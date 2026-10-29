import unittest
from types import SimpleNamespace
from app.schemas import MemoryStrategy
from scripts.b_update_history_candidate_v2_20261029 import include_update_history

def case(current,prior):
 return [{'record':SimpleNamespace(id='new',lifecycle_state='ACTIVE',canonical_value=current),'eligible':True,'category_match':True,'relevance':3,'reason':''},
         {'record':SimpleNamespace(id='old',lifecycle_state='SUPERSEDED',canonical_value=prior),'eligible':False,'category_match':True,'relevance':0,'reason':'superseded'}]
class ScopeTest(unittest.TestCase):
 def test_same_named_project_can_include_prior(self):
  c=case('The Cobalt project now uses PostgreSQL.','The Cobalt project previously used MySQL.')
  include_update_history(c,[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')],'How did the Cobalt project database change?',MemoryStrategy.STRONG_RULE_BASED)
  self.assertTrue(c[1]['eligible'])
 def test_other_project_or_cross_project_link_does_not_include_prior(self):
  for new,old in [('The Willow project uses PostgreSQL.','The Willow project previously used MySQL.'),('The Cobalt project uses PostgreSQL.','The Willow project previously used MySQL.')]:
   c=case(new,old);include_update_history(c,[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')],'How did the Cobalt project database change?',MemoryStrategy.STRONG_RULE_BASED)
   self.assertFalse(c[1]['eligible'])
 def test_unscoped_question_does_not_reinstate_cross_project_link(self):
  c=case('The Cobalt project uses PostgreSQL.','The Willow project previously used MySQL.')
  include_update_history(c,[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')],'How did the database change?',MemoryStrategy.STRONG_RULE_BASED)
  self.assertFalse(c[1]['eligible'])
if __name__=='__main__':unittest.main()
