"""Checks for provenance and pending-status verification of the nine-history run."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'verify_ac2_fact_slots_product_9_20261029.py'

class VerificationTest(unittest.TestCase):
    def test_rejects_a_question_that_skips_required_review(self):
        spec = importlib.util.spec_from_file_location('nine_verify', SCRIPT)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); mod.RUN = root/'run'; mod.RUN.mkdir(); mod.SOURCE = root/'sources.json'
            ids = [f'H{i}' for i in range(9)]
            mod.SOURCE.write_text(json.dumps({'conversations':[{'conversation_id':i,'messages':[{'source_id':'M1','text':'Fact'}]} for i in ids]}))
            sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            p=mod.RUN/'protocol.json';p.write_text(json.dumps({'source_sha256':sha(mod.SOURCE),'history_ids':ids,'coverage_policy':'evidence_supported_only_v1'}))
            test={'supporting_memory_ids':['m1'],'quality_status':'pending','dimension':'accuracy','generator_version':'agent-coverage-semantic-v23'}
            h={'history_id':'H0','state':'completed','requests':[
                {'path':'/conversations','state':'returned','request':{'messages':[{'message_id':'M1','content':'Fact'}]}},
                {'path':'/extract','state':'returned','response':[{'memory_id':'m1'}]},
                {'path':'/test-review','state':'returned','response':{'coverage_policy':'evidence_supported_only_v1','tests':[test]}}]}
            rows=[h]+[{'history_id':i,'state':'failed','requests':[]} for i in ids[1:]]
            ledger=mod.RUN/'ledger.json'; summary=mod.RUN/'summary.json'
            def write():
                ledger.write_text(json.dumps({'protocol_sha256':sha(p),'histories':rows}))
                summary.write_text(json.dumps({'protocol_sha256':sha(p),'ledger_sha256':sha(ledger),'saved_questions':1,'states':{'completed':1,'failed':8},'quality_states':{test['quality_status']:1},'dimensions':{'accuracy':1},'histories_with_saved_suite':1}))
            write();mod.main()
            test['quality_status']='accepted';write()
            with self.assertRaises(AssertionError):mod.main()

if __name__ == '__main__':
    unittest.main()
