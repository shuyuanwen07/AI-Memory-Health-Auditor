"""Destructive schema setup confined to the hard-coded disposable PostgreSQL."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from app.services.ac3_attempt_ledger import AttemptLedger

URL = 'postgresql+psycopg://ac3_test:ac3_test_only@ac3-attempt-postgres-test:5432/ac3_test'
pytestmark = pytest.mark.skipif(os.environ.get('AC3_ATTEMPT_DISPOSABLE') != 'yes', reason='isolated DB only')
DIGEST = 'a' * 64
CONTRACT = 'b' * 64

@pytest.fixture
def ledger():
    engine = create_engine(URL, pool_size=10)
    sql = (Path('/app/research_migrations/ac3_attempt_ledger.sql')).read_text()
    with engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS ac3_attempt_receipts'))
        c.execute(text('DROP TABLE IF EXISTS ac3_attempt_scopes'))
        for statement in sql.split(';'):
            if statement.strip(): c.execute(text(statement))
        c.execute(text("INSERT INTO ac3_attempt_scopes (scope_id, frozen_sha256, status) VALUES ('fixture', :sha, 'active')"), {'sha': DIGEST})
    yield AttemptLedger(engine)
    engine.dispose()


def test_dispatch_durable_and_unknown_blocks_all_new_work(ledger):
    assert ledger.begin('fixture', DIGEST, 'q1', CONTRACT, 'T1')['state'] == 'dispatched'
    restored = AttemptLedger(ledger.engine)
    with pytest.raises(ValueError, match='unresolved'): restored.begin('fixture', DIGEST, 'q1', CONTRACT, 'T1')
    with pytest.raises(ValueError, match='unresolved'): restored.begin('fixture', DIGEST, 'q2', CONTRACT, 'T2')
    with pytest.raises(ValueError, match='missing'): restored.settle('fixture', DIGEST, 'q1', 'response', None)
    with pytest.raises(ValueError, match='unresolved'): restored.begin('fixture', DIGEST, 'q2', CONTRACT, 'T2')


def test_settled_response_is_restored_but_not_resent(ledger):
    ledger.begin('fixture', DIGEST, 'q1', CONTRACT, 'T1')
    assert ledger.settle('fixture', DIGEST, 'q1', 'synthetic response', '0.00012')['cost_source'] == 'provider_report_unreconciled'
    previous = ledger.begin('fixture', DIGEST, 'q1', CONTRACT, 'T1')
    assert previous['duplicate'] and previous['response'] == 'synthetic response'
    assert previous['reported_cost_usd'] == '0.00012'
    assert ledger.begin('fixture', DIGEST, 'q2', CONTRACT, 'T2')['state'] == 'dispatched'


def test_concurrent_requests_allow_only_one_unresolved_attempt(ledger):
    def run(i):
        try: return ledger.begin('fixture', DIGEST, f'q{i}', CONTRACT, f'T{i}')['state']
        except ValueError: return 'blocked'
    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(run, range(8)))
    assert result.count('dispatched') == 1 and result.count('blocked') == 7


def test_wrong_suite_or_reused_contract_never_dispatch(ledger):
    with pytest.raises(ValueError, match='Unknown'): ledger.begin('fixture', 'c' * 64, 'q1', CONTRACT, 'T1')
    ledger.begin('fixture', DIGEST, 'q1', CONTRACT, 'T1')
    ledger.settle('fixture', DIGEST, 'q1', 'synthetic response', '0')
    with pytest.raises(ValueError, match='another request'): ledger.begin('fixture', DIGEST, 'q1', 'c' * 64, 'T1')


def test_export_requires_complete_verified_suite(ledger, tmp_path):
    import json
    from unittest.mock import patch
    fake_plan = {'frozen_sha256': DIGEST, 'eligible_question_count': 2, 'items': [
        {'test_id': 'T1', 'grounding_review': 'valid'}, {'test_id': 'T2', 'grounding_review': 'valid'}]}
    output = tmp_path / 'receipts.json'
    with patch('scripts.ac3_fixed_suite_adapter.compile_mock', return_value=fake_plan):
        ledger.begin('fixture', DIGEST, 'q1', CONTRACT, 'T1')
        ledger.settle('fixture', DIGEST, 'q1', 'synthetic response 1', '0.001')
        with pytest.raises(ValueError, match='Not every eligible'):
            ledger.export_settled('fixture', None, DIGEST, '0', output)
        assert not output.exists()
        ledger.begin('fixture', DIGEST, 'q2', CONTRACT, 'T2')
        with pytest.raises(ValueError, match='unresolved'):
            ledger.export_settled('fixture', None, DIGEST, '0', output)
        ledger.settle('fixture', DIGEST, 'q2', 'synthetic response 2', '0.002')
        result = ledger.export_settled('fixture', None, DIGEST, '0', output)
        saved = json.loads(output.read_text())
        assert result['receipt_count'] == 2 and not result['human_outcome_reviewed']
        assert saved['reported_cost_status'] == 'provider_report_unreconciled'
        assert len(saved['responses']) == 2
        with pytest.raises(FileExistsError):
            ledger.export_settled('fixture', None, DIGEST, '0', output)


def test_actual_connector_contract_and_ledger_with_fake_transport(ledger):
    """Test wiring only; no human review or live execution authorization."""
    import httpx
    from unittest.mock import patch
    from app.target_ai.openrouter import CHAT_COMPLETIONS_URL, build_openrouter_target_payload
    from app.target_ai.providers import HttpTargetAIConnector, single_attempt_target_request
    from app.target_ai.request_contracts import observe_request_contracts
    payload = build_openrouter_target_payload(model='openai/gpt-6-luna', instructions='fixture', prompt='fixture', temperature=0, max_output_tokens=10, provider_options={'require_parameters': True, 'allow_fallbacks': False})
    seen = []
    def observer(receipt):
        if receipt['phase'] == 'before_send':
            ledger.begin('fixture', DIGEST, 'q1', receipt['request_contract_sha256'], 'T1')
            seen.append(receipt['request_contract_sha256'])
    reply = {'choices': [{'message': {'content': 'synthetic response'}, 'finish_reason': 'stop'}], 'usage': {'cost': 0.001}}
    with patch('app.target_ai.providers.httpx.post', return_value=httpx.Response(200, json=reply)) as post:
        with single_attempt_target_request(), observe_request_contracts(observer):
            data = HttpTargetAIConnector._post(CHAT_COMPLETIONS_URL, {}, payload)
        assert post.call_count == 1 and len(seen) == 1
    usage = HttpTargetAIConnector._usage(data, __import__('app.schemas', fromlist=['TargetProvider']).TargetProvider.OPENROUTER)
    ledger.settle('fixture', DIGEST, 'q1', data['choices'][0]['message']['content'], usage['reported_cost_usd'])
    assert ledger.begin('fixture', DIGEST, 'q1', seen[0], 'T1')['duplicate']
