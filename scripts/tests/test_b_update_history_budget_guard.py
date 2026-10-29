import unittest
from types import SimpleNamespace
from scripts.b_update_history_budget_guard_20261030 import guard_selected_updates

def item(i):return {'record':SimpleNamespace(id=i)}
class TestGuard(unittest.TestCase):
 def setUp(self):self.rel=[SimpleNamespace(memory_id='new',target_memory_id='old',relationship_type='UPDATE')]
 def test_old_without_new_is_removed_and_gap_recorded(self):
  kept,notice=guard_selected_updates([item('old')],self.rel,[('new','old')]);self.assertEqual(kept,[]);self.assertTrue(notice['incomplete_update_history']);self.assertEqual(notice['excluded_orphan_prior_ids'],['old'])
 def test_new_without_old_is_retained_but_gap_recorded(self):
  kept,notice=guard_selected_updates([item('new')],self.rel,[('new','old')]);self.assertEqual([x['record'].id for x in kept],['new']);self.assertTrue(notice['incomplete_update_history'])
 def test_complete_pair_is_retained(self):
  kept,notice=guard_selected_updates([item('old'),item('new')],self.rel,[('new','old')]);self.assertEqual(len(kept),2);self.assertFalse(notice['incomplete_update_history'])
 def test_unknown_pair_is_rejected(self):
  with self.assertRaises(ValueError):guard_selected_updates([item('old')],self.rel,[('other','old')])
 def test_preserves_unrelated_records(self):
  kept,_=guard_selected_updates([item('old'),item('other')],self.rel,[('new','old')]);self.assertEqual([x['record'].id for x in kept],['other'])
 def test_update_chain_does_not_leave_an_older_orphan(self):
  rel=[SimpleNamespace(memory_id='new',target_memory_id='middle',relationship_type='UPDATE'),SimpleNamespace(memory_id='middle',target_memory_id='old',relationship_type='UPDATE')]
  kept,notice=guard_selected_updates([item('middle'),item('old')],rel,[('new','middle'),('middle','old')]);self.assertEqual(kept,[]);self.assertEqual(notice['excluded_orphan_prior_ids'],['middle','old'])
if __name__=='__main__':unittest.main()
