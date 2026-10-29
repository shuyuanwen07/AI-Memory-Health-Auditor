"""Only run on the explicitly identified, disposable test database."""
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.services.ac3_budget_test_models import BudgetTestBase, ResearchBudgetAccountModel
from app.services.ac3_budget_simulation import SimulatedLedger

URL = 'postgresql+psycopg://ac3_test:ac3_test_only@ac3-postgres-isolated-20261028:5432/ac3_test'
pytestmark = pytest.mark.skipif(os.environ.get('AC3_DISPOSABLE_POSTGRES_TEST') != 'yes', reason='Requires disposable PostgreSQL')
FROZEN = 'a' * 64
REQUEST = 'b' * 64

@pytest.fixture
def ledger():
    engine = create_engine(URL, pool_size=12)
    BudgetTestBase.metadata.drop_all(engine)
    BudgetTestBase.metadata.create_all(engine)
    value = SimulatedLedger(engine)
    value.create(FROZEN, 400_000_000, 379_770_200, 20_229_800, 5_000_000)
    yield value
    engine.dispose()


def test_concurrent_reservations_never_overallocate(ledger):
    def reserve(i):
        try:
            return ledger.reserve(FROZEN, str(i), REQUEST)
        except ValueError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=10) as pool:
        result = list(pool.map(reserve, range(10)))
    assert result.count('reserved') == 4
    assert result.count('blocked') == 6
    with Session(ledger.engine) as db:
        account = db.scalar(select(ResearchBudgetAccountModel))
        assert account.reserved_nusd == 20_000_000


def test_identity_and_dispatch_only_once(ledger):
    assert ledger.reserve(FROZEN, 'x', REQUEST) == 'reserved'
    assert ledger.reserve(FROZEN, 'x', REQUEST) == 'reserved'
    with pytest.raises(ValueError):
        ledger.reserve(FROZEN, 'x', 'c' * 64)
    def dispatch(_):
        try:
            return ledger.transition(FROZEN, 'x', 'dispatch')
        except ValueError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=5) as pool:
        result = list(pool.map(dispatch, range(5)))
    assert result.count('dispatched') == 1
    assert result.count('blocked') == 4
    assert ledger.transition(FROZEN, 'x', 'settle', actual=1_000_000, receipt_sha='d' * 64) == 'settled'
    with Session(ledger.engine) as db:
        account = db.scalar(select(ResearchBudgetAccountModel))
        assert account.spent_nusd == 380_770_200
        assert account.reserved_nusd == 0


def test_uncertain_and_overrun_fail_closed(ledger):
    ledger.reserve(FROZEN, 'x', REQUEST)
    ledger.transition(FROZEN, 'x', 'dispatch')
    ledger.transition(FROZEN, 'x', 'uncertain')
    with pytest.raises(ValueError):
        ledger.reserve(FROZEN, 'y', REQUEST)
    with Session(ledger.engine) as db:
        account = db.scalar(select(ResearchBudgetAccountModel))
        assert account.reserved_nusd == 5_000_000
    with pytest.raises(ValueError):
        ledger.transition(FROZEN, 'x', 'cancel')


def test_overrun_commits_and_suspends(ledger):
    ledger.reserve(FROZEN, 'x', REQUEST)
    ledger.transition(FROZEN, 'x', 'dispatch')
    ledger.transition(FROZEN, 'x', 'settle', actual=6_000_000, receipt_sha='d' * 64)
    with pytest.raises(ValueError):
        ledger.reserve(FROZEN, 'y', REQUEST)
    with Session(ledger.engine) as db:
        account = db.scalar(select(ResearchBudgetAccountModel))
        assert account.state == 'overrun'
        assert account.spent_nusd == 385_770_200


def test_refuses_any_other_database():
    engine = create_engine('sqlite:///:memory:')
    with pytest.raises(ValueError):
        SimulatedLedger(engine)
