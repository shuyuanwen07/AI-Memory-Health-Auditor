"""User-selected thresholds are source-bound; all reviews here are synthetic."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import freeze_ac3_prospective_suite as freeze
from scripts import ac3_fixed_suite_adapter as adapter


class UserThresholdSelectionTest(unittest.TestCase):
    def test_selection_validation_rejects_incomplete_or_mismatched_records(self):
        raw = freeze.PILOT.read_bytes()
        pilot, digest = json.loads(raw), freeze.sha(raw)
        values = {**pilot['proposed_thresholds'], 'failure_detection_recall_min': .8}
        config = {'pilot_draft_sha256': digest, 'thresholds': values}
        record = {'format': 'ac3-user-selected-thresholds-v1', 'recorded_at_utc': '2026-01-01T00:00:00+00:00',
                  'user_response': 'synthetic fixture only', 'selection_basis': 'synthetic choice',
                  'provenance_limitations': 'synthetic pilot, do not use as human evidence',
                  'thresholds': values, 'pilot_draft_sha256': digest, 'held_out_results_seen': False}
        self.assertEqual(freeze.validate_threshold_selection(config, pilot, digest, record), 'user_adjusted')
        with self.assertRaisesRegex(ValueError, 'Changed thresholds require'):
            freeze.validate_threshold_selection(config, pilot, digest)
        for patch in ({'thresholds': pilot['proposed_thresholds']}, {'pilot_draft_sha256': '0' * 64},
                      {'held_out_results_seen': True}, {'user_response': ''},
                      {'provenance_limitations': ''}, {'recorded_at_utc': '2026-01-01T00:00:00'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                freeze.validate_threshold_selection(config, pilot, digest, {**record, **patch})
        with self.assertRaises(ValueError):
            freeze.validate_threshold_selection({**config, 'thresholds': {**values, 'false_positive_rate_max': float('nan')}}, pilot, digest, record)

    def test_synthetic_freeze_binds_record_and_detects_later_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp, returns = Path(directory), []
            for slot in (1, 2):
                data = json.loads((freeze.PACKET / f'grounding-reviewer-{slot}.json').read_text())
                data['reviewer_declaration'] = {'reviewer_label': f'fixture-{slot}', 'completed_by_human': True,
                    'completed_independently': True, 'used_ai_assistance': False, 'note': 'synthetic fixture only'}
                for case in data['cases']:
                    for question in case['questions']:
                        question['review'] = {'question_validity': 'valid', 'rationale': 'synthetic fixture only'}
                path = tmp / f'review-{slot}.json'; path.write_text(json.dumps(data)); returns.append(path)
            cfg = json.loads((freeze.PACKET / 'protocol-config-template.json').read_text())
            cfg['thresholds']['failure_detection_recall_min'] = .8
            cfg['human_attestations'] = {'pilot_provenance_reviewed': True, 'pilot_thresholds_accepted': True,
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
            approval = {'format':'ac3-user-selected-thresholds-v1', 'recorded_at_utc':'2026-01-01T00:00:00+00:00',
                'user_response':'synthetic fixture only', 'selection_basis':'fixture selection',
                'provenance_limitations':'fixture limitations', 'pilot_draft_sha256':cfg['pilot_draft_sha256'],
                'thresholds':cfg['thresholds'], 'held_out_results_seen':False}
            config_path = tmp / 'config.json'; config_path.write_text(json.dumps(cfg))
            approval_path = tmp / 'approval.json'; approval_path.write_text(json.dumps(approval))
            out = tmp / 'frozen.json'
            cmd = [sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'),
                '--review-1',str(returns[0]), '--review-2',str(returns[1]), '--config',str(config_path),
                '--threshold-approval',str(approval_path), '--output',str(out)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(out.read_text())
            self.assertEqual(data['threshold_selection'], 'user_adjusted')
            self.assertEqual(data['threshold_approval_source'], str(approval_path))
            self.assertFalse(data['model_called'])
            digest = adapter.sha(out.read_bytes())
            self.assertEqual(adapter.compile_mock(out, digest, '0')['question_count'], 32)
            approval_path.write_text(json.dumps({**approval, 'user_response':'modified'}))
            with self.assertRaisesRegex(ValueError, 'source file changed'):
                adapter.compile_mock(out, digest, '0')


if __name__ == '__main__':
    unittest.main()
