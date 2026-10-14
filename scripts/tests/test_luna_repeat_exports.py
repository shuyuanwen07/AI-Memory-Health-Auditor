"""Synthetic export contracts; no provider call or empirical score claim."""
from copy import deepcopy
import unittest

from scripts.verify_luna_isolated_api import verify_condition_exports


def fixture():
    runs, conditions, csv_rows = [], [], []
    for policy in ('weak_first_hit', 'strong_rule_based'):
        members = []
        for repeat, percentage in enumerate((0, 100), 1):
            rid = f'{policy}-{repeat}'
            members.append(rid)
            runs.append({'run_id': rid, 'strategy': policy, 'result': {
                'overall_score': percentage, 'dimensions': [{'dimension': 'accuracy',
                    'percentage': percentage, 'passed': percentage // 100, 'total': 1,
                    'uncertain_count': 0, 'excluded_evidence_count': 0, 'expected_tests': 1}]}})
        condition = {'condition_id': policy, 'run_ids': members,
                     'planned_runs': 2, 'completed_runs': 2, 'failed_runs': 0,
                     'overall_mean': 50, 'overall_standard_deviation': 50,
                     'dimensions': [{'dimension': 'accuracy', 'mean_percentage': 50,
                         'standard_deviation': 50, 'measured_runs': 2, 'passed': 1,
                         'total': 2, 'uncertain_count': 0, 'excluded_evidence_count': 0,
                         'expected_tests': 2}]}
        conditions.append(condition)
        for field in ('planned_runs', 'completed_runs', 'failed_runs', 'overall_mean', 'overall_standard_deviation'):
            csv_rows.append({'record_type': 'condition', 'condition_id': policy,
                             'metric': field, 'value': str(condition[field])})
        for metric, value in [('mean_percentage', 50), ('answers_passed', 1),
                              ('answers_decided', 2), ('pending_judgments', 0),
                              ('excluded_evidence', 0), ('expected_questions', 2)]:
            csv_rows.append({'record_type': 'dimension', 'condition_id': policy,
                             'dimension': 'accuracy', 'metric': metric, 'value': str(value)})
    return runs, conditions, csv_rows


class RepeatExportTests(unittest.TestCase):
    def test_recomputes_two_repeats_and_population_variation(self):
        verify_condition_exports(*fixture())

    def test_rejects_changed_mean_variation_or_denominator(self):
        for field in ('overall_mean', 'overall_standard_deviation', 'completed_runs'):
            with self.subTest(field=field):
                runs, conditions, rows = fixture()
                conditions[0][field] += 1
                with self.assertRaises(AssertionError):
                    verify_condition_exports(runs, conditions, rows)

    def test_csv_cannot_hide_a_different_mean_or_count(self):
        runs, conditions, rows = fixture()
        rows[0]['value'] = '3'
        with self.assertRaises(AssertionError):
            verify_condition_exports(runs, conditions, rows)

    def test_reused_run_cannot_inflate_conditions(self):
        runs, conditions, rows = fixture()
        conditions.append(deepcopy(conditions[0]))
        with self.assertRaises(AssertionError):
            verify_condition_exports(runs, conditions, rows)

    def test_pending_repeats_remain_unmeasured_in_json_and_csv(self):
        runs, conditions, rows = fixture()
        for run in runs:
            run['result']['overall_score'] = None
            run['result']['dimensions'][0].update(percentage=None, passed=0, total=0, uncertain_count=1)
        for condition in conditions:
            condition.update(overall_mean=None, overall_standard_deviation=None)
            condition['dimensions'][0].update(mean_percentage=None, standard_deviation=None,
                                              measured_runs=0, passed=0, total=0, uncertain_count=2)
        for row in rows:
            if row['metric'] in ('overall_mean', 'overall_standard_deviation', 'mean_percentage'):
                row['value'] = ''
            elif row['metric'] in ('answers_passed', 'answers_decided'):
                row['value'] = '0'
            elif row['metric'] == 'pending_judgments':
                row['value'] = '2'
        verify_condition_exports(runs, conditions, rows)
        next(row for row in rows if row['metric'] == 'overall_mean')['value'] = '0'
        with self.assertRaises(AssertionError):
            verify_condition_exports(runs, conditions, rows)
