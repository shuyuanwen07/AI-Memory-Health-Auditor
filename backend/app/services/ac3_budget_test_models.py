"""Isolated metadata for the disposable budget simulation; never production schema."""
from datetime import datetime, timezone
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class BudgetTestBase(DeclarativeBase):
    pass

def utc_now():
    return datetime.now(timezone.utc)

class ResearchBudgetAccountModel(BudgetTestBase):
    """Durable, quarantined accounting prototype; never enables provider calls."""
    __tablename__ = 'research_budget_accounts'
    __table_args__ = (CheckConstraint('cap_nusd > 0 AND initial_nusd >= 0 AND spent_nusd >= 0 AND reserved_nusd >= 0 AND max_new_nusd >= 0 AND request_ceiling_nusd > 0', name='ck_research_budget_nonnegative'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    frozen_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cap_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    initial_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_new_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_ceiling_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ResearchBudgetReservationModel(BudgetTestBase):
    __tablename__ = 'research_budget_reservations'
    __table_args__ = (UniqueConstraint('account_id', 'request_key', name='uq_research_budget_request'),
                      CheckConstraint('reserved_nusd > 0 AND (actual_nusd IS NULL OR actual_nusd >= 0)', name='ck_research_budget_reservation_amount'))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('research_budget_accounts.id', ondelete='RESTRICT'), index=True)
    request_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_nusd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    receipt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

