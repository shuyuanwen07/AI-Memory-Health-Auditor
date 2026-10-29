import os
"""Synthetic re-review fixtures; no new human review or paid call is created."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_ac3_h19_restoration import build, encode
from scripts.import_ac3_h19_restoration_reviews import convert
from scripts.ac3_fixed_suite_adapter import compile_mock,sha

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'output/proposal-delivery'
V6=D/'ac3-expanded-30-candidate-draft-2026-10-28-v6'
V6_REVIEW=D/'ac3-expanded-v6-composite-user-confirmed-2026-10-28'
V7=D/'ac3-expanded-30-candidate-draft-2026-10-28-v7'


class H19RestorationTests(unittest.TestCase):
    def setUp(self):
        self.v6=(V6/'candidate-inputs.json').read_bytes();self.plan=(V6/'proposed-fact-plan.json').read_bytes()
        self.v7=(V7/'candidate-inputs.json').read_bytes();self.manifest=(V7/'manifest.json').read_bytes()
        self.ground=[(V6_REVIEW/f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)]
        self.facts=[(V6_REVIEW/f'fact-reviewer-{i}.json').read_bytes() for i in (1,2)]
        self.packets=[json.loads((V7/f'reviewer-{i}.json').read_text()) for i in (1,2)]
        # Reset only in-memory synthetic fixtures if the user's working copies
        # were edited; never change the submitted review files.
        for packet in self.packets:
            packet['reviewer_declaration']={'reviewer_label':None,'completed_by_human':None,
                'completed_independently':None,'used_ai_assistance':None,'note':''}
            packet['review']={'question_validity':None,'comment':''}

    def approved_fixture(self):
        packets=copy.deepcopy(self.packets)
        for slot,p in enumerate(packets,1):
            p['reviewer_declaration'].update({'reviewer_label':f'synthetic-{slot}','completed_by_human':True,
                'completed_independently':True,'used_ai_assistance':False})
            p['review']['question_validity']='valid'
        return [json.dumps(p,ensure_ascii=False).encode() for p in packets]

    def test_draft_changes_only_one_question_and_does_not_claim_new_review(self):
        revised,*_=build();self.assertEqual(encode(revised),self.v7)
        before=json.loads(self.v6);after=json.loads(self.v7)
        differences=[]
        for a,b in zip(before['cases'],after['cases']):
            for q1,q2 in zip(a['tests'],b['tests']):
                if q1!=q2:differences.append((q1['test_id'],q1['question'],q2['question']))
        self.assertEqual(len(differences),1);self.assertEqual(differences[0][0],'AC3-H19-Q4')
        self.assertIn('arrangement to offer',differences[0][2]);self.assertIn('requirement',differences[0][1])
        self.assertEqual((V7/'proposed-fact-plan.json').read_bytes(),self.plan)
        self.assertTrue(all(p['review']['question_validity'] is None for p in self.packets))

    def test_blank_or_uncertain_reviewer_is_not_silently_promoted(self):
        with self.assertRaisesRegex(ValueError,'human, independent'):
            convert(self.v6,self.plan,V6_REVIEW/'manifest.json',self.ground,self.facts,self.v7,self.manifest,
                    [json.dumps(p).encode() for p in self.packets])
        packets=[json.loads(x) for x in self.approved_fixture()]
        packets[0]['review']['question_validity']='uncertain'
        with self.assertRaisesRegex(ValueError,'uncertain'):
            convert(self.v6,self.plan,V6_REVIEW/'manifest.json',self.ground,self.facts,self.v7,self.manifest,
                    [json.dumps(p).encode() for p in packets])

    def test_synthetic_single_question_reviews_preserve_other_119(self):
        grounds,facts=convert(self.v6,self.plan,V6_REVIEW/'manifest.json',self.ground,self.facts,
                              self.v7,self.manifest,self.approved_fixture())
        old=json.loads(self.ground[0]);differences=[]
        for before,after in zip(old['cases'],grounds[0]['cases']):
            for a,b in zip(before['questions'],after['questions']):
                if a!=b:differences.append(a['test_id'])
        self.assertEqual(differences,['AC3-H19-Q4']);self.assertEqual(facts[0],json.loads(self.facts[0]))
        self.assertIn('not authenticated',grounds[0]['reviewer_declaration']['note'])

    def test_synthetic_cli_through_readiness_freeze_and_repeat_child(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("CI_FIXTURE_OUTPUT_ROOT")) as directory:
            tmp=Path(directory);review_paths=[]
            for slot,data in enumerate(self.approved_fixture(),1):
                path=tmp/f'review-{slot}.json';path.write_bytes(data);review_paths.append(path)
            out=tmp/'composite'; command=[sys.executable,str(ROOT/'scripts/import_ac3_h19_restoration_reviews.py'),
                '--v6-source',str(V6/'candidate-inputs.json'),'--v6-plan',str(V6/'proposed-fact-plan.json'),
                '--v6-manifest',str(V6_REVIEW/'manifest.json'),
                '--v6-ground-1',str(V6_REVIEW/'grounding-reviewer-1.json'),'--v6-ground-2',str(V6_REVIEW/'grounding-reviewer-2.json'),
                '--v6-fact-1',str(V6_REVIEW/'fact-reviewer-1.json'),'--v6-fact-2',str(V6_REVIEW/'fact-reviewer-2.json'),
                '--v7-source',str(V7/'candidate-inputs.json'),'--restoration-manifest',str(V7/'manifest.json'),
                '--question-review-1',str(review_paths[0]),'--question-review-2',str(review_paths[1]),'--output-dir',str(out)]
            proc=subprocess.run(command,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
            readiness=[sys.executable,str(ROOT/'scripts/check_ac3_prospective_readiness.py'),
                '--source',str(V7/'candidate-inputs.json'),'--review-1',str(out/'grounding-reviewer-1.json'),
                '--review-2',str(out/'grounding-reviewer-2.json'),'--expanded-manifest',str(out/'manifest.json')]
            proc=subprocess.run(readiness,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['both_valid'],120)
            cfg=json.loads((D/'ac3-protocol-review-draft-revised-2026-10-28/protocol-config-expanded-draft.json').read_text())
            cfg['human_attestations']={'pilot_provenance_reviewed':True,'pilot_thresholds_accepted':True,
                'held_out_outputs_not_generated_or_inspected':True,'exclusions_and_abstention_policy_frozen':True,
                'responsible_reviewer':'synthetic fixture','provenance_note':'synthetic fixture only'}
            cfg['model_configuration']['runtime_source_sha256']='a'*64;cfg['model_configuration']['ledger_schema_sha256']='b'*64
            config=tmp/'config.json';config.write_text(json.dumps(cfg))
            approval={'format':'ac3-user-selected-thresholds-v1','recorded_at_utc':'2026-01-01T00:00:00+00:00',
                'user_response':'synthetic fixture only','selection_basis':'fixture selection',
                'provenance_limitations':'fixture limitations','pilot_draft_sha256':cfg['pilot_draft_sha256'],
                'thresholds':cfg['thresholds'],'held_out_results_seen':False}
            ap=tmp/'approval.json';ap.write_text(json.dumps(approval));frozen=tmp/'frozen.json'
            command=[sys.executable,str(ROOT/'scripts/freeze_ac3_prospective_suite.py'),
                '--source',str(V7/'candidate-inputs.json'),'--review-1',str(out/'grounding-reviewer-1.json'),
                '--review-2',str(out/'grounding-reviewer-2.json'),'--fact-plan',str(V7/'proposed-fact-plan.json'),
                '--fact-review-1',str(out/'fact-reviewer-1.json'),'--fact-review-2',str(out/'fact-reviewer-2.json'),
                '--expanded-manifest',str(out/'manifest.json'),'--threshold-approval',str(ap),'--config',str(config),'--output',str(frozen)]
            proc=subprocess.run(command,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(compile_mock(frozen,sha(frozen.read_bytes()),'0.008')['question_count'],120)
            child=tmp/'child.json';proc=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_ac3_stability_child.py'),
                '--primary-frozen',str(frozen),'--primary-sha256',sha(frozen.read_bytes()),'--output',str(child)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(compile_mock(child,sha(child.read_bytes()),'0.008')['question_count'],40)
            review_paths[0].write_text('{}')
            with self.assertRaisesRegex(ValueError,'source file changed'):
                compile_mock(frozen,sha(frozen.read_bytes()),'0.008')


if __name__=='__main__':unittest.main()
