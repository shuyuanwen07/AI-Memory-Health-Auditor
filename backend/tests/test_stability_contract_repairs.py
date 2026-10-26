"""Synthetic only; standard-library tests, no real benchmark data or model clients."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE if (HERE / 'export_stability_package.py').exists() else HERE.parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('candidate_export', SCRIPTS / 'export_stability_package.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)
REQUIRED = ['run_id', 'case_id', 'target_status', 'target_response_path', 'target_response_sha256', 'automatic_grade_path', 'automatic_grade_unchanged', 'source_message_ids', 'write_receipt_path', 'retention_receipt_path', 'retrieval_receipt_path', 'final_input_path', 'identity_observation_path', 'claims', 'critical_errors', 'omissions', 'usefulness', 'pipeline_losses', 'review_limitations']

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_synthetic_cli(command):
    # Container execution must use the fixture workspace, never /app's real runtime.
    wrapper = "import runpy,sys; from pathlib import Path; original=Path.exists; Path.exists=lambda self: False if str(self)=='/app/app' else original(self); sys.argv=sys.argv[1:]; sys.path.insert(0,str(Path(sys.argv[0]).parent)); runpy.run_path(sys.argv[0],run_name='__main__')"
    return subprocess.run([command[0], '-c', wrapper, *command[1:]], capture_output=True, text=True)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name)
        trials = []
        reviews = []
        for case in range(12):
            for round_ in [1, 2, 3]:
                row = {'case_id': f'SYNTHETIC-{case}', 'round': round_, 'arm': 'strong_rule_based', 'directory': f'trials/{case}/{round_}'}
                trials.append(row)
                text = f'Synthetic only: 零 {case} round {round_}.\n'
                report = {'status': 'completed', 'target_call_receipts': [{'status': 'completed', 'response': {'response_text': text, 'execution_metadata': {'completion_status': 'complete', 'finish_reason': 'stop'}}}], 'semantic_assessments': [{'status': 'completed'}]}
                report['benchmark_result'] = {'run_id': f'{case}-{round_}'}
                write(self.stage / row['directory'] / 'pilot-report.json', report)
                write(self.stage / row['directory'] / 'guard-case.json', {'conversation': {'messages': [{'message_id': 'SOURCE-001', 'content': 'Synthetic only: saved original source.'}]}, 'runtime_source_id_map': [{'original_source_id': 'SOURCE-001', 'runtime_source_id': 'MSG-001'}]})
                review = {key: None for key in REQUIRED}
                review.update({**{key: row[key] for key in ('case_id', 'round', 'arm')}, 'run_id': f'{case}-{round_}', 'target_status': 'completed', 'target_response_path': row['directory'] + '/pilot-report.json', 'target_response_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'automatic_grade_unchanged': True, 'critical_errors': [], 'claims': [{'claim': 'Synthetic only:', 'source_support': 'supported', 'source_quote': 'Synthetic only:', 'source_message_id': 'MSG-001', 'supplied_quote_verified': True, 'explanation': 'Synthetic source quote matches.'}], 'review_limitations': ['Synthetic fixture only.']})
                reviews.append(review)
        write(self.stage / 'trial-matrix.json', {'trials': trials})
        write(self.stage / 'study-execution.json', {'status': 'completed', 'trials': [{**row, 'status': 'completed'} for row in trials]})
        self.review = {'status': 'completed', 'reviewed_trials': 36, 'critical_error_count': 0, 'trials': reviews}

    def validate(self):
        return export.validate_source_reviews(self.review, self.stage, REQUIRED, 36)

    def test_exact36_unicode_response_bound_rows_pass(self):
        gate, rows = self.validate()
        self.assertEqual(gate['status'], 'pass')
        self.assertEqual(len(rows), 36)

    def test_summary_only_cannot_pass(self):
        self.review['trials'] = []
        gate, rows = self.validate()
        self.assertEqual(gate['status'], 'fail')
        self.assertEqual(gate['observed']['reviewed_trials'], 0)
        self.assertEqual(rows, {})

    def test_duplicate_and_missing_key_cannot_pass(self):
        self.review['trials'][-1] = copy.deepcopy(self.review['trials'][0])
        gate, rows = self.validate()
        self.assertEqual(gate['status'], 'fail')
        self.assertEqual(len(rows), 34)

    def test_wrong_response_hash_excludes_join(self):
        self.review['trials'][0]['target_response_sha256'] = '0' * 64
        gate, rows = self.validate()
        self.assertEqual(gate['status'], 'fail')
        self.assertNotIn(('SYNTHETIC-0', 1, 'strong_rule_based'), rows)

    def test_critical_count_is_derived_not_summary(self):
        self.review['trials'][0]['critical_errors'] = [{'category': 'unsupported_merge'}]
        gate, _ = self.validate()
        self.assertEqual(gate['status'], 'fail')
        self.assertEqual(gate['observed']['critical_error_count'], 1)

    def test_explicit_failed_review_stays_failed(self):
        self.review['status'] = 'failed'
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_missing_round_cannot_pass(self):
        self.review['trials'][0].pop('round')
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_missing_required_field_cannot_pass(self):
        self.review['trials'][0].pop('final_input_path')
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_technical_target_not_safe(self):
        path = self.stage / 'trials/0/1/pilot-report.json'
        report = json.loads(path.read_text())
        report['target_call_receipts'][0]['status'] = 'failed'
        write(path, report)
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_missing_grade_attempt_not_review_terminal(self):
        path = self.stage / 'trials/0/1/pilot-report.json'
        report = json.loads(path.read_text())
        report['semantic_assessments'] = []
        write(path, report)
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_running_execution_stays_pending(self):
        execution = json.loads((self.stage / 'study-execution.json').read_text())
        execution['status'] = 'running'
        write(self.stage / 'study-execution.json', execution)
        self.assertEqual(self.validate()[0]['status'], 'pending')

    def test_original_grade_must_stay_unchanged(self):
        self.review['trials'][0]['automatic_grade_unchanged'] = False
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_claim_fields_required(self):
        self.review['trials'][0]['claims'] = [{'claim': 'synthetic'}]
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_invalid_round_type_rejected_without_crash(self):
        self.review['trials'][0]['round'] = []
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_absent_schema_cannot_pass(self):
        self.assertEqual(export.validate_source_reviews(self.review, self.stage, [], 36)[0]['status'], 'fail')

    def test_optional_sidecar_absent_leaves_no_reviews(self):
        self.assertEqual(export.validate_source_reviews(None, self.stage, [], None)[1], {})

    def test_optional_sidecar_maps_only_hash_bound_rows(self):
        self.review['trials'][0]['target_response_sha256'] = '0' * 64
        _, rows = export.validate_source_reviews(self.review, self.stage, [], None)
        self.assertEqual(len(rows), 35)

    def test_run_id_must_match_saved_benchmark(self):
        self.review['trials'][0]['run_id'] = 'another-run'
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_empty_claims_cannot_pass(self):
        self.review['trials'][0]['claims'] = []
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_claim_must_be_exact_target_substring(self):
        self.review['trials'][0]['claims'][0]['claim'] = 'Not in the target response'
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_claim_enum_and_types_are_checked(self):
        claim = self.review['trials'][0]['claims'][0]
        original = copy.deepcopy(claim)
        for field, value in [('source_support', []), ('source_support', 'maybe'), ('supplied_quote_verified', 'yes'), ('source_message_id', []), ('explanation', ''), ('source_quote', 0)]:
            self.review['trials'][0]['claims'][0] = {**original, field: value}
            self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_source_quote_must_match_mapped_original_message(self):
        self.review['trials'][0]['claims'][0]['source_quote'] = 'Invented original message'
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_supported_claim_requires_source_quote(self):
        self.review['trials'][0]['claims'][0]['source_quote'] = None
        self.assertEqual(self.validate()[0]['status'], 'fail')

    def test_replay_requires_grade_coverage_and_current_matrix(self):
        trials = json.loads((self.stage / 'trial-matrix.json').read_text())['trials']
        proof = {'status': 'passed', 'model_calls': 0, 'network_attempts': 0, 'trial_matrix_sha256': digest(self.stage / 'trial-matrix.json'), 'compared_trials': 36, 'grader_input_comparisons': 36, 'planned_grader_input_comparisons': 36, 'rows': [{**row, 'inputs_equal': True, 'grade_input_compared': True} for row in trials]}
        self.assertTrue(export.replay_is_complete(proof, self.stage, 36))
        for mutation in [dict(grader_input_comparisons=35), dict(trial_matrix_sha256='0' * 64), dict(rows=[]), dict(network_attempts=1)]:
            with self.subTest(mutation=list(mutation)):
                self.assertFalse(export.replay_is_complete({**proof, **mutation}, self.stage, 36))
        legacy = {key: value for key, value in proof.items() if key not in {'grader_input_comparisons', 'planned_grader_input_comparisons'}}
        self.assertTrue(export.replay_is_complete(legacy, self.stage, 36))
        proof['rows'][0]['grade_input_compared'] = False
        self.assertFalse(export.replay_is_complete(proof, self.stage, 36))


class GradeIdentityTests(unittest.TestCase):
    def test_legacy_empty_target_receipts_keep_report_failure_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            diagnostics = export.failure_diagnostics({'status': 'failed', 'error_code': 'PipelineRequestError', 'target_call_receipts': [], 'semantic_assessments': []}, Path(temp))
            self.assertEqual(diagnostics, {'report_status': 'failed', 'report_error_code': 'PipelineRequestError', 'target_error_code': None, 'target_receipt_count': 0, 'grading_attempt_count': 0})

    def test_private_identity_observation_projects_only_safe_failed_reason_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            secret = 'PRIVATE_SYNTHETIC_SECRET_MARKER'
            write(directory / 'identity-observation-receipts.json', {'input_payload': secret, 'observations': [
                {'attempt': 1, 'analyzer_call_status': 'completed', 'exception_type': secret, 'last_observation': {'status': 'completed', 'error_summary': secret}},
                {'attempt': 2, 'analyzer_call_status': 'failed', 'exception_type': 'PipelineRequestError', 'last_execution': {'raw_input_payload': secret}, 'last_observation': {'status': 'failed', 'error_code': 'invalid_identity_contract', 'error_summary': 'Target identity evidence was not accepted.', 'instructions': secret, 'prompt': secret, 'input_payload': secret, 'raw_input_payload': secret, 'unvalidated_output_data': secret, 'error_diagnostics': {'phase': 'output_validation', 'validation_type': 'ValueError', 'reason_code': 'duplicate_mention_quote_reference', 'raw': secret, 'prompt': secret, 'unvalidated_output': secret}}}]})
            diagnostics = export.failure_diagnostics({'status': 'failed', 'error_code': 'PipelineRequestError', 'target_call_receipts': [], 'semantic_assessments': []}, directory)
            serialized = json.dumps(diagnostics)
            self.assertNotIn(secret, serialized)
            self.assertEqual(len(diagnostics['identity_observations']), 1)
            failure = diagnostics['identity_observations'][0]
            self.assertEqual(failure['attempt'], 2)
            self.assertEqual(failure['last_observation']['error_diagnostics']['reason_code'], 'duplicate_mention_quote_reference')
            self.assertEqual(set(failure['last_observation']), {'error_code', 'error_summary', 'error_diagnostics'})


    def test_failed_grade_cannot_be_a_semantic_grade(self):
        grade = {'status': 'failed', 'error_code': 'SyntheticTimeout', 'execution': {'status': 'failed'}}
        original = copy.deepcopy(grade)
        self.assertIsNone(export.valid_semantic_grade('error', grade))
        self.assertEqual(grade, original)
        self.assertIsNone(export.valid_semantic_grade('error', {'status': 'completed', 'verdict': {'correct': True}}))

    def test_valid_original_grade_unchanged(self):
        grade = {'status': 'completed', 'verdict': {'correct': False, 'reason': 'Synthetic original grade.'}, 'execution': {'reported_model': 'openai/gpt-6-luna'}}
        self.assertIs(export.valid_semantic_grade('completed', grade)['correct'], False)

    def test_missing_role_identity_fails(self):
        run = {'target_usable': True, 'case_id': 'SYNTHETIC', 'split': 'evaluation', 'round': 1, 'arm': 'weak_first_hit', 'grading_attempt': {'status': 'completed'}, 'extra_agent_executions': []}
        self.assertEqual(len(export.actual_role_mismatches([run])), 1)
        run['grading_attempt']['execution'] = {'reported_model': 'openai/gpt-6-luna', 'model': 'openai/gpt-6-luna', 'provider': 'openrouter', 'agent_role': 'benchmark_pilot_assessment'}
        self.assertEqual(export.actual_role_mismatches([run]), [])
        run['extra_agent_executions'] = [{'agent_role': 'target_identity_evidence', 'execution': None}]
        self.assertEqual(len(export.actual_role_mismatches([run])), 1)


class RunnerExitTests(unittest.TestCase):
    def test_real_runner_cli_saves_partial_failure_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / 'backend/app').mkdir(parents=True)
            (workspace / 'scripts').mkdir()
            script = workspace / 'scripts/run_stability_study.py'
            shutil.copy2(SCRIPTS / script.name, script)
            shutil.copy2(SCRIPTS / 'stability_grading_budget.py', workspace / 'scripts/stability_grading_budget.py')
            shutil.copy2(SCRIPTS / 'stability_configuration.py', workspace / 'scripts/stability_configuration.py')
            (workspace / 'scripts/run_stability_trial.py').write_text('raise SystemExit(1)\n')
            root = workspace / 'synthetic-study'
            protocol = {'acceptance': {}, 'target': {'final_target_profile_flags': {'identity_analysis': 'off'}, 'profile_is_provisional_pending_parent_final_interface': False}}
            selected = {'status': 'selection_complete', 'selected_ids': []}
            write(root / 'study-protocol.json', protocol)
            write(root / 'selected-metadata.json', selected)
            write(root / 'selection-commitment.json', {'quantitative_acceptance_sha256': hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest(), 'selected_metadata_sha256': digest(root / 'selected-metadata.json'), 'selected_ids': []})
            (workspace / 'scripts/prepare_stability_study.py').write_text('# Synthetic only\n')
            args = [sys.executable, str(script), '--root', str(root), '--stage', 'development-pilot', '--phase']
            freeze = run_synthetic_cli([*args, 'freeze'])
            self.assertEqual(freeze.returncode, 0, freeze.stderr)
            stage = root / 'development-pilot'
            directory = stage / 'trials/synthetic'
            write(directory / 'pilot-protocol.json', {})
            write(directory / 'pilot-subset.json', [])
            trial = {'directory': 'trials/synthetic', 'case_id': 'SYNTHETIC', 'split': 'development', 'round': 1, 'arm': 'weak_first_hit', 'protocol_sha256': digest(directory / 'pilot-protocol.json'), 'source_sha256': digest(directory / 'pilot-subset.json')}
            write(stage / 'trial-matrix.json', {'trials': [trial]})
            run = run_synthetic_cli([*args, 'run'])
            self.assertEqual(run.returncode, 1, run.stderr)
            terminal = json.loads((stage / 'study-execution.json').read_text())
            self.assertEqual(terminal['status'], 'partial_failure')
            self.assertEqual(terminal['trials'][0]['exit_code'], 1)


class ExportCliTests(unittest.TestCase):
    def test_real_export_cli_preserves_failed_grade_separately_and_binds_sidecar(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = parent / 'synthetic-study'
            stage = root / 'development-pilot'
            write(root / 'study-protocol.json', {'development_pilot': {'selected_ids': ['DEV-SYNTHETIC']}})
            write(root / 'selected-metadata.json', {'dataset_sha256': 'synthetic', 'selected_metadata': []})
            write(root / 'selection-commitment.json', {})
            write(parent / 'longmemeval-identity-conservative-final-20261021/regression-4096/run-01/suite-manifest.json', {'cases': [{'case_id': 'DEV-SYNTHETIC', 'category': 'synthetic'}]})
            trials = []
            reviews = []
            identity = {'reported_model': 'openai/gpt-6-luna', 'model': 'openai/gpt-6-luna', 'provider': 'openrouter', 'agent_role': 'benchmark_pilot_assessment'}
            text = 'Synthetic saved target response only.'
            for arm in ['weak_first_hit', 'strong_rule_based']:
                directory = f'trials/development/round-1/DEV-SYNTHETIC/{arm}'
                trial = {'case_id': 'DEV-SYNTHETIC', 'round': 1, 'arm': arm, 'directory': directory}
                trials.append(trial)
                grade = {'status': 'failed', 'error_code': 'SyntheticTimeout', 'execution': identity, 'verdict': {'correct': True, 'reason': 'A failed attempt must not enter valid statistics.'}}
                target = {'status': 'completed', 'response': {'response_text': text, 'execution_metadata': {'reported_model': 'openai/gpt-6-luna', 'response_source': 'openrouter', 'completion_status': 'complete', 'finish_reason': 'stop'}}}
                write(stage / directory / 'pilot-report.json', {'status': 'partial_assessment_failure', 'target_call_receipts': [target], 'semantic_assessments': [grade]})
                reviews.append({**trial, 'target_status': 'completed', 'target_response_sha256': hashlib.sha256(text.encode()).hexdigest(), 'claims': [{'claim': 'Synthetic saved target response', 'source_support': 'not_assessable', 'source_quote': None, 'source_message_id': None, 'supplied_quote_verified': None, 'explanation': 'Synthetic optional sidecar.'}], 'critical_errors': []})
            write(stage / 'inputs/development/DEV-SYNTHETIC.json', [{'question': 'Synthetic count?', 'answer': 0}])
            write(stage / 'trial-matrix.json', {'trials': trials})
            write(stage / 'study-execution.json', {'status': 'partial_failure', 'trials': [{**trial, 'status': 'error'} for trial in trials]})
            write(stage / 'case-source-reviews.json', {'status': 'completed', 'trials': reviews})
            output = root / 'result-package.json'
            result = subprocess.run([sys.executable, str(SCRIPTS / 'export_stability_package.py'), '--root', str(root), '--stage', 'development-pilot', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(output.read_text())
            self.assertEqual(envelope['payload_sha256'], hashlib.sha256(envelope['payload_json'].encode()).hexdigest())
            payload = json.loads(envelope['payload_json'])
            runs = payload['splits'][0]['cases'][0]['runs']
            self.assertEqual(payload['splits'][0]['cases'][0]['reference_answer'], 0)
            for run in runs:
                self.assertEqual(run['status'], 'error')
                self.assertIsNone(run['semantic_grade'])
                self.assertEqual(run['grading_attempt']['error_code'], 'SyntheticTimeout')
                self.assertTrue(run['grading_attempt']['verdict']['correct'])
                self.assertEqual(run['source_review']['target_response_sha256'], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(payload['acceptance_results']['gates']['grade_coverage']['observed'], 0)
            self.assertEqual(payload['acceptance_results']['status_counts'], {'error': 2})
            for trial in trials:
                write(stage / trial['directory'] / 'pilot-report.json', {'status': 'failed', 'error_code': 'PipelineRequestError', 'target_call_receipts': [], 'semantic_assessments': []})
            result = subprocess.run([sys.executable, str(SCRIPTS / 'export_stability_package.py'), '--root', str(root), '--stage', 'development-pilot', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            empty_payload = json.loads(json.loads(output.read_text())['payload_json'])
            for run in empty_payload['splits'][0]['cases'][0]['runs']:
                self.assertEqual(run['failure_diagnostics']['target_receipt_count'], 0)
                self.assertEqual(run['failure_diagnostics']['grading_attempt_count'], 0)
                self.assertEqual(run['failure_diagnostics']['report_error_code'], 'PipelineRequestError')
                self.assertEqual(run['status'], 'error')
                self.assertIsNone(run['semantic_grade'])



class ReplayCliTests(unittest.TestCase):
    def test_real_replay_cli_missing_grade_saves_failed_proof_and_exits_nonzero(self):
        self.run_replay_fixture(False)

    def test_frozen_runtime_empty_receipt_keeps_failed_row_and_original_proof(self):
        self.run_replay_fixture(True)

    def run_replay_fixture(self, diagnostic):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            scripts = workspace / 'scripts'
            scripts.mkdir()
            shutil.copy2(SCRIPTS / 'replay_stability_study.py', scripts / 'replay_stability_study.py')
            shutil.copy2(SCRIPTS / 'stability_grading_budget.py', scripts / 'stability_grading_budget.py')
            shutil.copy2(SCRIPTS / 'stability_auxiliary.py', scripts / 'stability_auxiliary.py')
            shutil.copy2(SCRIPTS / 'stability_configuration.py', scripts / 'stability_configuration.py')
            shutil.copy2(SCRIPTS / 'stability_request_contracts.py', scripts / 'stability_request_contracts.py')
            shutil.copy2(SCRIPTS / 'stability_answer_validation.py', scripts / 'stability_answer_validation.py')
            modules = {
                'benchmarks/live.py': "from types import SimpleNamespace\nclass LiveBenchmarkRunner:\n def run(self, request):\n  from app.target_ai.providers import HttpTargetAIConnector\n  test=SimpleNamespace(expected_behavior=None,supporting_memory_ids=[],prompt='Synthetic question')\n  audit=SimpleNamespace(target_configuration='strong',target_memory_profile=SimpleNamespace(output_token_limit=4096))\n  HttpTargetAIConnector()._execute_provider(audit,test,'Synthetic instructions','unused')\n",
                'schemas/benchmark.py': 'class LiveBenchmarkRequest:\n def __init__(self, **kwargs): pass\n',
                'target_ai/providers.py': "class HttpTargetAIConnector:\n _credential_for=staticmethod(lambda provider: 'unused')\n def _execute_provider(self,*args): raise RuntimeError('unexpected provider call')\n def execute(self,*args): raise RuntimeError('unexpected target call')\n",
                'target_ai/rule_based.py': "from types import SimpleNamespace\ndef memory_input_evidence(*args): return SimpleNamespace(model_dump=lambda **kwargs: {})\ndef target_question_input(prompt): return prompt\n",
                'extraction/llm.py': "class PipelineRequestError(RuntimeError): pass\nclass PipelineLLMClient:\n def complete_json(self, **kwargs): raise RuntimeError('unexpected agent call')\n",
            }
            for relative, source in modules.items():
                path = workspace / 'backend/app' / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
                parent = path.parent
                while parent != workspace / 'backend':
                    (parent / '__init__.py').touch()
                    parent = parent.parent
            (scripts / 'run_longmemeval_pilot.py').write_text('def protocol_memory_profile(protocol): return {}\n')
            (scripts / 'longmemeval_grading.py').write_text('def load_upstream_prompt(directory): return (lambda *args, **kwargs: "Synthetic grade input"), {}\n')
            if diagnostic:
                (scripts / 'replay_stability_study.py').write_text('# Original frozen harness, never executed by this test.\n')
            root = workspace / 'synthetic-study'
            stage = root / 'development-pilot'
            write(root / 'study-protocol.json', {})
            manifest = {str(path.relative_to(workspace)): digest(path) for path in [*(workspace / 'backend/app').rglob('*.py'), *scripts.glob('*.py')]}
            write(stage / 'tested-source-manifest.json', manifest)
            write(stage / 'FROZEN.json', {'protocol_sha256': digest(root / 'study-protocol.json'), 'source_manifest_sha256': digest(stage / 'tested-source-manifest.json'), 'fixture_manifest': {}})
            directory = stage / 'trials/synthetic'
            protocol = {'source_provenance': {'revision': 'synthetic', 'license': 'synthetic', 'citation': 'synthetic'}, 'provider': 'openrouter', 'model': 'openai/gpt-6-luna', 'strategies': ['strong_rule_based'], 'upstream_evaluator_directory': '.'}
            write(directory / 'pilot-protocol.json', protocol)
            write(directory / 'pilot-subset.json', [{'question_type': 'synthetic', 'question': 'Synthetic question', 'answer': 0, 'question_id': 'SYNTHETIC'}])
            write(directory / 'pilot-report.json', {'target_call_receipts': [{'status': 'completed', 'response': {'response_text': 'Synthetic response', 'execution_metadata': {'memory_input': {}}}}], 'semantic_assessments': []})
            instructions = 'Synthetic instructions'
            question = 'Synthetic question'
            sha_text = lambda text: hashlib.sha256(text.encode()).hexdigest()
            write(directory / 'actual-input-receipt.json', {'memory_input': {}, 'instruction_sha256': sha_text(instructions), 'question_sha256': sha_text(question), 'combined_input_sha256': sha_text(json.dumps({'instructions': instructions, 'question': question}, sort_keys=True)), 'requested_output_token_limit': 4096, 'identity_advisory_sha256': None})
            trial = {'split': 'development', 'case_id': 'SYNTHETIC', 'round': 1, 'arm': 'strong_rule_based', 'directory': 'trials/synthetic', 'protocol_sha256': digest(directory / 'pilot-protocol.json'), 'source_sha256': digest(directory / 'pilot-subset.json')}
            trials = [trial]
            if diagnostic:
                report = json.loads((directory / 'pilot-report.json').read_text())
                report['semantic_assessments'] = [{'status': 'completed', 'execution': {'input_fingerprint': sha_text('Synthetic grade input'), 'declared_output_token_limit': 1024, 'requested_output_token_limit': 1024}}]
                write(directory / 'pilot-report.json', report)
                missing_directory = stage / 'trials/missing'
                write(missing_directory / 'pilot-protocol.json', protocol)
                write(missing_directory / 'pilot-subset.json', [{'question_type': 'synthetic', 'question': 'Synthetic question', 'answer': 0, 'question_id': 'SYNTHETIC'}])
                write(missing_directory / 'pilot-report.json', {'status': 'failed', 'target_call_receipts': [], 'semantic_assessments': []})
                trials.append({**trial, 'case_id': 'SYNTHETIC-MISSING', 'directory': 'trials/missing'})
                write(stage / 'replay-proof.json', {'original': 'must remain unchanged'})
            write(stage / 'trial-matrix.json', {'trials': trials})
            command = [sys.executable, str(SCRIPTS / 'replay_stability_study.py' if diagnostic else scripts / 'replay_stability_study.py'), '--root', str(root), '--stage', 'development-pilot']
            if diagnostic:
                command += ['--frozen-source-root', str(workspace)]
            result = run_synthetic_cli(command)
            self.assertEqual(result.returncode, 1, result.stderr)
            proof_path = stage / ('replay-proof-frozen-diagnostic.json' if diagnostic else 'replay-proof.json')
            self.assertTrue(proof_path.exists(), result.stderr)
            proof = json.loads(proof_path.read_text())
            self.assertEqual(proof['status'], 'failed')
            self.assertEqual(proof['compared_trials'], 1, proof)
            self.assertEqual(proof['grader_input_comparisons'], 1 if diagnostic else 0)
            self.assertEqual(proof['planned_grader_input_comparisons'], 2 if diagnostic else 1)
            if diagnostic:
                self.assertEqual(proof['rows'][1]['error_type'], 'MissingTargetReceipt')
                self.assertTrue(proof['rows'][0]['grade_input_compared'])
                self.assertFalse(proof['rows'][1]['grade_input_compared'])
                self.assertFalse(proof['source_unchanged'])
                self.assertTrue(proof['runtime_source_unchanged'])
                self.assertFalse(proof['replay_harness_matches_frozen_source'])
                self.assertEqual(json.loads((stage / 'replay-proof.json').read_text()), {'original': 'must remain unchanged'})
            else:
                self.assertFalse(proof['rows'][0]['grade_input_compared'])
            self.assertEqual(proof['model_calls'], 0)
            self.assertEqual(proof['network_attempts'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
