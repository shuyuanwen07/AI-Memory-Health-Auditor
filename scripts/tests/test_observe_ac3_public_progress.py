"""Read-only ledger aggregates: fixture IDs and counts only."""
import unittest
from scripts.observe_ac3_public_progress import summarize,FORMATS


class LedgerSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.expected={'primary':[f'p{i}' for i in range(120)],'repeat':[f'r{i}' for i in range(40)]}
    def test_counts_and_no_private_payload(self):
        scopes=[{'scope_id':'private-scope','frozen_sha256':FORMATS['primary'],'status':'unknown'}]
        receipts=[{'scope_id':'private-scope','test_id':'p0','status':'settled'},
                  {'scope_id':'private-scope','test_id':'p1','status':'dispatched'}]
        d=summarize(self.expected,scopes,receipts)
        self.assertEqual(d['primary'],{'expected':120,'settled':1,'dispatched':1,'unknown':0,'not_dispatched':118,'scope_observed':True})
        self.assertFalse(d['repeat']['scope_observed'])
        self.assertNotIn('private-scope',str(d));self.assertNotIn('p0',str(d))
    def test_unknown_or_duplicate_receipts_rejected(self):
        scopes=[{'scope_id':'s','frozen_sha256':FORMATS['primary'],'status':'active'}]
        row={'scope_id':'s','test_id':'p0','status':'settled'}
        with self.assertRaisesRegex(ValueError,'Unexpected ledger receipt'):summarize(self.expected,scopes,[row,row])
        with self.assertRaisesRegex(ValueError,'Unexpected ledger receipt'):summarize(self.expected,scopes,[{**row,'test_id':'other'}])

if __name__=='__main__':unittest.main()
