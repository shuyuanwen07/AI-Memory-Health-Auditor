import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from import_ac1_extraction_reviews import ingest
from prepare_ac1_extraction_review import make_packets

class ImportTests(unittest.TestCase):
    def setUp(self):
        folder=Path(__file__).resolve().parents[2]/'output/proposal-delivery/ac1-extraction-human-review-2026-10-28-v1'
        root=folder.parent.parent.parent
        self.expected,_=make_packets(root/'output/proposal-delivery/ac1-extraction-frozen-2026-10-28-v1.json','6abefe61e40398dadff4b9e3558e6e647b6235e96dd909a5ccfbae62c90f9f1c',root/'output/proposal-delivery/ac1-ac2-source-only-2026-10-28-v3/reviewed-source.json',root/'output/ac3-generated/AC1-1a74cc906df755f6fc2a4855')
        self.manifest=json.loads((folder/'manifest.json').read_text());self.hashes=self.manifest['source_hashes']
        self.reviews=[copy.deepcopy(packet) for packet in self.expected]
        for i,p in enumerate(self.reviews):
            p['reviewer_declaration'].update(reviewer_label=f'Reviewer {i+1}',completed_by_human=True,completed_independently=True,used_ai_assistance=False)
            for h in p['histories']:
                for item in h['candidates']:item['review'].update(supported='invalid',note='Synthetic test decision')
                for item in h['relationships']:item['review'].update(correct='invalid',note='Synthetic test decision')
    def test_complete_and_partial_excluded(self):
        out=ingest(self.expected,self.reviews,self.hashes,self.manifest)
        self.assertEqual(out['primary_complete_histories'],29);self.assertEqual(out['partial_histories'],1)
        self.assertEqual(out['supported_candidate_precision_decided']['numerator'],0)
        sensitivity=out['sensitivity_including_partial']
        self.assertEqual(sensitivity['included_partial_histories'],1)
        partial=out['histories']['partial'][0]
        self.assertEqual(sensitivity['supported_candidate_precision_decided']['denominator'],out['supported_candidate_precision_decided']['denominator']+partial['supported']+partial['invalid'])
        self.assertEqual(sensitivity['reference_fact_id_matched_coverage']['denominator'],out['reference_fact_id_matched_coverage']['denominator']+partial['reviewed_reference_facts'])
    def test_blank_and_mutated_evidence_rejected(self):
        with self.assertRaises(ValueError):ingest(self.expected,self.expected,self.hashes,self.manifest)
        self.reviews[0]['histories'][0]['source_messages'][0]['text']='tampered'
        with self.assertRaises(ValueError):ingest(self.expected,self.reviews,self.hashes,self.manifest)
    def test_disagreement_and_unreviewed_reference(self):
        a=self.reviews[0]['histories'][0]['candidates'][0]['review'];a.update(supported='valid',note='',matched_reference_fact_ids=['AC3-H01-F1'])
        result=ingest(self.expected,self.reviews,self.hashes,self.manifest)
        self.assertEqual(result['undecided_candidates'],1)
        a['matched_reference_fact_ids']=['fake']
        with self.assertRaises(ValueError):ingest(self.expected,self.reviews,self.hashes,self.manifest)
    def test_duplicate_or_not_independent_reviewers_rejected(self):
        self.reviews[1]['reviewer_declaration']['reviewer_label']='Reviewer 1'
        with self.assertRaises(ValueError):ingest(self.expected,self.reviews,self.hashes,self.manifest)
        self.reviews[1]['reviewer_declaration'].update(reviewer_label='Reviewer 2',completed_independently=False)
        with self.assertRaises(ValueError):ingest(self.expected,self.reviews,self.hashes,self.manifest)

if __name__=='__main__':unittest.main()
