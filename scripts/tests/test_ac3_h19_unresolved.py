import os
"""Synthetic two-review fixtures only; original human judgments are not edited."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.prepare_ac3_h19_unresolved import build,encode
from scripts.import_ac3_h19_unresolved_reviews import convert
from scripts.ac3_fixed_suite_adapter import compile_mock,sha

ROOT=Path(__file__).resolve().parents[2]; D=ROOT/'output/proposal-delivery'
V7=D/'ac3-expanded-30-candidate-draft-2026-10-28-v7'
PRIOR=D/'ac3-expanded-v7-composite-user-confirmed-2026-10-28'
V8=D/'ac3-expanded-30-candidate-draft-2026-10-28-v8'


class H19UnresolvedTests(unittest.TestCase):
    def setUp(self):
        self.src=(V7/'candidate-inputs.json').read_bytes();self.oldplan=(V7/'proposed-fact-plan.json').read_bytes()
        self.ground=[(PRIOR/f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)]
        self.facts=[(PRIOR/f'fact-reviewer-{i}.json').read_bytes() for i in (1,2)]
        self.newsrc=(V8/'candidate-inputs.json').read_bytes();self.newplan=(V8/'proposed-fact-plan.json').read_bytes()
        self.manifest=(V8/'manifest.json').read_bytes()
        self.packets=[json.loads((V8/f'reviewer-{i}.json').read_text()) for i in (1,2)]
        for packet in self.packets:
            packet['reviewer_declaration']={'reviewer_label':None,'completed_by_human':None,
                'completed_independently':None,'used_ai_assistance':None,'note':''}
            packet['review']={'fact_validity':None,'edge_handling':None,'comment':''}

    def approved_fixture(self):
        packets=copy.deepcopy(self.packets)
        for slot,p in enumerate(packets,1):
            p['reviewer_declaration'].update({'reviewer_label':f'synthetic-{slot}','completed_by_human':True,
                'completed_independently':True,'used_ai_assistance':False})
            p['review'].update({'fact_validity':'valid','edge_handling':'accept'})
        return [json.dumps(p,ensure_ascii=False).encode() for p in packets]

    def test_projection_preserves_question_and_records_edge_as_unresolved(self):
        source,plan,*_=build();self.assertEqual(self.newsrc,self.src);self.assertEqual(encode(plan),self.newplan)
        old=json.loads(self.oldplan);new=json.loads(self.newplan);a=old['histories']['AC3-H19'];b=new['histories']['AC3-H19']
        oldfact=next(x for x in a['facts'] if x['memory_id']=='AC3-H19-F8');newfact=next(x for x in b['facts'] if x['memory_id']=='AC3-H19-F8')
        self.assertEqual(newfact['canonical_value'],newfact['source_span'])
        self.assertNotEqual(oldfact['canonical_value'],newfact['canonical_value'])
        self.assertEqual(len(a['relationships'])-len(b['relationships']),1)
        manifest=json.loads(self.manifest);self.assertEqual(manifest['unresolved_edge_status'],'unresolved_not_written_as_confirmed')
        self.assertTrue(all(p['review']['fact_validity'] is None for p in self.packets))

    def test_no_blank_or_uncertain_review_can_be_merged(self):
        with self.assertRaisesRegex(ValueError,'human, independent'):
            convert(self.src,self.oldplan,PRIOR/'manifest.json',self.ground,self.facts,self.newsrc,self.newplan,self.manifest,
                    [json.dumps(p).encode() for p in self.packets])
        packets=[json.loads(x) for x in self.approved_fixture()];packets[0]['review']['edge_handling']='uncertain'
        with self.assertRaisesRegex(ValueError,'not accepted'):
            convert(self.src,self.oldplan,PRIOR/'manifest.json',self.ground,self.facts,self.newsrc,self.newplan,self.manifest,
                    [json.dumps(p).encode() for p in packets])

    def test_synthetic_reviews_preserve_all_question_labels_and_no_new_gold_edge(self):
        grounds,facts=convert(self.src,self.oldplan,PRIOR/'manifest.json',self.ground,self.facts,
                              self.newsrc,self.newplan,self.manifest,self.approved_fixture())
        self.assertEqual(grounds,[json.loads(x) for x in self.ground])
        self.assertTrue(all('unresolved, not invalid' in x['note'] for x in facts))
        self.assertNotEqual(facts[0]['fact_plan_sha256'],json.loads(self.facts[0])['fact_plan_sha256'])

    def test_synthetic_120_primary_and_40_repeat_chain(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("CI_FIXTURE_OUTPUT_ROOT")) as directory:
            tmp=Path(directory);review_paths=[]
            for slot,data in enumerate(self.approved_fixture(),1):
                path=tmp/f'review-{slot}.json';path.write_bytes(data);review_paths.append(path)
            out=tmp/'composite'
            command=[sys.executable,str(ROOT/'scripts/import_ac3_h19_unresolved_reviews.py'),
                '--v7-source',str(V7/'candidate-inputs.json'),'--v7-plan',str(V7/'proposed-fact-plan.json'),
                '--v7-manifest',str(PRIOR/'manifest.json'),'--v7-ground-1',str(PRIOR/'grounding-reviewer-1.json'),
                '--v7-ground-2',str(PRIOR/'grounding-reviewer-2.json'),'--v7-fact-1',str(PRIOR/'fact-reviewer-1.json'),
                '--v7-fact-2',str(PRIOR/'fact-reviewer-2.json'),'--v8-source',str(V8/'candidate-inputs.json'),
                '--v8-plan',str(V8/'proposed-fact-plan.json'),'--v8-manifest',str(V8/'manifest.json'),
                '--review-1',str(review_paths[0]),'--review-2',str(review_paths[1]),'--output-dir',str(out)]
            proc=subprocess.run(command,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
            cmd=[sys.executable,str(ROOT/'scripts/check_ac3_prospective_readiness.py'),
                 '--source',str(V8/'candidate-inputs.json'),'--review-1',str(out/'grounding-reviewer-1.json'),
                 '--review-2',str(out/'grounding-reviewer-2.json'),'--expanded-manifest',str(out/'manifest.json')]
            proc=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['both_valid'],120)
            cfg=json.loads((D/'ac3-protocol-review-draft-revised-2026-10-28/protocol-config-expanded-draft.json').read_text())
            cfg['human_attestations']={'pilot_provenance_reviewed':True,'pilot_thresholds_accepted':True,
                'held_out_outputs_not_generated_or_inspected':True,'exclusions_and_abstention_policy_frozen':True,
                'responsible_reviewer':'synthetic fixture','provenance_note':'synthetic fixture only'}
            cfg['model_configuration']['runtime_source_sha256']='a'*64;cfg['model_configuration']['ledger_schema_sha256']='b'*64
            config=tmp/'config.json';config.write_text(json.dumps(cfg));approval={'format':'ac3-user-selected-thresholds-v1',
                'recorded_at_utc':'2026-01-01T00:00:00+00:00','user_response':'synthetic fixture only',
                'selection_basis':'fixture','provenance_limitations':'fixture','pilot_draft_sha256':cfg['pilot_draft_sha256'],
                'thresholds':cfg['thresholds'],'held_out_results_seen':False}
            ap=tmp/'approval.json';ap.write_text(json.dumps(approval));frozen=tmp/'frozen.json'
            cmd=[sys.executable,str(ROOT/'scripts/freeze_ac3_prospective_suite.py'),'--source',str(V8/'candidate-inputs.json'),
                '--review-1',str(out/'grounding-reviewer-1.json'),'--review-2',str(out/'grounding-reviewer-2.json'),
                '--fact-plan',str(V8/'proposed-fact-plan.json'),'--fact-review-1',str(out/'fact-reviewer-1.json'),
                '--fact-review-2',str(out/'fact-reviewer-2.json'),'--expanded-manifest',str(out/'manifest.json'),
                '--threshold-approval',str(ap),'--config',str(config),'--output',str(frozen)]
            proc=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(compile_mock(frozen,sha(frozen.read_bytes()),'0.008')['question_count'],120)
            child=tmp/'child.json';proc=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_ac3_stability_child.py'),
                '--primary-frozen',str(frozen),'--primary-sha256',sha(frozen.read_bytes()),'--output',str(child)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr);self.assertEqual(compile_mock(child,sha(child.read_bytes()),'0.008')['question_count'],40)
            review_paths[0].write_text('{}')
            with self.assertRaisesRegex(ValueError,'source file changed'):
                compile_mock(child,sha(child.read_bytes()),'0.008')


if __name__=='__main__':unittest.main()
