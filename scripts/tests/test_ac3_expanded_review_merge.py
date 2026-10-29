"""Exercise 30-history merge with synthetic new-review declarations only."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.import_ac3_expanded_reviews import convert, merge_revision_reviews, sha
import hashlib
from scripts.ac3_fixed_suite_adapter import compile_mock, sha

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / 'output/proposal-delivery'
OLD = DELIVERY / 'ac3-conflict-revision-draft-2026-10-28-v3'
PRIOR = DELIVERY / 'ac3-v3-composite-human-review-2026-10-28'
FACT = DELIVERY / 'ac3-v3-composite-fact-declarations-2026-10-28'
NEW = DELIVERY / 'ac3-expanded-v5-original-reconstructed-2026-10-28'
REVIEWED_PARENT = DELIVERY / 'ac3-expanded-v5-confirmed-intake-2026-10-28'
REVISION = DELIVERY / 'ac3-expanded-30-candidate-draft-2026-10-28-v6'


class ExpandedReviewMergeTests(unittest.TestCase):
    def setUp(self):
        self.args = [(OLD/'candidate-inputs.json').read_bytes(), (OLD/'proposed-fact-plan.json').read_bytes(),
            PRIOR/'manifest.json', [(PRIOR/f'grounding-reviewer-{i}.json').read_bytes() for i in (1,2)],
            [(FACT/f'fact-review-{i}.json').read_bytes() for i in (1,2)],
            (NEW/'candidate-inputs.json').read_bytes(), (NEW/'proposed-fact-plan.json').read_bytes()]
        self.packets = [json.loads((NEW/f'reviewer-{i}.json').read_text()) for i in (1,2)]

    def encoded(self, packets):
        return [json.dumps(packet, ensure_ascii=False).encode() for packet in packets]

    def accepted_fixture(self):
        packets = copy.deepcopy(self.packets)
        for slot, review in enumerate(packets,1):
            review['reviewer_declaration'].update({'reviewer_label':f'synthetic-{slot}',
                'completed_by_human':True,'completed_independently':True,'used_ai_assistance':False})
            for case in review['cases']:
                case['fact_review']['decision']='accept';case['additional_source_facts_missing']=[]
                for question in case['questions']: question['review']['question_validity']='valid'
                for edge in case['relationship_checks']: edge['review']['decision']='valid'
        return packets

    def test_blank_user_packets_cannot_be_converted(self):
        with self.assertRaisesRegex(ValueError,'human, independent'):
            convert(*self.args,self.encoded(self.packets))

    def test_synthetic_reviews_preserve_old_evidence_and_cover_120(self):
        grounds,facts=convert(*self.args,self.encoded(self.accepted_fixture()))
        self.assertEqual(len(grounds[0]['cases']),30)
        self.assertEqual(sum(len(c['questions']) for c in grounds[0]['cases']),120)
        old=json.loads(self.args[3][0])
        self.assertEqual(grounds[0]['cases'][:8],old['cases'])
        self.assertIn('not authenticated',facts[0]['note'])

    def test_missing_or_uncertain_is_not_upgraded_to_valid(self):
        packets=self.accepted_fixture()
        for mutation in ('question','fact','relationship','missing','identity','source'):
            candidate=copy.deepcopy(packets)
            c=candidate[0]['cases'][0]
            if mutation=='question': c['questions'][0]['review']['question_validity']='uncertain'
            if mutation=='fact': c['fact_review']['decision']='revise'
            if mutation=='relationship': c['relationship_checks'][0]['review']['decision']='invalid'
            if mutation=='missing': c['additional_source_facts_missing']=None
            if mutation=='identity': candidate[1]['reviewer_declaration']['reviewer_label']=' SYNTHETIC-1 '
            if mutation=='source': c['source_messages'][0]['text']='modified'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                convert(*self.args,self.encoded(candidate))

    def test_synthetic_review_round_trips_through_freeze_and_mock_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory);packets=self.accepted_fixture()
            reviews=[]
            for i,packet in enumerate(packets,1):
                path=tmp/f'new-review-{i}.json';path.write_text(json.dumps(packet,ensure_ascii=False));reviews.append(path)
            out=tmp/'combined'
            command=[sys.executable,str(ROOT/'scripts/import_ac3_expanded_reviews.py'),
                '--old-source',str(OLD/'candidate-inputs.json'),'--old-plan',str(OLD/'proposed-fact-plan.json'),
                '--old-manifest',str(PRIOR/'manifest.json'),
                '--old-ground-1',str(PRIOR/'grounding-reviewer-1.json'),'--old-ground-2',str(PRIOR/'grounding-reviewer-2.json'),
                '--old-fact-1',str(FACT/'fact-review-1.json'),'--old-fact-2',str(FACT/'fact-review-2.json'),
                '--expanded-source',str(NEW/'candidate-inputs.json'),'--expanded-plan',str(NEW/'proposed-fact-plan.json'),
                '--new-review-1',str(reviews[0]),'--new-review-2',str(reviews[1]),'--output-dir',str(out)]
            done=subprocess.run(command,capture_output=True,text=True);self.assertEqual(done.returncode,0,done.stderr)
            readiness=[sys.executable,str(ROOT/'scripts/check_ac3_prospective_readiness.py'),
                '--source',str(NEW/'candidate-inputs.json'),'--review-1',str(out/'grounding-reviewer-1.json'),
                '--review-2',str(out/'grounding-reviewer-2.json'),'--expanded-manifest',str(out/'manifest.json')]
            checked=subprocess.run(readiness,capture_output=True,text=True);self.assertEqual(checked.returncode,0,checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['both_valid'],120)
            self.assertEqual(json.loads(checked.stdout)['histories'],30)
            cfg=json.loads((DELIVERY/'ac3-prospective-inputs-2026-10-28-v3/protocol-config-template.json').read_text())
            cfg['human_attestations']={'pilot_provenance_reviewed':True,'pilot_thresholds_accepted':True,
                'held_out_outputs_not_generated_or_inspected':True,'exclusions_and_abstention_policy_frozen':True,
                'responsible_reviewer':'synthetic fixture','provenance_note':'synthetic fixture only'}
            cfg['model_configuration']={'target_provider':'ollama','target_model':'fixture','evaluator_provider':'ollama',
                'evaluator_model':'fixture','pipeline_provider':'ollama','pipeline_model':'fixture','pipeline_version':'fixture',
                'evaluator_implementation_version':'fixture','pipeline_implementation_version':'fixture','target_strategy':'fixture'}
            cfg['budget']['max_new_estimated_usd']=0
            cfg.update({'minimum_decided_coverage':.8,'minimum_human_failure_count':30,'minimum_human_pass_count':30,
                'minimum_independent_histories':30,'abstention_policy':'fixture','exclusion_policy':'fixture',
                'budget_enforcement_plan':'fixture','reference_blinding_plan':'fixture'})
            config=tmp/'config.json';config.write_text(json.dumps(cfg))
            approval={'format':'ac3-user-selected-thresholds-v1','recorded_at_utc':'2026-01-01T00:00:00+00:00',
                'user_response':'synthetic fixture only','selection_basis':'fixture selection',
                'provenance_limitations':'fixture limitations','pilot_draft_sha256':cfg['pilot_draft_sha256'],
                'thresholds':cfg['thresholds'],'held_out_results_seen':False}
            approval_path=tmp/'approval.json';approval_path.write_text(json.dumps(approval))
            frozen=tmp/'frozen.json'
            freeze=[sys.executable,str(ROOT/'scripts/freeze_ac3_prospective_suite.py'),'--source',str(NEW/'candidate-inputs.json'),
                '--review-1',str(out/'grounding-reviewer-1.json'),'--review-2',str(out/'grounding-reviewer-2.json'),
                '--fact-plan',str(NEW/'proposed-fact-plan.json'),'--fact-review-1',str(out/'fact-reviewer-1.json'),
                '--fact-review-2',str(out/'fact-reviewer-2.json'),'--expanded-manifest',str(out/'manifest.json'),
                '--threshold-approval',str(approval_path),'--config',str(config),'--output',str(frozen)]
            done=subprocess.run(freeze,capture_output=True,text=True);self.assertEqual(done.returncode,0,done.stderr)
            result=compile_mock(frozen,sha(frozen.read_bytes()),'0')
            self.assertEqual(result['history_count'],30);self.assertEqual(result['eligible_question_count'],120)
            self.assertFalse(result['model_called'])
            packets[0]['cases'][0]['fact_review']['decision']='uncertain'
            reviews[0].write_text(json.dumps(packets[0]))
            with self.assertRaisesRegex(ValueError,'source file changed'):
                compile_mock(frozen,sha(frozen.read_bytes()),'0')

    def test_revisions_reuse_only_unchanged_histories_and_require_both_rechecks(self):
        parent_source=self.args[5]; parent_plan=self.args[6]
        source=json.loads(parent_source);plan=json.loads(parent_plan)
        changed={source['cases'][9]['history_id'],source['cases'][18]['history_id']}
        for case in source['cases']:
            if case['history_id'] in changed:
                case['tests'][0]['question'] += ' (synthetic revision)'
        source_raw=json.dumps(source,ensure_ascii=False).encode()
        plan_raw=json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
        manifest={'format':'ac3-expanded-repair-manifest-v1','parent_source_sha256':sha(parent_source),
            'parent_fact_plan_sha256':sha(parent_plan),'revised_source_sha256':sha(source_raw),
            'revised_fact_plan_sha256':sha(plan_raw),'changed_history_ids':sorted(changed)}
        manifest_raw=json.dumps(manifest,ensure_ascii=False).encode()
        parents=self.accepted_fixture(); deltas=[]
        for slot,parent in enumerate(parents,1):
            delta=copy.deepcopy(parent)
            delta['expanded_source_sha256']=sha(source_raw)
            delta['fact_plan_sha256']=hashlib.sha256(plan_raw).hexdigest()
            delta['parent_source_sha256']=sha(parent_source)
            delta['revision_manifest_sha256']=sha(manifest_raw)
            delta['cases']=[c for c in delta['cases'] if c['history_id'] in changed]
            for reviewed in delta['cases']:
                current=next(c for c in source['cases'] if c['history_id']==reviewed['history_id'])
                for question,updated in zip(reviewed['questions'],current['tests']):
                    question['question']=updated['question']
            deltas.append(delta)
        combined=merge_revision_reviews(parent_source,parent_plan,source_raw,plan_raw,manifest_raw,
                                        self.encoded(parents),self.encoded(deltas))
        self.assertEqual(len(combined[0]['cases']),22)
        encoded=[json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() for row in combined]
        args=self.args[:5]+[source_raw,plan_raw]
        grounds,_=convert(*args,encoded)
        self.assertEqual(sum(len(c['questions']) for c in grounds[0]['cases']),120)
        missing=copy.deepcopy(deltas);missing[0]['cases'].pop()
        with self.assertRaisesRegex(ValueError,'omit'):
            merge_revision_reviews(parent_source,parent_plan,source_raw,plan_raw,manifest_raw,self.encoded(parents),self.encoded(missing))
        bad=copy.deepcopy(deltas);bad[0]['cases'][0]['questions'][0]['review']['question_validity']='uncertain'
        merged=merge_revision_reviews(parent_source,parent_plan,source_raw,plan_raw,manifest_raw,self.encoded(parents),self.encoded(bad))
        with self.assertRaisesRegex(ValueError,'uncertain'):
            convert(*args,[json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() for row in merged])
        false_manifest={**manifest,'changed_history_ids':sorted(changed)[:1]}
        with self.assertRaisesRegex(ValueError,'actual changed'):
            merge_revision_reviews(parent_source,parent_plan,source_raw,plan_raw,json.dumps(false_manifest).encode(),self.encoded(parents),self.encoded(deltas))

    def test_real_v6_layout_allows_skipping_changed_parent_cases(self):
        base_source,base_plan=self.args[5:7]
        parent_source=(REVIEWED_PARENT/'original-candidate-inputs.json').read_bytes()
        parent_plan=(REVIEWED_PARENT/'original-proposed-fact-plan.json').read_bytes()
        revised_source=(REVISION/'candidate-inputs.json').read_bytes()
        revised_plan=(REVISION/'proposed-fact-plan.json').read_bytes()
        manifest_raw=(REVISION/'manifest.json').read_bytes()
        changed=set(json.loads(manifest_raw)['changed_history_ids'])
        parents=[json.loads((REVIEWED_PARENT/f'reviewer-{i}-user-confirmed.json').read_text()) for i in (1,2)]
        deltas=[json.loads((REVISION/f'reviewer-{i}.json').read_text()) for i in (1,2)]
        for slot,(parent,delta) in enumerate(zip(parents,deltas),1):
            for packet in (parent,delta):
                packet['reviewer_declaration'].update({'reviewer_label':f'synthetic-{slot}',
                    'completed_by_human':True,'completed_independently':True,'used_ai_assistance':False})
            for case in parent['cases']:
                if case['history_id'] in changed:
                    case['fact_review']['decision']=None
                    case['additional_source_facts_missing']=None
                    for question in case['questions']: question['review']['question_validity']=None
                    for edge in case['relationship_checks']: edge['review']['decision']=None
                    continue  # old changed cases deliberately remain blank
                case['fact_review']['decision']='accept';case['additional_source_facts_missing']=[]
                for question in case['questions']: question['review']['question_validity']='valid'
                for edge in case['relationship_checks']: edge['review']['decision']='valid'
            for case in delta['cases']:
                case['fact_review']['decision']='accept';case['additional_source_facts_missing']=[]
                for question in case['questions']: question['review']['question_validity']='valid'
                for edge in case['relationship_checks']: edge['review']['decision']='valid'
        combined=merge_revision_reviews(parent_source,parent_plan,revised_source,revised_plan,manifest_raw,
                                        self.encoded(parents),self.encoded(deltas),base_source,base_plan)
        args=self.args[:5]+[revised_source,revised_plan]
        grounds,_=convert(*args,[json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() for row in combined])
        self.assertEqual(sum(len(c['questions']) for c in grounds[0]['cases']),120)
        self.assertTrue(all(c['fact_review']['decision'] is None for c in parents[0]['cases'] if c['history_id'] in changed))
        # Check the actual CLI, revised composite manifest, readiness and mock
        # staging together. Everything below is a temporary synthetic fixture.
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory)
            parent_paths=[REVIEWED_PARENT/f'reviewer-{i}-user-confirmed.json' for i in (1,2)];delta_paths=[]
            for slot,delta in enumerate(deltas,1):
                b=tmp/f'delta-{slot}.json';b.write_text(json.dumps(delta,ensure_ascii=False));delta_paths.append(b)
            out=tmp/'combined'
            command=[sys.executable,str(ROOT/'scripts/import_ac3_expanded_reviews.py'),
                '--old-source',str(OLD/'candidate-inputs.json'),'--old-plan',str(OLD/'proposed-fact-plan.json'),
                '--old-manifest',str(PRIOR/'manifest.json'),
                '--old-ground-1',str(PRIOR/'grounding-reviewer-1.json'),'--old-ground-2',str(PRIOR/'grounding-reviewer-2.json'),
                '--old-fact-1',str(FACT/'fact-review-1.json'),'--old-fact-2',str(FACT/'fact-review-2.json'),
                '--expanded-source',str(REVISION/'candidate-inputs.json'),'--expanded-plan',str(REVISION/'proposed-fact-plan.json'),
                '--new-review-1',str(parent_paths[0]),'--new-review-2',str(parent_paths[1]),
                '--parent-expanded-source',str(REVIEWED_PARENT/'original-candidate-inputs.json'),
                '--parent-expanded-plan',str(REVIEWED_PARENT/'original-proposed-fact-plan.json'),
                '--revision-manifest',str(REVISION/'manifest.json'),'--revision-review-1',str(delta_paths[0]),
                '--revision-review-2',str(delta_paths[1]),'--revision-base-source',str(NEW/'candidate-inputs.json'),
                '--revision-base-plan',str(NEW/'proposed-fact-plan.json'),
                '--parent-review-confirmation',str(REVIEWED_PARENT/'confirmation.json'),
                '--parent-original-review-1',str(REVIEWED_PARENT/'original-reviewer-1.json'),
                '--parent-original-review-2',str(REVIEWED_PARENT/'original-reviewer-2.json'),'--output-dir',str(out)]
            result=subprocess.run(command,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
            readiness=[sys.executable,str(ROOT/'scripts/check_ac3_prospective_readiness.py'),
                '--source',str(REVISION/'candidate-inputs.json'),'--review-1',str(out/'grounding-reviewer-1.json'),
                '--review-2',str(out/'grounding-reviewer-2.json'),'--expanded-manifest',str(out/'manifest.json')]
            result=subprocess.run(readiness,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['both_valid'],120)
            cfg=json.loads((DELIVERY/'ac3-prospective-inputs-2026-10-28-v3/protocol-config-template.json').read_text())
            cfg['human_attestations']={'pilot_provenance_reviewed':True,'pilot_thresholds_accepted':True,
                'held_out_outputs_not_generated_or_inspected':True,'exclusions_and_abstention_policy_frozen':True,
                'responsible_reviewer':'synthetic fixture','provenance_note':'synthetic fixture only'}
            template=json.loads((DELIVERY/'ac3-protocol-review-draft-revised-2026-10-28/protocol-config-expanded-draft.json').read_text())
            cfg['model_configuration']=copy.deepcopy(template['model_configuration'])
            cfg['model_configuration']['runtime_source_sha256']='a'*64
            cfg['model_configuration']['ledger_schema_sha256']='b'*64
            cfg['budget']=copy.deepcopy(template['budget']);cfg['stability_plan']=copy.deepcopy(template['stability_plan'])
            cfg.update({'minimum_decided_coverage':.8,'minimum_human_failure_count':30,'minimum_human_pass_count':30,
                'minimum_independent_histories':30,'abstention_policy':'fixture','exclusion_policy':'fixture',
                'budget_enforcement_plan':'fixture','reference_blinding_plan':'fixture'})
            config=tmp/'config.json';config.write_text(json.dumps(cfg))
            approval={'format':'ac3-user-selected-thresholds-v1','recorded_at_utc':'2026-01-01T00:00:00+00:00',
                'user_response':'synthetic fixture only','selection_basis':'fixture selection',
                'provenance_limitations':'fixture limitations','pilot_draft_sha256':cfg['pilot_draft_sha256'],
                'thresholds':cfg['thresholds'],'held_out_results_seen':False}
            approval_path=tmp/'approval.json';approval_path.write_text(json.dumps(approval));frozen=tmp/'frozen.json'
            command=[sys.executable,str(ROOT/'scripts/freeze_ac3_prospective_suite.py'),
                '--source',str(REVISION/'candidate-inputs.json'),'--review-1',str(out/'grounding-reviewer-1.json'),
                '--review-2',str(out/'grounding-reviewer-2.json'),'--fact-plan',str(REVISION/'proposed-fact-plan.json'),
                '--fact-review-1',str(out/'fact-reviewer-1.json'),'--fact-review-2',str(out/'fact-reviewer-2.json'),
                '--expanded-manifest',str(out/'manifest.json'),'--threshold-approval',str(approval_path),
                '--config',str(config),'--output',str(frozen)]
            result=subprocess.run(command,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(compile_mock(frozen,sha(frozen.read_bytes()),'0.008')['question_count'],120)
            child=tmp/'child.json'
            derived=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_ac3_stability_child.py'),
                '--primary-frozen',str(frozen),'--primary-sha256',sha(frozen.read_bytes()),'--output',str(child)],
                capture_output=True,text=True)
            self.assertEqual(derived.returncode,0,derived.stderr)
            child_plan=compile_mock(child,sha(child.read_bytes()),'0.008')
            self.assertEqual(child_plan['history_count'],10);self.assertEqual(child_plan['question_count'],40)
            self.assertEqual(len({row['repeat_id'] for row in child_plan['items']}),40)
            self.assertTrue(all(row['repeat_id'].startswith('R2:') for row in child_plan['items']))
            self.assertFalse(child_plan['model_called'])
            self.assertEqual(len(child_plan['fact_plan_reviews']),2)
            self.assertIn('no additional human review claimed',child_plan['fact_plan_reviews'][0]['note'])
            original_child=child.read_bytes()
            altered=json.loads(child.read_text());altered['suite']['cases'][0]['source_messages'][0]['text']='changed'
            child.write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError,'differs from the predeclared'):
                compile_mock(child,sha(child.read_bytes()),'0.008')
            child.write_bytes(original_child)
            delta_paths[0].write_text('{}')
            with self.assertRaisesRegex(ValueError,'source file changed'):
                compile_mock(frozen,sha(frozen.read_bytes()),'0.008')
            with self.assertRaisesRegex(ValueError,'source file changed'):
                compile_mock(child,sha(child.read_bytes()),'0.008')
        for case in deltas[0]['cases']:
            if case['history_id'] in changed:
                case['fact_review']['decision']='uncertain';break
        combined=merge_revision_reviews(parent_source,parent_plan,revised_source,revised_plan,manifest_raw,
                                        self.encoded(parents),self.encoded(deltas),base_source,base_plan)
        with self.assertRaisesRegex(ValueError,'not accepted'):
            convert(*args,[json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() for row in combined])


if __name__=='__main__': unittest.main()
