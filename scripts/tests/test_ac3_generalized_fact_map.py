"""Synthetic checks for varied message counts and cross-message relations."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from scripts.ac3_reviewed_fact_map import validate_fact_plan
from scripts.ac3_fixed_suite_adapter import mock_reservation_for_suite
from scripts.freeze_ac3_prospective_suite import validate_expanded_audit_setup
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / 'output/proposal-delivery/ac3-expanded-v5-original-reconstructed-2026-10-28'


class GeneralizedFactMapTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads((PACKET / 'candidate-inputs.json').read_text())
        self.plan = json.loads((PACKET / 'proposed-fact-plan.json').read_text())
        digest = hashlib.sha256(json.dumps(self.plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        # Test-only declarations: never written to the actual review packets.
        self.reviews = [{'reviewer_label':f'synthetic-fixture-{i}', 'completed_by_human':True,
            'completed_independently':True, 'reviewed_fact_and_relation_semantics':True,
            'fact_plan_sha256':digest} for i in (1,2)]

    def test_varied_layouts_match_explicit_question_evidence(self):
        new = self.suite['cases'][8:]
        self.assertGreater(len({len(c['source_messages']) for c in new}), 1)
        result = validate_fact_plan(self.suite, self.plan, self.reviews)
        self.assertEqual(result['history_count'], 30)
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['database_snapshot_checked'])

    def test_removing_relation_endpoint_source_is_rejected(self):
        suite = copy.deepcopy(self.suite)
        selected = next(q for c in suite['cases'][8:] for q in c['tests']
                        if q['dimension'] == 'conflict_resolution' and len(q['supporting_source_message_ids']) > 1)
        selected['supporting_source_message_ids'] = selected['supporting_source_message_ids'][:1]
        with self.assertRaisesRegex(ValueError, 'source-backed relationship'):
            validate_fact_plan(suite, self.plan, self.reviews)

    def test_questions_cannot_be_omitted_to_bypass_relation_checks(self):
        suite = copy.deepcopy(self.suite)
        suite['cases'][0]['tests'] = []
        with self.assertRaisesRegex(ValueError, 'source-linked tests'):
            validate_fact_plan(suite, self.plan, self.reviews)

    def test_mock_reservation_scales_with_actual_suite_size(self):
        frozen = {'suite': self.suite, 'protocol': {'model_configuration': {
            'target_provider':'openrouter','evaluator_provider':'rule_based','pipeline_provider':'rule_based'},
            'budget': {'max_new_estimated_usd': .20}}}
        per_call = Decimal(mock_reservation_for_suite(frozen))
        self.assertGreater(per_call, 0)
        self.assertLessEqual(per_call * 120, Decimal('.20'))
        self.assertGreater(per_call * 120, Decimal('.199999999999999999999999'))

    def test_complete_setup_is_hashed_and_missing_versions_or_changed_profile_fail(self):
        p = ROOT / 'output/proposal-delivery/ac3-protocol-review-draft-revised-2026-10-28/protocol-config-draft.json'
        model = json.loads(p.read_text())['model_configuration']
        # Version digests are synthetic fixtures, not actual runtime identity.
        model['runtime_source_sha256'] = 'a' * 64
        model['ledger_schema_sha256'] = 'b' * 64
        validate_expanded_audit_setup(model, self.suite)
        for field in ('runtime_source_sha256','ledger_schema_sha256'):
            modified=copy.deepcopy(model);modified[field]=None
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_expanded_audit_setup(modified,self.suite)
        modified=copy.deepcopy(model);modified['audit_setup']['target_memory_profile']['max_retrieved_records']=49
        with self.assertRaisesRegex(ValueError,'settings hash'):
            validate_expanded_audit_setup(modified,self.suite)
        modified=copy.deepcopy(model);modified['audit_setup']['target_memory_profile']['output_token_limit']=512
        with self.assertRaisesRegex(ValueError,'output limit'):
            validate_expanded_audit_setup(modified,self.suite)


if __name__ == '__main__':
    unittest.main()
