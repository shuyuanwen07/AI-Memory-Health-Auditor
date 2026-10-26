"""Synthetic runtime observations only; fake client and denied network transports."""
import importlib.util
import json
import socket
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.extraction.llm import PipelineLLMClient, PipelineRequestError
from app.memory_agent.identity_evidence import TargetIdentityEvidenceAnalyzer
from app.target_ai.providers import HttpTargetAIConnector

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/run_stability_trial.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('stability_identity_receipts', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('invalid', [False, True])
def test_runner_main_preserves_actual_contract_outcome_and_role_attempt(monkeypatch, tmp_path, invalid):
    protocol = {'strategies': ['strong_rule_based'], 'model': 'openai/gpt-6-luna',
                'provider': 'openrouter', 'output_token_limit': 4096,
                'target_memory_profile': {'identity_analysis': 'evidence_links'},
                'maximum_extra_identity_evidence_calls': 1,
                'assessment_kind': 'synthetic_source_safety'}
    (tmp_path / 'pilot-protocol.json').write_text(json.dumps(protocol))
    seen = {'client_calls': 0, 'network_attempts': 0, 'target_calls': 0}

    def denied(*args, **kwargs):
        seen['network_attempts'] += 1
        raise AssertionError('Network forbidden in synthetic observation test')

    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)

    def fake_client(self, **request):
        seen['client_calls'] += 1
        seen['request'] = request
        self.last_execution = {'provider': protocol['provider'], 'model': protocol['model'],
                               'reported_model': protocol['model'],
                               'agent_role': 'target_identity_evidence', 'status': 'parsed',
                               'requested_output_token_limit': 4096, 'declared_output_token_limit': 4096,
                               'request_attempts': 1}
        return {'quotes': [{'quote_id': 'Q1', 'candidate_id': json.loads(request['prompt'])['quote_candidates'][0]['candidate_id']}],
                'mentions': [{'mention_id': 'M1', 'quote_id': 'Q1'}] +
                            ([{'mention_id': 'M2', 'quote_id': 'Q1'}] if invalid else []),
                'relations': [], 'limitations': 'Synthetic record does not establish an event year.'}

    monkeypatch.setattr(PipelineLLMClient, 'complete_json', fake_client)
    # Register restorations for the class attributes patched inside main().
    monkeypatch.setattr(HttpTargetAIConnector, 'execute', HttpTargetAIConnector.execute)
    monkeypatch.setattr(HttpTargetAIConnector, '_execute_provider', HttpTargetAIConnector._execute_provider)
    monkeypatch.setattr(TargetIdentityEvidenceAnalyzer, 'analyze', TargetIdentityEvidenceAnalyzer.analyze)
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--directory', str(tmp_path)])

    def synthetic_trial(path, run_name):
        assert Path(path).name == 'run_stability_guard_trial.py'
        analyzer = TargetIdentityEvidenceAnalyzer('openrouter', protocol['model'],
                                                client=PipelineLLMClient('openrouter', protocol['model']))
        analyzer.analyze(question='PRIVATE_SYNTHETIC_QUESTION', context=['PRIVATE_SYNTHETIC_SOURCE'])
        # If validation fails, this point (and the hypothetical target) is unreachable.
        seen['target_calls'] += 1

    monkeypatch.setattr(runner.runpy, 'run_path', synthetic_trial)
    if invalid:
        with pytest.raises(PipelineRequestError, match='invalid evidence contract') as raised:
            runner.main()
        assert str(raised.value.__cause__) == 'Duplicate mention quote references.'
    else:
        runner.main()

    private_path = tmp_path / 'identity-observation-receipts.json'
    receipt = json.loads(private_path.read_text())
    assert receipt['provenance'] == 'actual_runtime_observation'
    assert receipt['reconstructed'] is False
    assert len(receipt['observations']) == 1
    row = receipt['observations'][0]
    observed = row['last_observation']
    assert row['analyzer_call_status'] == ('failed' if invalid else 'completed')
    assert row['exception_type'] == ('PipelineRequestError' if invalid else None)
    assert observed['status'] == ('failed' if invalid else 'completed')
    assert observed['instructions'] == seen['request']['instructions']
    assert observed['prompt'] == seen['request']['prompt']
    assert observed['schema'] == seen['request']['schema']
    assert observed['raw_input_payload']['selected_context'] == ['PRIVATE_SYNTHETIC_SOURCE']
    assert row['last_execution'] == observed['execution']
    assert row['last_execution']['request_attempts'] == 1
    if invalid:
        assert observed['error_code'] == 'invalid_identity_contract'
        assert observed['error_diagnostics']['phase'] == 'output_validation'
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    roles = json.loads((tmp_path / 'agent-execution-receipts.json').read_text())
    assert len(roles) == 1
    assert roles[0]['agent_role'] == 'target_identity_evidence'
    assert roles[0]['evidence_payload']['mentions'][-1]['quote_id'] == 'Q1'
    assert roles[0]['execution'] == row['last_execution']
    assert seen['client_calls'] == 1 and seen['network_attempts'] == 0
    assert seen['target_calls'] == (0 if invalid else 1)
    assert not (tmp_path / 'pilot-report.json').exists()


def test_finally_write_failure_preserves_original_exception_and_redacts_log(tmp_path, monkeypatch, capsys):
    original = RuntimeError('PRIVATE_ORIGINAL_ERROR')
    analyzer = SimpleNamespace(last_observation=None, last_execution={'request_attempts': 1})

    def failed(self):
        self.last_observation = {'status': 'failed', 'prompt': 'PRIVATE_PROMPT'}
        raise original

    def broken_replace(*args):
        raise OSError('PRIVATE_WRITE_ERROR')

    monkeypatch.setattr(runner.os, 'replace', broken_replace)
    with pytest.raises(RuntimeError) as caught:
        runner.identity_observation_wrapper(failed, tmp_path)(analyzer)
    assert caught.value is original
    assert json.loads(capsys.readouterr().err) == {
        'identity_observation_write_failure': 'OSError', 'analyzer_call_status': 'failed',
        'analyzer_exception_type': 'RuntimeError'}
    assert list(tmp_path.iterdir()) == []


def test_write_failure_does_not_change_success(tmp_path, monkeypatch, capsys):
    analyzer = SimpleNamespace(last_execution=None)
    monkeypatch.setattr(runner.tempfile, 'mkstemp', lambda **kwargs: (_ for _ in ()).throw(OSError('PRIVATE')))
    assert runner.identity_observation_wrapper(lambda self: 'unchanged', tmp_path)(analyzer) == 'unchanged'
    assert 'PRIVATE' not in capsys.readouterr().err


def test_each_call_appends_actual_observation_without_stale_state(tmp_path):
    analyzer = SimpleNamespace(last_execution=None)

    def analyze(self, index):
        self.last_observation = {'status': 'completed', 'index': index}
        return index

    wrapped = runner.identity_observation_wrapper(analyze, tmp_path)
    assert [wrapped(analyzer, index) for index in [1, 2]] == [1, 2]
    rows = json.loads((tmp_path / 'identity-observation-receipts.json').read_text())['observations']
    assert [row['attempt'] for row in rows] == [1, 2]
    assert [row['last_observation']['index'] for row in rows] == [1, 2]
