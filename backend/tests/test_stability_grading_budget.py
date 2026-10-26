"""Pure synthetic candidate tests; no provider/backend imports or real sources."""
import ast
import copy
import importlib
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(HERE))

from stability_grading_budget import (trial_grader_cap, study_grader_cap, budget_source,
    preflight_grader_budget, grader_budget_matches, output_budget_ledger, validate_budget_ledger, study_trial_grader_budget_matches)



def synthetic_protocol(cap=4096):
    return {'grading': {'output_token_limit': cap}, 'target': {'output_token_limit': 4096,
        'final_target_profile_flags': {'identity_analysis': 'evidence_links', 'identity_analysis_output_token_limit': 4096}},
        'execution': {'planned_total_target_calls': 120, 'planned_maximum_grader_calls': 120, 'extra_model_stage_calls': 60},
        'development_pilot': {'target_calls': 8, 'grader_calls_max': 8, 'evidence_stage_calls_max': 4},
        'critical_guards': {'target_calls': 36, 'grader_calls_max': 36, 'identity_evidence_calls_max': 36},
        'acceptance': {'synthetic_immutable_gate': 1.0}, 'selection': {'selected_ids': ['SYNTHETIC-METADATA-ONLY']}}


def first_call(name, method):
    tree = ast.parse((HERE / name).read_text())
    return next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == method)


