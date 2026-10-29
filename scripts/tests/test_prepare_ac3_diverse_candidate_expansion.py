"""Structural checks only; these do not replace independent human grounding."""
import collections
import hashlib
import json
import unittest
from scripts.prepare_ac3_diverse_candidate_expansion import OLD, OLD_PLAN, build, review_packet


class ExpandedCandidateTest(unittest.TestCase):
    def test_preserves_old_and_varies_source_structure(self):
        raw, old_plan = OLD.read_bytes(), OLD_PLAN.read_bytes()
        doc, plan, fresh = build(raw, old_plan)
        self.assertEqual(doc['cases'][:8], json.loads(raw)['cases'])
        self.assertEqual({k:plan['histories'][k] for k in json.loads(old_plan)['histories']}, json.loads(old_plan)['histories'])
        self.assertEqual((len(doc['cases']), len(fresh)), (30,22))
        self.assertEqual(collections.Counter(len(c['source_messages']) for c in fresh), {5:6, 6:6, 8:10})
        self.assertEqual(collections.Counter(q['dimension'] for c in doc['cases'] for q in c['tests']), {
            'accuracy':30,'freshness':30,'conflict_resolution':30,'appropriate_use':30})
        self.assertEqual(len({q['test_id'] for c in doc['cases'] for q in c['tests']}),120)
        for case in fresh:
            hid=case['history_id']; messages={m['message_id']:m['text'] for m in case['source_messages']}
            section=plan['histories'][hid]
            for question in case['tests']:
                self.assertTrue(question['question'] and question['expected_behavior'])
                self.assertTrue(set(question['supporting_source_message_ids']).issubset(messages))
            for fact in section['facts']:
                self.assertIn(fact['source_span'], messages[fact['source_message_id']])
                self.assertTrue(fact['canonical_value'])
            fact_ids={f['memory_id'] for f in section['facts']}
            fact_sources={f['memory_id']:f['source_message_id'] for f in section['facts']}
            for relation in section['relationships']:
                self.assertIn(relation['memory_id'], fact_ids)
                self.assertIn(relation['target_memory_id'], fact_ids)
                self.assertTrue(set(relation['evidence_message_ids']).issubset(messages))
                self.assertTrue({fact_sources[relation['memory_id']],fact_sources[relation['target_memory_id']]}
                    .issubset(relation['evidence_message_ids']))
            for question in case['tests']:
                expected_relation={'freshness':'UPDATE','conflict_resolution':'CONFLICT','appropriate_use':'CONTEXTUAL_OVERRIDE'}.get(question['dimension'])
                if expected_relation:
                    relation=next(r for r in section['relationships'] if r['relationship_type']==expected_relation)
                    self.assertTrue(set(relation['evidence_message_ids']).issubset(question['supporting_source_message_ids']))

    def test_review_packets_are_blank_and_consistent(self):
        doc,plan,fresh=build(OLD.read_bytes(), OLD_PLAN.read_bytes())
        source=hashlib.sha256(json.dumps(doc,ensure_ascii=False,indent=2).encode()).hexdigest()
        planhash=hashlib.sha256(json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        packets=[review_packet(fresh,plan,source,planhash,slot) for slot in (1,2)]
        self.assertEqual([p['reviewer_slot'] for p in packets],[1,2])
        for packet in packets:
            self.assertEqual(len(packet['cases']),22)
            self.assertIsNone(packet['reviewer_declaration']['completed_by_human'])
            for item in packet['cases']:
                self.assertTrue(all(q['review']['question_validity'] is None for q in item['questions']))
                self.assertIsNone(item['fact_review']['decision'])
                self.assertTrue(all(r['review']['decision'] is None for r in item['relationship_checks']))
                self.assertIsNone(item['additional_source_facts_missing'])


if __name__ == '__main__': unittest.main()
