import os
"""The fabricated delta decisions below are fixtures, never human evidence."""
import copy
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.import_ac3_conflict_delta_reviews import convert
from scripts.import_ac3_fact_reviews import convert as convert_fact
from scripts.ac3_fixed_suite_adapter import compile_mock

ROOT = Path(__file__).resolve().parents[2] / 'output/proposal-delivery'


class ConflictDeltaReviewTests(unittest.TestCase):
    revision_folder = 'ac3-conflict-revision-draft-2026-10-28-v2'

    def setUp(self):
        old = ROOT / 'ac3-prospective-inputs-2026-10-28-v3'
        new = ROOT / self.revision_folder
        plan = ROOT / 'ac3-fact-review-draft-2026-10-28-v2'
        ground = ROOT / 'ac3-grounding-human-confirmed-2026-10-28'
        fact = ROOT / 'ac3-fact-review-return-intake-2026-10-28'
        intake = json.loads((fact / 'intake.json').read_text())
        self.templates = [(new / f'changed-items-reviewer-{i}.json').read_bytes() for i in (1, 2)]
        packets = [json.loads(raw) for raw in self.templates]
        for i, packet in enumerate(packets, 1):
            packet['reviewer_declaration'].update(reviewer_label=f'synthetic-{i}', completed_by_human=True,
                                                   completed_independently=True, used_ai_assistance=False)
            for item in packet['cases']:
                item['review'].update(question_validity='valid', fact_and_relation='accept')
        self.packets = packets
        self.args = [(old / 'candidate-inputs.json').read_bytes(), (new / 'candidate-inputs.json').read_bytes(),
            (plan / 'proposed-fact-plan.json').read_bytes(), (new / 'proposed-fact-plan.json').read_bytes(),
            [(ground / f'grounding-reviewer-{i}-human-confirmed.json').read_bytes() for i in (1, 2)],
            [(fact / row['archived_as']).read_bytes() for row in intake['records']],
            (ground / 'confirmation-record.json').read_bytes(), (fact / 'user-followup.json').read_bytes(),
            self.encode(packets), self.templates]

    @staticmethod
    def encode(packets):
        return [json.dumps(x, ensure_ascii=False).encode() for x in packets]

    def test_approved_changed_items_produce_composite_not_new_full_review(self):
        ground, fact = convert(*self.args)
        self.assertEqual(len(ground), 2)
        for packet in ground:
            self.assertEqual(sum(q['review']['question_validity'] == 'valid' for c in packet['cases'] for q in c['questions']), 32)
            self.assertIn('not asserted to be the same person', packet['reviewer_declaration']['note'])
        self.assertEqual(len(fact), 2)

    def test_uncertain_or_revise_cannot_become_approval(self):
        for field, value in (('question_validity','uncertain'), ('fact_and_relation','revise')):
            packets = copy.deepcopy(self.packets); packets[0]['cases'][0]['review'][field] = value
            args = self.args.copy(); args[8] = self.encode(packets)
            with self.assertRaises(ValueError): convert(*args)

    def test_tampered_source_or_jointly_tampered_template_is_rejected(self):
        packets = copy.deepcopy(self.packets); templates = [json.loads(x) for x in self.templates]
        packets[0]['cases'][0]['revised_M4'] = templates[0]['cases'][0]['revised_M4'] = 'different'
        args = self.args.copy(); args[8] = self.encode(packets); args[9] = self.encode(templates)
        with self.assertRaises(ValueError): convert(*args)
        args = self.args.copy()
        original = b'exactly one confirmed venue' if b'exactly one confirmed venue' in args[1] else b'only final confirmed venue'
        args[1] = args[1].replace(original, b'two confirmed venues', 1)
        with self.assertRaises(ValueError): convert(*args)

    def test_identity_missing_or_duplicate_and_missing_original_confirmation_rejected(self):
        packets = copy.deepcopy(self.packets); packets[1]['reviewer_declaration']['reviewer_label'] = 'synthetic-1'
        args = self.args.copy(); args[8] = self.encode(packets)
        with self.assertRaises(ValueError): convert(*args)
        confirmation = json.loads(self.args[7]); confirmation['user_independence_statement'] = ''
        args = self.args.copy(); args[7] = json.dumps(confirmation).encode()
        with self.assertRaises(ValueError): convert(*args)

    def test_revised_composite_readiness_freeze_and_tampering(self):
        """Synthetic test attestation is confined to a temporary directory."""
        with tempfile.TemporaryDirectory(dir=os.environ.get("CI_FIXTURE_OUTPUT_ROOT")) as directory:
            tmp = Path(directory)
            paths = []
            flat = self.args[:4] + self.args[4] + self.args[5] + self.args[6:8] + self.args[8] + self.args[9]
            for index, raw in enumerate(flat):
                path = tmp / f'input-{index}.json'; path.write_bytes(raw); paths.append(path)
            composite = tmp / 'composite'; composite.mkdir()
            grounds, facts = convert(*self.args)
            for i in (1, 2):
                (composite / f'grounding-reviewer-{i}.json').write_text(json.dumps(grounds[i-1], ensure_ascii=False))
                (composite / f'fact-reviewer-{i}.json').write_text(json.dumps(facts[i-1], ensure_ascii=False))
            manifest = {'format':'ac3-conflict-composite-review-v1', 'inputs':[
                {'path':str(path), 'sha256':hashlib.sha256(raw).hexdigest()} for path,raw in zip(paths,flat)]}
            (composite / 'manifest.json').write_text(json.dumps(manifest))
            fact_raw = [(composite / f'fact-reviewer-{i}.json').read_bytes() for i in (1, 2)]
            declarations = convert_fact(flat[1], flat[3], fact_raw)
            for i in (1, 2): (tmp / f'fact-declaration-{i}.json').write_text(json.dumps(declarations[i-1]))
            script_root = ROOT.parent.parent / 'scripts'
            readiness = [sys.executable, str(script_root/'check_ac3_prospective_readiness.py'),
                '--source',str(paths[1]), '--review-1',str(composite/'grounding-reviewer-1.json'),
                '--review-2',str(composite/'grounding-reviewer-2.json'), '--composite-manifest',str(composite/'manifest.json')]
            result = subprocess.run(readiness, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['both_valid'], 32)
            without_manifest = subprocess.run(readiness[:-2], capture_output=True, text=True)
            self.assertNotEqual(without_manifest.returncode, 0)
            cfg = json.loads((ROOT/'ac3-prospective-inputs-2026-10-28-v3/protocol-config-template.json').read_text())
            cfg['human_attestations'] = {'pilot_provenance_reviewed':True,'pilot_thresholds_accepted':True,
                'held_out_outputs_not_generated_or_inspected':True,'exclusions_and_abstention_policy_frozen':True,
                'responsible_reviewer':'synthetic only','provenance_note':'synthetic only'}
            cfg['model_configuration'] = {'target_provider':'ollama','target_model':'fixture','evaluator_provider':'ollama',
                'evaluator_model':'fixture','pipeline_provider':'ollama','pipeline_model':'fixture','pipeline_version':'fixture','evaluator_implementation_version':'fixture-evaluator','pipeline_implementation_version':'fixture-pipeline','target_strategy':'fixture'}
            cfg['budget']['max_new_estimated_usd'] = 0
            cfg.update({'minimum_decided_coverage':.8,'minimum_human_failure_count':8,'minimum_human_pass_count':8,
                'minimum_independent_histories':8,'abstention_policy':'fixture','exclusion_policy':'fixture',
                'budget_enforcement_plan':'fixture','reference_blinding_plan':'fixture'})
            config = tmp/'config.json'; config.write_text(json.dumps(cfg))
            frozen = tmp/'frozen.json'
            command=[sys.executable,str(script_root/'freeze_ac3_prospective_suite.py'),
                '--source',str(paths[1]),'--review-1',str(composite/'grounding-reviewer-1.json'),
                '--review-2',str(composite/'grounding-reviewer-2.json'), '--fact-plan',str(paths[3]),
                '--fact-review-1',str(tmp/'fact-declaration-1.json'),'--fact-review-2',str(tmp/'fact-declaration-2.json'),
                '--composite-manifest',str(composite/'manifest.json'),'--config',str(config),'--output',str(frozen)]
            done=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(done.returncode,0,done.stderr)
            staged=compile_mock(frozen,hashlib.sha256(frozen.read_bytes()).hexdigest(),'0')
            self.assertEqual(staged['eligible_question_count'],32)
            paths[10].write_text('{}')
            with self.assertRaises(ValueError): compile_mock(frozen,hashlib.sha256(frozen.read_bytes()).hexdigest(),'0')
class ExplicitConflictDeltaReviewTests(ConflictDeltaReviewTests):
    revision_folder = 'ac3-conflict-revision-draft-2026-10-28-v3'

    def test_both_active_records_claim_different_unique_final_venues(self):
        old = json.loads(self.args[0]); revised = json.loads(self.args[1]); plan = json.loads(self.args[3])
        for original, case in zip(old['cases'], revised['cases']):
            self.assertEqual(original['tests'], case['tests'])
            self.assertEqual(original['source_messages'][:3] + original['source_messages'][4:],
                             case['source_messages'][:3] + case['source_messages'][4:])
            message = case['source_messages'][3]['text']
            self.assertIn('an active site plan states that', message)
            self.assertIn('A separate still-active signed booking states that', message)
            self.assertEqual(message.count('is the only final confirmed venue'), 2)
            self.assertIn('Neither record has priority', message)
            facts = plan['histories'][case['history_id']]['facts']
            for fact in (facts[3], facts[4]):
                self.assertIn(fact['source_span'], message)
                self.assertIn('is the only final confirmed venue', fact['canonical_value'])


if __name__ == '__main__': unittest.main()
