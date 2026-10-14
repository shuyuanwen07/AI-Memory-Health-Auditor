"""Smoke acceptance status only; no model calls or research conclusions."""
from copy import deepcopy
import unittest

from scripts.smoke_luna_isolated_api import completed_workflow_status


class WorkflowStatusTests(unittest.TestCase):
    def setUp(self):
        self.report = {'extraction_agents': [
            {'role': role, 'status': 'completed'}
            for role in ('memory_extraction', 'relationship_analysis', 'independent_memory_review')
        ], 'runs': [{'diagnostic_agent_status_code': 200}]}

    def test_all_required_stages_complete(self):
        self.assertEqual(completed_workflow_status(self.report), 'completed')

    def test_each_failed_stage_remains_partial(self):
        for index in range(3):
            with self.subTest(index=index):
                report = deepcopy(self.report)
                report['extraction_agents'][index]['status'] = 'failed'
                self.assertEqual(completed_workflow_status(report), 'partial_extraction_failure')

    def test_missing_stage_is_not_success(self):
        self.report['extraction_agents'].pop()
        self.assertEqual(completed_workflow_status(self.report), 'partial_extraction_failure')

    def test_failed_diagnostic_is_partial(self):
        self.report['runs'][0]['diagnostic_agent_status_code'] = 502
        self.assertEqual(completed_workflow_status(self.report), 'partial_diagnostic_failure')

    def test_empty_runs_are_not_success(self):
        self.report['runs'] = []
        self.assertEqual(completed_workflow_status(self.report), 'partial_diagnostic_failure')
