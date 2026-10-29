"""Exercise paired generation on synthetic fixtures, never on unreviewed study inputs."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.formal_freeze import formal_runtime_signature
from scripts.ac2_paired_retest_freeze import prepare
from scripts.ac2_paired_retest_run import run
from scripts.ac2_paired_retest_adapter import adapt, review_source

ROOT = Path(__file__).resolve().parents[2]

class PairedRunTests(unittest.TestCase):
    def setUp(self):
        self.source = json.dumps({'cases': [{'history_id': 'synthetic-1', 'source_messages': [
            {'message_id': 'm1', 'text': 'The meeting is on Tuesday.'}]}]}).encode()
        self.plan = json.dumps({'histories': {'synthetic-1': {'facts': [
            {'memory_id': 'f1', 'canonical_value': 'The meeting is on Tuesday.',
             'source_message_id': 'm1'}], 'relationships': []}}}).encode()
        self.reviews = [b'synthetic-review-1', b'synthetic-review-2']
        self.archive = (ROOT/'output/proposal-delivery/ac3-retest-diverse-candidate-2026-10-28-v6/legacy-app-source-unlocked.zip').read_bytes()
        self.candidate = (ROOT/'backend/app/test_generator/rule_based.py').read_bytes()
        self.validator = (ROOT/'backend/app/test_generator/quality.py').read_bytes()

    def freeze(self):
        return prepare(self.source, self.plan, self.reviews, self.archive, self.candidate,
                       self.validator, formal_runtime_signature()['source_sha256'])

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_loaded_sources_are_verified_outside_container_and_tampering_rejected(self, _inspect):
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / 'generator.py'
            validator_path = Path(directory) / 'quality.py'
            candidate_path.write_bytes(self.candidate)
            validator_path.write_bytes(self.validator)
            frozen = self.freeze()
            with patch('scripts.ac2_paired_retest_run.inspect.getfile', side_effect=[str(candidate_path), str(validator_path)]):
                result = run(frozen, self.source, self.plan, self.reviews, self.archive, self.candidate, self.validator)
            self.assertFalse(result['model_called'])
            candidate_path.write_bytes(self.candidate + b'\n# altered\n')
            with patch('scripts.ac2_paired_retest_run.inspect.getfile', return_value=str(candidate_path)):
                with self.assertRaisesRegex(ValueError, 'Candidate is not the running product generator'):
                    run(frozen, self.source, self.plan, self.reviews, self.archive, self.candidate, self.validator)

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_both_versions_preserve_same_synthetic_history(self, _inspect):
        result = run(self.freeze(), self.source, self.plan, self.reviews, self.archive,
                     self.candidate, self.validator)
        for name in ('baseline', 'candidate'):
            row = result['conditions'][name][0]
            self.assertEqual(row['history_id'], 'synthetic-1')
            self.assertEqual(row['status'], 'completed')
            self.assertGreater(row['generated_count'], 0)
            self.assertEqual(row['generated_count'], len(row['tests']))
            self.assertEqual(row['missing_slots'], max(0, 4-len(row['tests'])))
            self.assertIn('quality_status', row['tests'][0]['quality_assessment'])
        self.assertFalse(result['model_called'])

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_generation_exception_is_retained(self, _inspect):
        frozen = self.freeze()
        with patch('scripts.ac2_paired_retest_run.RuleBasedTestGenerator.generate', side_effect=RuntimeError('synthetic')):
            result = run(frozen, self.source, self.plan, self.reviews, self.archive,
                         self.candidate, self.validator)
        row = result['conditions']['candidate'][0]
        self.assertEqual((row['status'], row['error_type'], row['missing_slots']), ('error', 'RuntimeError', 4))
        self.assertEqual(result['conditions']['baseline'][0]['status'], 'completed')

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_validator_exception_does_not_erase_generated_question(self, _inspect):
        frozen = self.freeze()
        with patch('scripts.ac2_paired_retest_run.RuleBasedTestQualityValidator.validate', side_effect=RuntimeError('synthetic')):
            result = run(frozen, self.source, self.plan, self.reviews, self.archive,
                         self.candidate, self.validator)
        runs, ledger = adapt(self.source, frozen, result)
        for side in ('baseline', 'candidate'):
            row = result['conditions'][side][0]
            self.assertEqual(row['generated_count'], 1)
            self.assertEqual(row['tests'][0]['quality_assessment']['validation_error_type'], 'RuntimeError')
            self.assertEqual(runs[side]['synthetic-1'][0]['gate_status'], 'uncertain')
            self.assertEqual(ledger[side]['synthetic-1']['missing_slots'], 3)

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_suite_exception_is_preserved_separately(self, _inspect):
        frozen = self.freeze()
        with patch('scripts.ac2_paired_retest_run.RuleBasedTestQualityValidator.validate_suite', side_effect=RuntimeError('synthetic')):
            result = run(frozen, self.source, self.plan, self.reviews, self.archive,
                         self.candidate, self.validator)
        _, ledger = adapt(self.source, frozen, result)
        self.assertEqual(ledger['candidate']['synthetic-1']['suite_validation_error_type'], 'RuntimeError')
        self.assertEqual(result['conditions']['candidate'][0]['generated_count'], 1)

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_changed_review_is_rejected(self, _inspect):
        frozen = self.freeze()
        with self.assertRaises(ValueError):
            run(frozen, self.source, self.plan, [b'changed', self.reviews[1]], self.archive,
                self.candidate, self.validator)

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_real_output_adapter_retains_questions_and_gate(self, _inspect):
        frozen = self.freeze()
        output = run(frozen, self.source, self.plan, self.reviews, self.archive,
                     self.candidate, self.validator)
        runs, ledger = adapt(self.source, frozen, output)
        for side in ('baseline', 'candidate'):
            raw = output['conditions'][side][0]
            self.assertEqual(runs[side]['synthetic-1'][0]['prompt'], raw['tests'][0]['test']['prompt'])
            self.assertEqual(runs[side]['synthetic-1'][0]['gate_status'], raw['tests'][0]['quality_assessment']['quality_status'])
            self.assertEqual(ledger[side]['synthetic-1']['missing_slots'], 3)
        altered = copy.deepcopy(output)
        altered['conditions']['baseline'][0]['generated_count'] = 0
        with self.assertRaises(ValueError):
            adapt(self.source, frozen, altered)
        changed_freeze = copy.deepcopy(frozen)
        changed_freeze['review_policy'] = 'changed after generation'
        with self.assertRaises(ValueError):
            adapt(self.source, changed_freeze, output)

    @patch('scripts.ac2_paired_retest_freeze.inspect', return_value={'all_items_valid_in_both_reviews': True})
    def test_synthetic_end_to_end_blind_review(self, _inspect):
        frozen = self.freeze()
        output = run(frozen, self.source, self.plan, self.reviews, self.archive,
                     self.candidate, self.validator)
        runs, _ledger = adapt(self.source, frozen, output)
        source = review_source(self.source, self.plan, frozen)
        module_path = ROOT/'output/proposal-delivery/ac2-prospective-retest-draft-2026-10-28/blind_pairing.py'
        spec = importlib.util.spec_from_file_location('synthetic_blind_pairing', module_path)
        blind = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(blind)
        packet, reviews, private = blind.make_packets(source, runs)
        self.assertEqual(len(packet['cases']), 2)
        for item in packet['cases']:
            self.assertEqual(item['reviewed_reference']['facts'][0]['memory_id'], 'f1')
            self.assertNotIn('gate_status', item)
            self.assertNotIn('condition', item)
        for index, review in enumerate(reviews):
            review['reviewer_declaration'].update(reviewer_label=f'synthetic-{index}',
                completed_by_human=True, completed_independently=True,
                has_seen_automatic_results=False, has_seen_other_review=False, used_ai_assistance=False)
            for decision in review['decisions']:
                decision.update(grounded='valid', structurally_executable='valid')
        result = blind.compare(source, packet, reviews, private, runs)
        self.assertEqual(result['mean_paired_delta_pp'], 0)
        self.assertEqual(result['per_history']['synthetic-1']['candidate']['missing_slots'], 3)
        with self.assertRaises(ValueError):
            review_source(self.source, b'{}', frozen)
        altered = copy.deepcopy(output)
        altered['baseline_sha256'] = 'changed'
        with self.assertRaises(ValueError):
            adapt(self.source, frozen, altered)


if __name__ == '__main__':
    unittest.main()