class BudgetTests(unittest.TestCase):
    def test_legacy_missing_field_remains1024(self):
        self.assertEqual(trial_grader_cap({}), 1024)
        self.assertEqual(budget_source({}), 'legacy_1024')

    def test_explicit_protocol4096(self):
        self.assertEqual(trial_grader_cap({'grading_output_token_limit': 4096}), 4096)
        self.assertEqual(budget_source({'grading_output_token_limit': 4096}), 'trial_protocol')
        self.assertEqual(study_grader_cap(synthetic_protocol()), 4096)

    def test_study4096_trial1024_is_rejected_despite_consistent_trial_meter(self):
        study = synthetic_protocol(4096)
        trial = {'grading_output_token_limit': 1024}
        meter = {'declared_output_token_limit': 1024, 'requested_output_token_limit': 1024}
        self.assertTrue(grader_budget_matches(trial, meter))
        self.assertFalse(study_trial_grader_budget_matches(study, trial))
        self.assertTrue(study_trial_grader_budget_matches(synthetic_protocol(1024), {}))
        self.assertTrue(study_trial_grader_budget_matches({}, {}))

    def test_runstudy_checks_each_trial_against_study_before_dispatch(self):
        tree = ast.parse((HERE / 'run_stability_study.py').read_text())
        statement = next(node for node in ast.walk(tree) if isinstance(node, ast.Assert)
                         and isinstance(node.test, ast.Call) and isinstance(node.test.func, ast.Name)
                         and node.test.func.id == 'study_trial_grader_budget_matches')
        env = {'protocol': synthetic_protocol(4096), 'directory': Path('/synthetic-no-read'),
               'read': lambda path: {'grading_output_token_limit': 1024},
               'study_trial_grader_budget_matches': study_trial_grader_budget_matches}
        with self.assertRaises(AssertionError):
            exec(compile(ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[])), 'candidate-runstudy', 'exec'), env)
        env['protocol'] = synthetic_protocol(1024)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[])), 'candidate-runstudy', 'exec'), env)

    def test_export_rejects_self_consistent1024_grade_under4096_study(self):
        tree = ast.parse((HERE / 'export_stability_package.py').read_text())
        statement = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == 'grade_budget_ok' for target in node.targets))
        for study_cap, expected in [(4096, False), (1024, True)]:
            env = {'protocol': synthetic_protocol(study_cap), 'trial_protocol': {'grading_output_token_limit': 1024},
                   'grade': {'execution': {'declared_output_token_limit': 1024, 'requested_output_token_limit': 1024}},
                   'study_trial_grader_budget_matches': study_trial_grader_budget_matches, 'grader_budget_matches': grader_budget_matches}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[])), 'candidate-export', 'exec'), env)
            self.assertEqual(env['grade_budget_ok'], expected)

    def test_replay_study_trial_mismatch_is_an_explicit_failed_row_before_target_reconstruction(self):
        tree = ast.parse((HERE / 'replay_stability_study.py').read_text())
        statement = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                         and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.operand, ast.Call)
                         and isinstance(node.test.operand.func, ast.Name)
                         and node.test.operand.func.id == 'study_trial_grader_budget_matches')
        after = ast.parse('after_budget_check = True').body[0]
        loop = ast.For(target=ast.Name(id='fixture_index', ctx=ast.Store()), iter=ast.List(elts=[ast.Constant(0)], ctx=ast.Load()), body=[statement, after], orelse=[])
        env = {'study_protocol': synthetic_protocol(4096), 'protocol': {'grading_output_token_limit': 1024},
               'row': {}, 'rows': [{}], 'matrix': {'trials': [{}]}, 'after_budget_check': False, 'print': lambda *args, **kwargs: None,
               'json': json, 'study_trial_grader_budget_matches': study_trial_grader_budget_matches,
               'study_grader_cap': study_grader_cap, 'trial_grader_cap': trial_grader_cap}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])), 'candidate-replay', 'exec'), env)
        self.assertFalse(env['after_budget_check'])
        self.assertEqual(env['row']['status'], 'error')
        self.assertEqual(env['row']['error_type'], 'StudyTrialGraderBudgetMismatch')
        self.assertEqual(env['row']['study_grader_cap'], 4096)
        self.assertEqual(env['row']['trial_grader_cap'], 1024)

    def test_invalid_cap_is_rejected(self):
        for value in [True, '4096', 0, 12001, 4096.0, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                trial_grader_cap({'grading_output_token_limit': value})

    def test_preflight_environment4096_preserves4096(self):
        result = preflight_grader_budget(4096, {'PIPELINE_MAX_OUTPUT_TOKENS': '4096'})
        self.assertTrue(result['passed'])
        self.assertEqual(result['expected_effective_grader_output_token_limit'], 4096)

    def test_preflight_environment1024_blocks_before_dispatch(self):
        result = preflight_grader_budget(4096, {'PIPELINE_MAX_OUTPUT_TOKENS': '1024'})
        self.assertFalse(result['passed'])
        self.assertEqual(result['planned_grader_output_token_limit'], 4096)
        self.assertEqual(result['configured_pipeline_output_token_cap'], 1024)

    def test_preflight_no_environment_cap_preserves_declaration(self):
        self.assertTrue(preflight_grader_budget(4096, {})['passed'])

    def test_invalid_environment_cap_rejected(self):
        for value in ['not-an-int', '１２３４', '0', '12001']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                preflight_grader_budget(4096, {'PIPELINE_MAX_OUTPUT_TOKENS': value})

    def test_actual_declared_and_effective_caps_must_match_protocol(self):
        protocol = {'grading_output_token_limit': 4096}
        self.assertTrue(grader_budget_matches(protocol, {'declared_output_token_limit': 4096, 'requested_output_token_limit': 4096}))
        for meter in [None, {}, {'declared_output_token_limit': 4096, 'requested_output_token_limit': 1024}, {'declared_output_token_limit': 1024, 'requested_output_token_limit': 4096}]:
            self.assertFalse(grader_budget_matches(protocol, meter))

    def test_old1024_meter_not_upgraded_to_new4096(self):
        meter = {'declared_output_token_limit': 1024, 'requested_output_token_limit': 1024, 'reported_finish_reason': 'length', 'reported_reasoning_tokens': 0}
        self.assertTrue(grader_budget_matches({}, meter))
        self.assertFalse(grader_budget_matches({'grading_output_token_limit': 4096}, meter))
        self.assertEqual(meter['declared_output_token_limit'], 1024)

    def test_ledger_all428_roles_at4096(self):
        ledger = output_budget_ledger(synthetic_protocol())
        self.assertEqual(ledger['all_roles_call_upper_bound_including_pilot_final_and_guards'], 428)
        self.assertEqual(ledger['all_target_output_tokens_max'], 671744)
        self.assertEqual(ledger['all_grader_output_tokens_max'], 671744)
        self.assertEqual(ledger['all_identity_evidence_output_tokens_max'], 409600)
        self.assertEqual(ledger['all_output_token_upper_bound_including_pilot_final_and_guards'], 1753088)
        self.assertEqual(ledger['grader_output_token_max'], 491520)
        self.assertEqual(ledger['development_pilot_target_and_grade_output_tokens_max'], 65536)

    def test_old1024_ledger_is_preserved(self):
        old = output_budget_ledger(synthetic_protocol(1024))
        self.assertEqual(old['all_output_token_upper_bound_including_pilot_final_and_guards'], 1249280)
        self.assertEqual(old['grader_output_token_max'], 122880)

    def test_stale_ledger_rejected_without_touching_acceptance_or_selection(self):
        protocol = synthetic_protocol()
        original = copy.deepcopy(protocol)
        protocol['budget'] = output_budget_ledger(synthetic_protocol(1024))
        with self.assertRaises(ValueError):
            validate_budget_ledger(protocol)
        protocol['budget'] = output_budget_ledger(protocol)
        validate_budget_ledger(protocol)
        self.assertEqual(protocol['acceptance'], original['acceptance'])
        self.assertEqual(protocol['selection'], original['selection'])

    def test_guard_materialization_transmits4096_to_all36_trial_protocols(self):
        materialize = importlib.import_module('prepare_stability_guards').materialize
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); guards = root / 'guards'; guards.mkdir()
            cases = [{'case_id': f'SYNTHETIC-{index}', 'question': 'Synthetic only?', 'question_date': '2026-01-01',
                      'conversation': {'messages': [{'message_id': f'SOURCE-{index}', 'role': 'user', 'content': 'Synthetic source only.', 'timestamp': '2025-01-01'}]}}
                     for index in range(12)]
            (guards / 'conversation-cases.json').write_text(json.dumps({'cases': cases}))
            (guards / 'evaluator-private-criteria.json').write_text(json.dumps({'cases': [{'case_id': case['case_id']} for case in cases]}))
            stage = root / 'safety-guards'
            materialize(root, stage, synthetic_protocol())
            protocols = list(stage.rglob('pilot-protocol.json'))
            self.assertEqual(len(protocols), 36)
            for path in protocols:
                protocol = json.loads(path.read_text())
                self.assertEqual(protocol['grading_output_token_limit'], 4096)
                self.assertEqual(protocol['output_token_limit'], 4096)

    def test_long_study_materializer_binds_the_study_cap_into_trial_protocol(self):
        tree = ast.parse((HERE / 'run_stability_study.py').read_text())
        assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'grader_cap' for target in node.targets))
        env = {'protocol': synthetic_protocol(), 'study_grader_cap': study_grader_cap}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[assignment], type_ignores=[])), 'candidate-materializer', 'exec'), env)
        protocol_dict = next(node for node in ast.walk(tree) if isinstance(node, ast.Dict) and any(isinstance(key, ast.Constant) and key.value == 'grading_output_token_limit' for key in node.keys))
        value = next(value for key, value in zip(protocol_dict.keys, protocol_dict.values) if isinstance(key, ast.Constant) and key.value == 'grading_output_token_limit')
        self.assertEqual(eval(compile(ast.Expression(value), 'candidate-materializer', 'eval'), env), 4096)

    def test_both_actual_grader_call_expressions_use_protocol_cap(self):
        for name in ['run_stability_guard_trial.py', 'run_longmemeval_pilot.py']:
            call = first_call(name, 'complete_json')
            captured = []
            client = SimpleNamespace(complete_json=lambda **kwargs: captured.append(kwargs) or {'correct': True})
            for cap in [1024, 4096]:
                env = {'protocol':{},'client': client, 'grader_cap': trial_grader_cap({'grading_output_token_limit': cap}),
                       'ASSESSMENT_INSTRUCTIONS': 'Synthetic', 'ASSESSMENT_ROLE': 'stability_guard_assessment',
                       'SCHEMA': {}, 'schema': {}, 'prompt': 'Synthetic', 'assessment_instructions': 'Synthetic',
                       'assessment_prompt': 'Synthetic', 'assessment_version': 'synthetic'}
                eval(compile(ast.Expression(call), name, 'eval'), env)
                self.assertEqual(captured[-1]['max_output_tokens'], cap)

    def test_wrapper_rejects_callcap1024_when_trial4096_before_original_agent(self):
        tree = ast.parse((HERE / 'run_stability_trial.py').read_text())
        node = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'agent')
        node.body = [statement for statement in node.body if not isinstance(statement, ast.Nonlocal)]
        attempts = []; failures = []
        def mismatch(kind, value):
            failures.append(kind)
            raise ValueError(kind)
        env = {'grader_cap': 4096, 'protocol': {'grading_output_token_limit': 4096}, 'VALIDATION_ROLE': 'target_answer_validation',
               'assessment_role': 'benchmark_pilot_assessment', 'mismatch': mismatch,
               'original_agent': lambda *args, **kwargs: attempts.append(kwargs), 'grader_budget_matches': grader_budget_matches}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), 'candidate-wrapper', 'exec'), env)
        with self.assertRaises(ValueError):
            env['agent'](SimpleNamespace(), agent_role='benchmark_pilot_assessment', max_output_tokens=1024)
        self.assertEqual(failures, ['grader_protocol_budget_mismatch'])
        self.assertEqual(attempts, [])

    def test_replay_checks_original_protocol_cap_and_records_separate_budget_evidence(self):
        tree = ast.parse((HERE / 'replay_stability_study.py').read_text())
        statements = [node for node in ast.walk(tree) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'grade_budget_equal' for target in node.targets)]
        self.assertEqual(len(statements), 1)
        for cap, expected in [(1024, False), (4096, True)]:
            env = {'protocol': {'grading_output_token_limit': 4096}, 'grades': [{'execution': {'declared_output_token_limit': cap, 'requested_output_token_limit': cap}}], 'grader_budget_matches': grader_budget_matches}
            exec(compile(ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[])), 'candidate-replay', 'exec'), env)
            self.assertEqual(env['grade_budget_equal'], expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
