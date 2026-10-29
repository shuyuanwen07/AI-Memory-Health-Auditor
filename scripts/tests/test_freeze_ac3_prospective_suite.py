import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import freeze_ac3_prospective_suite as freeze
from scripts import ac3_fixed_suite_adapter as adapter


class FreezeAC3Test(unittest.TestCase):
    def test_normalized_duplicate_or_blank_reviewer_names_are_not_ready(self):
        script = freeze.ROOT / 'scripts/check_ac3_prospective_readiness.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for labels in [(' Reviewer ', 'reviewer'), ('   ', 'other')]:
                paths = []
                for slot, label in enumerate(labels, 1):
                    data = json.loads((freeze.PACKET / f'grounding-reviewer-{slot}.json').read_text())
                    data['reviewer_declaration'] = {'reviewer_label': label, 'completed_by_human': True, 'completed_independently': True, 'used_ai_assistance': False, 'note': 'fixture'}
                    for case in data['cases']:
                        for question in case['questions']:
                            question['review'] = {'question_validity': 'valid', 'rationale': 'fixture'}
                    path = root / f'return-{slot}.json'
                    path.write_text(json.dumps(data))
                    paths.append(path)
                proc = subprocess.run([sys.executable, str(script), '--review-1', str(paths[0]), '--review-2', str(paths[1])], capture_output=True, text=True, check=True)
                self.assertFalse(json.loads(proc.stdout)['grounding_ready_for_adjudication'])

    def test_blank_real_reviews_cannot_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'out.json'
            proc = subprocess.run([sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'), '--review-1', str(freeze.PACKET / 'grounding-reviewer-1.json'), '--review-2', str(freeze.PACKET / 'grounding-reviewer-2.json'), '--config', str(freeze.PACKET / 'protocol-config-template.json'), '--output', str(out)], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('complete independent source reviews', proc.stderr)
            self.assertFalse(out.exists())

    def test_synthetic_fixture_freezes_inputs_but_never_executes_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            returns = []
            for slot in (1, 2):
                data = json.loads((freeze.PACKET / f'grounding-reviewer-{slot}.json').read_text())
                data['reviewer_declaration'] = {'reviewer_label': f'test-only-{slot}', 'completed_by_human': True, 'completed_independently': True, 'used_ai_assistance': False, 'note': 'synthetic test fixture only'}
                for case in data['cases']:
                    for question in case['questions']:
                        question['review'] = {'question_validity': 'valid', 'rationale': 'synthetic test fixture only'}
                path = tmp / f'review-{slot}.json'; path.write_text(json.dumps(data)); returns.append(path)
            cfg = json.loads((freeze.PACKET / 'protocol-config-template.json').read_text())
            cfg['human_attestations'] = {'pilot_provenance_reviewed': True, 'pilot_thresholds_accepted': True, 'held_out_outputs_not_generated_or_inspected': True, 'exclusions_and_abstention_policy_frozen': True, 'responsible_reviewer': 'test fixture', 'provenance_note': 'test fixture only'}
            cfg['model_configuration'] = {'target_provider': 'ollama', 'target_model': 'qwen3:1.7b', 'evaluator_provider': 'ollama', 'evaluator_model': 'qwen3:1.7b', 'pipeline_provider': 'ollama', 'pipeline_model': 'qwen3:1.7b', 'pipeline_version': 'test', 'evaluator_implementation_version': 'fixture-evaluator', 'pipeline_implementation_version': 'fixture-pipeline', 'target_strategy': 'test'}
            cfg['budget']['max_new_estimated_usd'] = 0
            cfg.update({'minimum_decided_coverage': 0.8, 'minimum_human_failure_count': 8, 'minimum_human_pass_count': 8, 'minimum_independent_histories': 8, 'abstention_policy': 'fixture', 'exclusion_policy': 'fixture', 'budget_enforcement_plan': 'fixture', 'reference_blinding_plan': 'fixture'})
            config = tmp / 'config.json'; config.write_text(json.dumps(cfg)); out = tmp / 'frozen.json'
            invalid = dict(cfg)
            invalid['budget'] = {**cfg['budget'], 'existing_estimated_usd': float('nan')}
            invalid_config = tmp / 'invalid-budget.json'; invalid_config.write_text(json.dumps(invalid))
            invalid_output = tmp / 'invalid-frozen.json'
            invalid_proc = subprocess.run([sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'), '--review-1', str(returns[0]), '--review-2', str(returns[1]), '--config', str(invalid_config), '--output', str(invalid_output)], capture_output=True, text=True)
            self.assertNotEqual(invalid_proc.returncode, 0)
            self.assertFalse(invalid_output.exists())
            cmd = [sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'), '--review-1', str(returns[0]), '--review-2', str(returns[1]), '--config', str(config), '--output', str(out)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(out.read_text())
            self.assertFalse(result['execution_supported'])
            self.assertFalse(result['model_called'])
            self.assertFalse(result['results_observed'])
            self.assertEqual(len(result['suite']['cases']), 8)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            digest = adapter.sha(out.read_bytes())
            staged = adapter.compile_mock(out, digest, '0')
            self.assertEqual(staged['question_count'], 32)
            self.assertEqual(staged['eligible_question_count'], 32)
            self.assertFalse(staged['model_called'])
            self.assertFalse(staged['database_written'])
            snapshot = {'histories': []}
            for index, case in enumerate(result['suite']['cases']):
                conversation_id = f'test-conversation-{index}'
                snapshot['histories'].append({'history_id': case['history_id'], 'conversation_id': conversation_id, 'memories': [{'memory_id': f'test-memory-{index}-{i}', 'conversation_id': conversation_id, 'status': 'confirmed', 'source_message_ids': [message['message_id']], 'canonical_value': message['text']} for i, message in enumerate(case['source_messages'])]})
            mapped = adapter.compile_mock(out, digest, '0', snapshot)
            self.assertTrue(mapped['memory_snapshot_checked_offline'])
            self.assertFalse(mapped['memory_records_verified_in_app'])
            self.assertTrue(all(item['supporting_memory_ids'] for item in mapped['items']))
            snapshot['histories'][0]['memories'][0]['status'] = 'candidate'
            with self.assertRaisesRegex(ValueError, 'status and source'):
                adapter.compile_mock(out, digest, '0', snapshot)
            snapshot['histories'][0]['memories'][0]['status'] = 'confirmed'
            snapshot['histories'][0]['memories'][0]['canonical_value'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'verbatim'):
                adapter.compile_mock(out, digest, '0', snapshot)
            with self.assertRaisesRegex(ValueError, 'local-only'):
                adapter.compile_mock(out, digest, '0.00001')
            with self.assertRaisesRegex(ValueError, 'separately recorded'):
                adapter.compile_mock(out, '0' * 64, '0')
            hosted = json.loads(config.read_text())
            hosted['model_configuration'].update({'target_provider': 'openrouter', 'target_model': 'openai/gpt-6-luna', 'evaluator_provider': 'openrouter', 'evaluator_model': 'openai/gpt-6-luna'})
            hosted['budget']['max_new_estimated_usd'] = 0.02
            hosted_config = tmp / 'hosted-config.json'; hosted_config.write_text(json.dumps(hosted)); hosted_out = tmp / 'hosted-frozen.json'
            hosted_cmd = [sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'), '--review-1', str(returns[0]), '--review-2', str(returns[1]), '--config', str(hosted_config), '--output', str(hosted_out)]
            hosted_proc = subprocess.run(hosted_cmd, capture_output=True, text=True)
            self.assertEqual(hosted_proc.returncode, 0, hosted_proc.stderr)
            hosted_sha = adapter.sha(hosted_out.read_bytes())
            with self.assertRaisesRegex(ValueError, 'exceed the frozen'):
                adapter.compile_mock(hosted_out, hosted_sha, '0.0004')
            hosted_stage = adapter.compile_mock(hosted_out, hosted_sha, '0.0003')
            self.assertEqual(hosted_stage['simulated_target_and_grader_reservation_usd'], '0.0192')
            self.assertFalse(hosted_stage['model_called'])
            expanded = json.loads(hosted_config.read_text())
            expanded['budget']['cumulative_cap_usd'] = 0.45
            expanded['budget']['max_new_estimated_usd'] = 0.06
            expanded_config = tmp / 'expanded-config.json'; expanded_config.write_text(json.dumps(expanded))
            expanded_out = tmp / 'expanded-frozen.json'
            expanded_cmd = [sys.executable, str(freeze.ROOT / 'scripts/freeze_ac3_prospective_suite.py'), '--review-1', str(returns[0]), '--review-2', str(returns[1]), '--config', str(expanded_config), '--output', str(expanded_out)]
            expanded_proc = subprocess.run(expanded_cmd, capture_output=True, text=True)
            self.assertEqual(expanded_proc.returncode, 0, expanded_proc.stderr)
            expanded_stage = adapter.compile_mock(expanded_out, adapter.sha(expanded_out.read_bytes()), '0.0004')
            self.assertFalse(expanded_stage['model_called'])
            tampered = json.loads(returns[0].read_text())
            tampered['cases'][0]['questions'][0]['review']['question_validity'] = 'invalid'
            returns[0].write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, 'source file changed'):
                adapter.compile_mock(out, digest, '0')


if __name__ == '__main__':
    unittest.main()
