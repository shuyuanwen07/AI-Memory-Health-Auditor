"""Fully isolated synthetic protocol/attestations: never human evidence."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from scripts.tests.test_ac3_retest_snapshot_verify import archive
from scripts.ac3_retest_snapshot_verify import formal_signature
from scripts.ac3_retest_paired_fixture import run_fixture
from scripts.ac3_retest_paired_freeze import prepare, compile_isolated, THRESHOLDS
from scripts.ac3_retest_reference_stage import compile_reference_stage
from scripts.ac3_retest_budget_plan import budget_plan, combined_budget_preflight
from scripts.tests.test_ac3_retest_review_intake import synthetic_documents


class PairFreezeTests(unittest.TestCase):
    def setUp(self):
        self.source,self.plan,docs=synthetic_documents()
        self.reviews=[json.dumps(x).encode() for x in docs]
        self.components={'target_runtime':b'synthetic target', 'old_evaluator':archive(' old'), 'new_evaluator':archive(' new')}
        self.snapshot_infos={key:formal_signature(self.components[key]) for key in ('old_evaluator','new_evaluator')}
        self.patch=patch('scripts.ac3_retest_paired_freeze.PRIOR_RUNTIME_SHA256', self.snapshot_infos['old_evaluator']['app_source_sha256']);self.patch.start();self.addCleanup(self.patch.stop)
        self.cfg={'format':'ac3-retest-paired-protocol-v1','thresholds':THRESHOLDS.copy(),
            'minimum_consensus_pass':30,'minimum_consensus_fail':30,'minimum_auto_coverage':.8,
            'policy':{'single_target_answer_per_item':True,'both_graders_use_identical_answer':True,
                      'retain_target_errors':True,'retain_scoring_errors':True,'retain_uncertain_and_unclassified':True,
                      'exclude_after_outcome_inspection':False,'uncertainty_unit':'history'},
            'target':{'provider':'synthetic','model':'fixture','strategy':'fixture','prompt_template_version':'fixture',
                      'memory_configuration_sha256':'a'*64,'temperature':0,'random_seed':1,'output_token_limit':20,'retry_limit':0},
            'budget':{'max_usd':1,'per_request_reservation_usd':.001},
            'scorer':{'provider':'openrouter','model':'openai/gpt-6-luna','output_token_limit':20,
                      'prompt_version':'fixture-structured-v2','retry_limit':0,'variant':'hybrid'},
            'component_sha256':{key:hashlib.sha256(value).hexdigest() for key,value in self.components.items()},
            'evaluator_snapshots':{key:{'app_source_sha256':x['app_source_sha256'],'dependencies_lock_sha256':x['dependencies_lock_sha256']} for key,x in self.snapshot_infos.items()},
            'operator_declaration':{'new_target_results_observed':False,'fixed_before_target_generation':True,'operator_label':'SYNTHETIC'}}

    def freeze(self):
        return prepare(self.source,self.plan,self.reviews,self.cfg,self.components)

    def test_end_to_end_isolated(self):
        frozen=self.freeze()
        staged=compile_isolated(frozen,self.source,self.plan,self.reviews,self.components)
        self.assertEqual(len(staged['test_ids']),120)
        self.assertFalse(staged['model_called']);self.assertFalse(staged['product_execution_supported'])
        result=run_fixture(staged,'a'*64,'b'*64)
        self.assertEqual(result['integrity']['old_grader_records'],120);self.assertTrue(result['synthetic_only'])

    def test_reference_stage_maps_reviewed_memories_without_writes(self):
        frozen=self.freeze()
        staged=compile_reference_stage(frozen,self.source,self.plan,self.reviews,self.components)
        self.assertEqual(len(staged['histories']),30)
        self.assertEqual(len(staged['questions']),120)
        self.assertTrue(all(q['supporting_memory_ids'] for q in staged['questions']))
        self.assertFalse(staged['database_written'])
        self.assertFalse(staged['execution_supported'])
        altered=copy.deepcopy(frozen)
        altered['reviewed_fact_plan']['histories'][staged['histories'][0]['history_id']]['facts'][0]['canonical_value']='changed'
        with self.assertRaises(ValueError):
            compile_reference_stage(altered,self.source,self.plan,self.reviews,self.components)

    def test_paired_budget_projection_requires_review_and_cap(self):
        self.cfg['budget']['max_usd']=.4
        frozen=self.freeze(); raw=json.dumps(frozen).encode(); digest=hashlib.sha256(raw).hexdigest()
        result=budget_plan(raw,digest,self.source,self.plan,self.reviews,self.components,'.001')
        self.assertEqual(result['question_count'],120)
        self.assertEqual(result['planned_target_reservations_usd'],'0.120')
        self.assertFalse(result['execution_supported'])
        with self.assertRaises(ValueError):
            budget_plan(raw,digest,self.source,self.plan,self.reviews,self.components,'.002')
        with self.assertRaises(ValueError):
            budget_plan(raw,b'bad',self.source,self.plan,self.reviews,self.components,'.001')
        self.cfg['budget']['max_usd']=.5
        too_large=self.freeze();raw=json.dumps(too_large).encode()
        with self.assertRaisesRegex(ValueError,'cap'):
            budget_plan(raw,hashlib.sha256(raw).hexdigest(),self.source,self.plan,self.reviews,self.components,'.001')

    def test_combined_budget_keeps_unknown_and_over_limit_blocked(self):
        unknown=combined_budget_preflight(prior_upper_bound_usd=None,target_reserved_usd='.1',scorer_reserved_usd='.1')
        self.assertEqual(unknown['status'],'unresolved')
        self.assertFalse(unknown['may_dispatch'])
        over=combined_budget_preflight(prior_upper_bound_usd='.30',target_reserved_usd='.06',scorer_reserved_usd='.05')
        self.assertEqual(over['status'],'over_planning_cap')
        self.assertEqual(over['projected_total_usd'],'0.41')
        within=combined_budget_preflight(prior_upper_bound_usd='.20',target_reserved_usd='.10',scorer_reserved_usd='.10')
        self.assertEqual(within['status'],'within_planning_cap')
        self.assertFalse(within['may_dispatch'])
        with self.assertRaises(ValueError):
            combined_budget_preflight(prior_upper_bound_usd=True,target_reserved_usd=0,scorer_reserved_usd=0)

    def test_missing_review_and_bad_threshold_and_snapshot(self):
        docs=[json.loads(x) for x in self.reviews]
        docs[0]['reviewer_declaration']['completed_by_human']=None
        self.reviews=[json.dumps(x).encode() for x in docs]
        with self.assertRaises(ValueError): self.freeze()
        _,_,docs=synthetic_documents();self.reviews=[json.dumps(x).encode() for x in docs]
        self.cfg['thresholds']['test_validity_min']=.8
        with self.assertRaises(ValueError): self.freeze()
        self.cfg['thresholds']=THRESHOLDS.copy();self.components['new_evaluator']=b'tampered'
        with self.assertRaises(ValueError): self.freeze()

    def test_frozen_mutation_and_retroactive_attestation(self):
        frozen=self.freeze();tampered=copy.deepcopy(frozen);tampered['suite']['cases'][0]['tests'][0]['question']='changed'
        with self.assertRaises(ValueError):compile_isolated(tampered,self.source,self.plan,self.reviews,self.components)
        self.cfg['operator_declaration']['new_target_results_observed']=True
        with self.assertRaises(ValueError):self.freeze()

    def test_luna_sampling_controls_must_reflect_actual_omission(self):
        self.cfg['target'].update(provider='openrouter',model='openai/gpt-6-luna')
        with self.assertRaisesRegex(ValueError, 'omit temperature and seed'):
            self.freeze()
        self.cfg['target'].update(temperature=None,random_seed=None)
        self.assertEqual(self.freeze()['protocol']['target']['temperature'],None)

    def test_scorer_choice_must_be_fixed_before_results(self):
        for scorer in (None, {}, {**self.cfg['scorer'], 'variant': 'after-seeing-results'},
                       {**self.cfg['scorer'], 'retry_limit': 1}):
            with self.subTest(scorer=scorer):
                config = copy.deepcopy(self.cfg)
                if scorer is None:
                    del config['scorer']
                else:
                    config['scorer'] = scorer
                with self.assertRaises(ValueError):
                    prepare(self.source, self.plan, self.reviews, config, self.components)
        self.cfg['scorer']['variant'] = 'provider_only'
        self.assertEqual(self.freeze()['protocol']['scorer']['variant'], 'provider_only')
