"""Verify provenance is recorded as automated, not a synthetic human signature."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import freeze_ac3_prospective_suite as freeze
from scripts import ac3_fixed_suite_adapter as adapter
from scripts.prepare_ac3_pilot_provenance_audit import build_audit, SELECTION


class PilotProvenanceAuditTests(unittest.TestCase):
    def test_saved_audit_recomputes_without_human_or_identity_claim(self):
        audit = build_audit()
        saved = json.loads((freeze.ROOT / 'output/proposal-delivery/ac3-pilot-automated-provenance-audit-2026-10-28.json').read_text())
        self.assertEqual(audit, saved)
        self.assertFalse(audit['human_attestation_created'])
        self.assertFalse(audit['identity_or_independence_authenticated'])
        self.assertIn('not independently resolved', audit['pilot_limitations'])

    def test_synthetic_run_uses_checked_audit_and_still_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp, returns = Path(directory), []
            for slot in (1, 2):
                review = json.loads((freeze.PACKET / f'grounding-reviewer-{slot}.json').read_text())
                review['reviewer_declaration'] = {'reviewer_label': f'synthetic-{slot}', 'completed_by_human': True,
                    'completed_independently': True, 'used_ai_assistance': False, 'note': 'synthetic fixture only'}
                for case in review['cases']:
                    for question in case['questions']:
                        question['review'] = {'question_validity': 'valid', 'rationale': 'synthetic fixture only'}
                path = tmp / f'review-{slot}.json'; path.write_text(json.dumps(review)); returns.append(path)
            cfg = json.loads((freeze.PACKET / 'protocol-config-template.json').read_text())
            cfg['thresholds'] = json.loads(SELECTION.read_text())['thresholds']
            cfg['human_attestations'] = {'pilot_provenance_reviewed': None, 'pilot_thresholds_accepted': True,
                'held_out_outputs_not_generated_or_inspected': True, 'exclusions_and_abstention_policy_frozen': True,
                'responsible_reviewer': 'synthetic fixture', 'provenance_note': 'synthetic fixture only'}
            cfg['model_configuration'] = {'target_provider':'ollama', 'target_model':'fixture',
                'evaluator_provider':'ollama', 'evaluator_model':'fixture', 'pipeline_provider':'ollama',
                'pipeline_model':'fixture', 'pipeline_version':'fixture', 'evaluator_implementation_version':'fixture',
                'pipeline_implementation_version':'fixture', 'target_strategy':'fixture'}
            cfg['budget']['max_new_estimated_usd'] = 0
            cfg.update({'minimum_decided_coverage':.8, 'minimum_human_failure_count':8, 'minimum_human_pass_count':8,
                'minimum_independent_histories':8, 'abstention_policy':'fixture', 'exclusion_policy':'fixture',
                'budget_enforcement_plan':'fixture', 'reference_blinding_plan':'fixture'})
            config = tmp / 'config.json'; config.write_text(json.dumps(cfg))
            audit_file = tmp / 'audit.json'; audit_file.write_text(json.dumps(build_audit()))
            output = tmp / 'frozen.json'
            cmd = [sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'),
                '--review-1',str(returns[0]), '--review-2',str(returns[1]), '--config',str(config),
                '--threshold-approval',str(SELECTION), '--pilot-provenance-audit',str(audit_file), '--output',str(output)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            frozen = json.loads(output.read_text())
            self.assertIsNone(frozen['protocol']['human_attestations']['pilot_provenance_reviewed'])
            self.assertEqual(frozen['pilot_provenance_review_method'], 'automated_source_check_not_human_attestation')
            self.assertFalse(frozen['model_called'])
            self.assertEqual(adapter.compile_mock(output, adapter.sha(output.read_bytes()), '0')['question_count'], 32)
            tampered = copy.deepcopy(build_audit()); tampered['assessor'] = 'human'
            audit_file.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, 'source file changed'):
                adapter.compile_mock(output, adapter.sha(output.read_bytes()), '0')
            other = tmp / 'new-frozen.json'; cmd[-1] = str(other)
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(other.exists())


if __name__ == '__main__':
    unittest.main()
