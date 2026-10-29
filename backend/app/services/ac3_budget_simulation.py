"""Disposable PostgreSQL budget-ledger experiment. NEVER authorizes execution.

This module deliberately refuses every database except the named disposable
container. It does not validate reviewed suites, authenticate provider receipts,
or integrate with model transport. It must not be used as a production guard.
Amounts are integer billionths of a USD.
"""
import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.ac3_budget_test_models import ResearchBudgetAccountModel, ResearchBudgetReservationModel

_TEST_HOST = 'ac3-postgres-isolated-20261028'
_HEX = re.compile(r'^[0-9a-f]{64}$')
_MAX = 2**63 - 1


def _amount(value, *, positive=False):
    if type(value) is not int or value < int(positive) or value > _MAX:
        raise ValueError('invalid integer nano-dollar amount')
    return value


class SimulatedLedger:
    def __init__(self, engine):
        url = engine.url
        if (url.get_backend_name(), url.host, url.database, url.username) != ('postgresql', _TEST_HOST, 'ac3_test', 'ac3_test'):
            raise ValueError('ledger simulation requires the disposable test database')
        self.engine = engine

    def create(self, frozen_sha, cap, initial, maximum, ceiling):
        if not _HEX.fullmatch(frozen_sha):
            raise ValueError('invalid suite digest')
        cap, initial, maximum, ceiling = (_amount(cap, positive=True), _amount(initial), _amount(maximum), _amount(ceiling, positive=True))
        if initial > cap or maximum > cap - initial:
            raise ValueError('invalid configured cap')
        with Session(self.engine) as db, db.begin():
            db.add(ResearchBudgetAccountModel(id='disposable-test-only', frozen_sha256=frozen_sha,
                cap_nusd=cap, initial_nusd=initial, max_new_nusd=maximum, request_ceiling_nusd=ceiling,
                spent_nusd=initial, reserved_nusd=0, state='active'))

    def _account(self, db, frozen_sha):
        row = db.scalar(select(ResearchBudgetAccountModel).where(ResearchBudgetAccountModel.id == 'disposable-test-only').with_for_update())
        if row is None or row.frozen_sha256 != frozen_sha:
            raise ValueError('unknown budget or suite digest')
        return row

    def reserve(self, frozen_sha, key, request_sha):
        if not isinstance(key, str) or not 0 < len(key) <= 120 or not _HEX.fullmatch(request_sha):
            raise ValueError('invalid request identity')
        with Session(self.engine) as db, db.begin():
            account = self._account(db, frozen_sha)
            existing = db.scalar(select(ResearchBudgetReservationModel).where(ResearchBudgetReservationModel.account_id == account.id, ResearchBudgetReservationModel.request_key == key))
            if existing:
                if existing.request_sha256 != request_sha:
                    raise ValueError('request identity changed')
                return existing.state
            if account.state != 'active':
                raise ValueError('budget suspended')
            amount = account.request_ceiling_nusd
            if amount > account.cap_nusd - account.spent_nusd - account.reserved_nusd or amount > account.max_new_nusd - (account.spent_nusd - account.initial_nusd) - account.reserved_nusd:
                raise ValueError('budget limit reached')
            account.reserved_nusd += amount
            db.add(ResearchBudgetReservationModel(id=hashlib.sha256((account.id + '\0' + key).encode()).hexdigest(), account_id=account.id,
                request_key=key, request_sha256=request_sha, reserved_nusd=amount, state='reserved'))
            return 'reserved'

    def transition(self, frozen_sha, key, operation, *, actual=None, receipt_sha=None):
        with Session(self.engine) as db, db.begin():
            account = self._account(db, frozen_sha)
            row = db.scalar(select(ResearchBudgetReservationModel).where(ResearchBudgetReservationModel.account_id == account.id, ResearchBudgetReservationModel.request_key == key))
            if row is None:
                raise ValueError('unknown reservation')
            if operation == 'dispatch' and row.state == 'reserved' and account.state == 'active':
                row.state = 'dispatched'
            elif operation == 'cancel' and row.state == 'reserved':
                row.state = 'cancelled'
                account.reserved_nusd -= row.reserved_nusd
            elif operation == 'uncertain' and row.state == 'dispatched':
                row.state = 'uncertain'
                account.state = 'uncertain'
            elif operation == 'settle' and row.state == 'dispatched':
                _amount(actual)
                if not isinstance(receipt_sha, str) or not _HEX.fullmatch(receipt_sha):
                    raise ValueError('invalid receipt digest')
                if actual > _MAX - account.spent_nusd:
                    raise ValueError('actual cost exceeds representable amount; reservation remains held')
                account.reserved_nusd -= row.reserved_nusd
                account.spent_nusd += actual
                row.actual_nusd, row.receipt_sha256 = actual, receipt_sha
                row.state = 'settled'
                if actual > row.reserved_nusd or account.spent_nusd > account.cap_nusd or account.spent_nusd - account.initial_nusd > account.max_new_nusd:
                    account.state = 'overrun'
            else:
                raise ValueError('invalid or duplicate transition')
            return row.state
