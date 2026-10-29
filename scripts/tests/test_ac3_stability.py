"""Only synthetic fixtures; no provider calls or human-review claims."""
import copy
import json
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from scripts.ac3_stability import canonical_sha, sha, summarize, validate_plan
from scripts import analyze_ac3_stability as cli

ROOT=Path(__file__).resolve().parents[2]
PACKET=ROOT/'output/proposal-delivery/ac3-expanded-30-candidate-draft-2026-10-28-v6'


class StabilityTests(unittest.TestCase):
    def setUp(self):
        suite=json.loads((PACKET/'candidate-inputs.json').read_text())
        facts=json.loads((PACKET/'proposed-fact-plan.json').read_text())
        ids=sorted(c['history_id'] for c in suite['cases'])[::3]
        self.plan={'format':'ac3-stability-plan-v1','selection_rule':'sorted_history_ids_every_third_from_first',
                   'selected_history_ids':ids,'extra_repeats_per_question':1}
        cfg={'model_configuration':{'model':'synthetic-fixture'},'thresholds':{'value':'fixture'},'stability_plan':self.plan}
        self.parent={'study_role':'primary_validation','frozen_at_utc':'2026-01-01T00:00:00+00:00',
                     'suite':suite,'reviewed_fact_plan':facts,'protocol':cfg}
        chosen=copy.deepcopy([c for c in suite['cases'] if c['history_id'] in ids])
        self.child={'study_role':'stability_repeat','parent_frozen_sha256':'parent-sha',
            'stability_plan_sha256':canonical_sha(self.plan),'frozen_at_utc':'2026-01-01T00:01:00+00:00',
            'suite':{'cases':chosen},'reviewed_fact_plan':{'histories':{i:copy.deepcopy(facts['histories'][i]) for i in ids}},'protocol':copy.deepcopy(cfg)}
        def rows(cases):
            return [{'test_id':q['test_id'],'history_id':c['history_id'],'response':f'answer-{q["test_id"]}',
                     'response_sha256':sha(f'answer-{q["test_id"]}'.encode()),
                     'automatic':{'verdict':'pass','failure_dimension':None}} for c in cases for q in c['tests']]
        self.primary={'format':'ac3-heldout-run-export-v1','frozen_sha256':'parent-sha',
                      'started_at_utc':'2026-01-01T00:02:00+00:00','responses':rows(suite['cases'])}
        self.repeat={'format':'ac3-heldout-run-export-v1','frozen_sha256':'child-sha',
                     'started_at_utc':'2026-01-01T00:03:00+00:00','responses':rows(chosen)}
        self.repeat['responses'][0]['automatic']={'verdict':'fail','failure_dimension':'accuracy'}
        self.repeat['responses'][1]['automatic']={'verdict':'uncertain','failure_dimension':None}

    def run_report(self):
        return summarize(self.parent,'parent-sha',self.primary,'primary-run-sha',
                         self.child,'child-sha',self.repeat,'repeat-run-sha')

    def test_40_distinct_paired_repeats_do_not_claim_human_accuracy(self):
        report=self.run_report()
        self.assertEqual(report['pairs'],40)
        self.assertEqual(report['same_automatic_verdict_count'],38)
        self.assertEqual(report['both_decided_pairs'],39)
        self.assertEqual(report['same_decided_verdict_count'],38)
        self.assertEqual(len({x['repeat_id'] for x in report['repeat_ids']}),40)
        self.assertFalse(report['human_reviewed_repeat_answers'])

    def test_selection_cannot_follow_observed_results(self):
        changed=copy.deepcopy(self.plan);changed['selected_history_ids'][0]='AC3-H02'
        with self.assertRaisesRegex(ValueError,'predeclared'):
            validate_plan(changed,self.parent['suite'])
        self.child['frozen_at_utc']='2026-01-01T00:02:01+00:00'
        with self.assertRaisesRegex(ValueError,'before the primary'):
            self.run_report()

    def test_changed_sources_facts_config_or_answer_are_rejected(self):
        for target in ('source','fact','config','answer','duplicate'):
            self.setUp()
            if target=='source': self.child['suite']['cases'][0]['source_messages'][0]['text']='altered'
            if target=='fact': self.child['reviewed_fact_plan']['histories'][self.plan['selected_history_ids'][0]]['facts'][0]['canonical_value']='altered'
            if target=='config': self.child['protocol']['model_configuration']['model']='altered'
            if target=='answer': self.repeat['responses'][0]['response']='altered'
            if target=='duplicate': self.repeat['responses'][1]=copy.deepcopy(self.repeat['responses'][0])
            with self.subTest(target=target),self.assertRaises(ValueError): self.run_report()

    def test_cli_writes_only_descriptive_report_from_bound_synthetic_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp=Path(directory)
            paths=[tmp/'primary-frozen.json',tmp/'primary-run.json',tmp/'repeat-frozen.json',tmp/'repeat-run.json']
            paths[0].write_text(json.dumps(self.parent,ensure_ascii=False))
            primary_sha=sha(paths[0].read_bytes())
            self.primary.update({'frozen_path':str(paths[0]),'frozen_sha256':primary_sha})
            self.child['parent_frozen_sha256']=primary_sha
            paths[1].write_text(json.dumps(self.primary,ensure_ascii=False))
            paths[2].write_text(json.dumps(self.child,ensure_ascii=False))
            self.repeat.update({'frozen_path':str(paths[2]),'frozen_sha256':sha(paths[2].read_bytes())})
            paths[3].write_text(json.dumps(self.repeat,ensure_ascii=False))
            digests=[sha(path.read_bytes()) for path in paths]
            out=tmp/'report.json';names=('primary-frozen','primary-run','repeat-frozen','repeat-run')
            args=['analyze_ac3_stability.py']
            for name,path,digest in zip(names,paths,digests):args += [f'--{name}',str(path),f'--{name}-sha256',digest]
            args+=['--output',str(out)]
            with patch('sys.argv',args),patch.object(cli,'compile_mock'),patch.object(cli,'mock_reservation_for_suite',return_value='0'):
                cli.main()
            report=json.loads(out.read_text());self.assertEqual(report['pairs'],40)
            self.assertFalse(report['human_reviewed_repeat_answers'])
            self.assertEqual(report['repeat_run_sha256'],digests[3])
            with patch('sys.argv',args),patch.object(cli,'compile_mock'),patch.object(cli,'mock_reservation_for_suite',return_value='0'):
                with self.assertRaises(FileExistsError): cli.main()


if __name__=='__main__': unittest.main()
