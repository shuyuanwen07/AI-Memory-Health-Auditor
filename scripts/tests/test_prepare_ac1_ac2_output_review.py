"""Synthetic fixtures only; no human judgment or real run is created."""
from datetime import datetime, timezone
import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scripts.prepare_ac1_ac2_output_review import make_packets


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False)); return hashlib.sha256(path.read_bytes()).hexdigest()


class OutputReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); d=Path(self.temp.name)
        self.frozen=d/'frozen.json'; self.protocol=d/'protocol.json'; self.output=d/'output.json'
        self.frozen_data={'suite':{'cases':[{'history_id':'H1','source_messages':[{'message_id':'S1','text':'Synthetic','role':'user','order':1}]}]}}
        self.frozen_sha=save(self.frozen,self.frozen_data)
        self.protocol_data={'format':'ac1-ac2-validation-protocol-v1','status':'frozen','source_frozen_sha256':self.frozen_sha,
            'runtime_source_sha256':'runtime','frozen_at_utc':'2000-01-01T00:00:00Z','history_count':1,'generated_tests_per_history':4,
            'extractor':{'provider':'fixture'},'test_generator':{'provider':'fixture'}}
        self.protocol_sha=save(self.protocol,self.protocol_data)
        self.output_data={'format':'ac1-ac2-system-output-v1','protocol_sha256':self.protocol_sha,'source_frozen_sha256':self.frozen_sha,
            'runtime_source_sha256':'runtime','collection_started_at_utc':'2000-01-02T00:00:00Z',
            'extractor':self.protocol_data['extractor'],'test_generator':self.protocol_data['test_generator'],
            'histories':[{'history_id':'H1','source_record_id':'C1','extraction_record_id':'E1','generator_record_id':'G1',
                'extraction_status':'completed','generation_status':'completed',
                'candidates':[{'candidate_id':'M1','canonical_value':'Synthetic','source_message_ids':['S1']}],
                'relationships':[],'generated_tests':[{'test_id':'T1','prompt':'Question?','expected_behavior':'Answer', 'generator_version':'actual-generator'}]}]}
        self.stage={'reviewed_fact_plan':{'histories':{'H1':{'facts':[{'memory_id':'F1','canonical_value':'Synthetic'}],'relationships':[]}}}}
    def tearDown(self): self.temp.cleanup()
    def packets(self):
        out_sha=save(self.output,self.output_data)
        with patch('scripts.prepare_ac1_ac2_output_review.compile_mock',return_value=self.stage):
            return make_packets(self.frozen,self.frozen_sha,'0',self.protocol,self.protocol_sha,self.output,out_sha)
    def test_blank_reviews_preserve_missing_and_actual_output(self):
        a,b=self.packets(); self.assertNotEqual(a['reviewer_slot'],b['reviewer_slot'])
        self.assertIsNone(a['reviewer_declaration']['completed_by_human'])
        h=a['histories'][0]; self.assertEqual(h['missing_generated_test_count'],3)
        self.assertIsNone(h['candidates'][0]['review']['supported'])
        self.assertIsNone(h['generated_tests'][0]['review']['grounded'])
    def test_curated_ac3_question_cannot_be_misrepresented_as_generated(self):
        self.output_data['histories'][0]['generated_tests'][0]['generator_version']='ac3-quarantined-stage-v1'
        with self.assertRaisesRegex(ValueError,'curated AC3'): self.packets()
    def test_run_before_freeze_is_rejected(self):
        self.output_data['collection_started_at_utc']='1999-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'begin after'): self.packets()

if __name__=='__main__': unittest.main()
