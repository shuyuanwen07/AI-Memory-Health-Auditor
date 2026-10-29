"""All human attestations and outputs in this file are test fixtures."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import pytest
from scripts.ac3_dispatch_recovery_fixture import FixtureDispatchLedger, FixtureProvider
from scripts.tests.test_ac3_rehearsal_workflow import frozen


def test_persisted_success_resumes_without_second_dispatch(frozen):
    path, digest, _ = frozen
    with tempfile.TemporaryDirectory(prefix='ac3-dispatch-test-') as temp:
        db = Path(temp) / 'ledger.sqlite'
        provider = FixtureProvider()
        ledger = FixtureDispatchLedger(db, path, digest)
        test_id = next(iter(ledger._plan()))
        assert ledger.dispatch('request', test_id, provider)['state'] == 'settled'
        restored = FixtureDispatchLedger(db, path, digest)
        assert restored.dispatch('request', test_id, provider)['duplicate']
        assert provider.calls == 1
        assert restored.inspect('request')['response'] == provider.response


def test_unknown_outcome_survives_restart_and_retries_fail(frozen):
    path, digest, _ = frozen
    with tempfile.TemporaryDirectory(prefix='ac3-dispatch-test-') as temp:
        db = Path(temp) / 'ledger.sqlite'
        provider = FixtureProvider(fail=True)
        ledger = FixtureDispatchLedger(db, path, digest)
        test_id = next(iter(ledger._plan()))
        with pytest.raises(RuntimeError): ledger.dispatch('request', test_id, provider)
        restored = FixtureDispatchLedger(db, path, digest)
        assert restored.inspect('request')['state'] == 'unknown'
        with pytest.raises(ValueError, match='unresolved'): restored.dispatch('request', test_id, provider)
        assert provider.calls == 1


def test_concurrent_request_does_not_double_dispatch(frozen):
    path, digest, _ = frozen
    with tempfile.TemporaryDirectory(prefix='ac3-dispatch-test-') as temp:
        db = Path(temp) / 'ledger.sqlite'
        provider = FixtureProvider()
        ledger = FixtureDispatchLedger(db, path, digest)
        test_id = next(iter(ledger._plan()))
        def run(_):
            try: return ledger.dispatch('request', test_id, provider)['state']
            except ValueError: return 'blocked'
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(run, range(6)))
        assert provider.calls == 1
        assert ledger.inspect('request')['state'] == 'settled'
        assert all(x in ('settled', 'blocked') for x in results)


def test_changed_review_prevents_provider_call(frozen):
    path, digest, reviewers = frozen
    with tempfile.TemporaryDirectory(prefix='ac3-dispatch-test-') as temp:
        provider = FixtureProvider()
        ledger = FixtureDispatchLedger(Path(temp) / 'ledger.sqlite', path, digest)
        test_id = next(iter(ledger._plan()))
        reviewers[0].write_text('{}')
        with pytest.raises(ValueError, match='source file changed'): ledger.dispatch('request', test_id, provider)
        assert provider.calls == 0 and ledger.inspect('request') is None


def test_real_provider_and_nonisolated_database_are_rejected(frozen, tmp_path):
    path, digest, _ = frozen
    with pytest.raises(ValueError, match='isolated temporary'):
        FixtureDispatchLedger(tmp_path / 'ledger.sqlite', path, digest)
    with tempfile.TemporaryDirectory(prefix='ac3-dispatch-test-') as temp:
        ledger = FixtureDispatchLedger(Path(temp) / 'ledger.sqlite', path, digest)
        with pytest.raises(ValueError, match='fixture provider'):
            ledger.dispatch('request', next(iter(ledger._plan())), object())
