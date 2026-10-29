"""The existing selector must not be presumed to preserve update pairs."""
import unittest
from types import SimpleNamespace
from app.memory_agent.store import SqlTargetMemoryStore
from app.schemas import MemoryStrategy
from app.schemas.target_profile import TargetMemoryProfile

def make(i,order):
 return {'record':SimpleNamespace(id=i,canonical_value=i,write_order=order,observed_at=None),
         'test_prompt':'How did the database change from the previous value?', 'reason':'', 'conflict_targets':[]}

class BudgetTest(unittest.TestCase):
 def test_one_slot_can_deliver_only_one_side_of_update(self):
  store=SqlTargetMemoryStore(None,profile=TargetMemoryProfile(max_retrieved_records=1,context_character_budget=100))
  selected=store._apply_profile([make('old',1),make('new',2)],SimpleNamespace(prompt='How did the database change from the previous value?'),MemoryStrategy.STRONG_RULE_BASED)
  self.assertEqual([x['record'].id for x in selected],['new'])
 def test_two_slots_can_deliver_both(self):
  store=SqlTargetMemoryStore(None,profile=TargetMemoryProfile(max_retrieved_records=2,context_character_budget=100))
  selected=store._apply_profile([make('old',1),make('new',2)],SimpleNamespace(prompt='How did the database change from the previous value?'),MemoryStrategy.STRONG_RULE_BASED)
  self.assertEqual([x['record'].id for x in selected],['old','new'])
if __name__=='__main__':unittest.main()
