"""Cross-process protection for long-running stages."""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
from threading import Event, Thread
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, insert, text, update
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.entities import StageLockModel


_LEASE_DURATION = timedelta(minutes=3)
_LEASE_REFRESH_INTERVAL_SECONDS = 30


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stage_lock_key(scope: str) -> int:
    return int.from_bytes(hashlib.sha256(('memory-auditor-stage:' + scope).encode()).digest()[:8], 'big', signed=True)


@contextmanager
def database_stage_locks(db: Session | None, scopes: list[str], busy_message: str):
    """Acquire distinct stage locks with one PostgreSQL connection.

    The single-connection form avoids exhausting the default connection pool
    when a research import locks multiple audits. Locks are nonblocking and
    share exactly the same keys as individual database_stage_lock calls.
    """
    ordered = sorted(set(scopes))
    if db is None:
        yield
        return
    if db.get_bind().dialect.name != 'postgresql':
        with ExitStack() as stack:
            for scope in ordered:
                stack.enter_context(database_stage_lock(db, scope, busy_message))
            yield
        return
    connection = db.get_bind().engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    acquired = []
    try:
        for scope in ordered:
            key = stage_lock_key(scope)
            if not connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}):
                raise HTTPException(409, busy_message)
            acquired.append(key)
        yield
    finally:
        try:
            for key in reversed(acquired):
                connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})
        except Exception:
            connection.invalidate()
        finally:
            connection.close()


@contextmanager
def database_stage_lock(db: Session | None, scope: str, busy_message: str):
    if db is None:
        yield
        return
    bind = db.get_bind()
    if bind.dialect.name != 'postgresql':
        # Independent in-memory SQLite databases do not share state between
        # workers. File-backed SQLite and other persistent stores use a short
        # renewable row lease, so a crashed worker cannot leave a permanent lock.
        database_name = str(bind.url.database or '')
        if bind.dialect.name == 'sqlite' and (
            database_name in {':memory:', ''} or 'mode=memory' in database_name
        ):
            yield
            return
        with _database_lease_lock(bind.engine, scope, busy_message):
            yield
        return
    # Separate session: answer receipts can commit without releasing protection.
    connection = db.get_bind().engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    key = stage_lock_key(scope)
    acquired = False
    try:
        acquired = bool(connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}))
        if not acquired:
            raise HTTPException(409, busy_message)
        yield
    finally:
        try:
            if acquired:
                connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})
        except Exception:
            # Never put a connection with an unconfirmed release back in the pool.
            connection.invalidate()
            raise
        finally:
            connection.close()


@contextmanager
def _database_lease_lock(engine, scope: str, busy_message: str):
    table = StageLockModel.__table__
    owner = uuid4().hex
    now = _utc_naive_now()
    try:
        # A unique primary key makes the claim atomic across processes. Remove
        # an abandoned claim only after its renewable lease has expired.
        with engine.begin() as connection:
            connection.execute(delete(table).where(
                table.c.scope == scope,
                table.c.lease_expires_at <= now,
            ))
            connection.execute(insert(table).values(
                scope=scope,
                owner_token=owner,
                lease_expires_at=now + _LEASE_DURATION,
            ))
    except IntegrityError as exc:
        raise HTTPException(409, busy_message) from exc
    except OperationalError as exc:
        if engine.dialect.name == 'sqlite' and any(term in str(exc).casefold() for term in ('locked', 'busy')):
            raise HTTPException(409, busy_message) from exc
        raise

    stop = Event()
    heartbeat = Thread(
        target=_refresh_database_lease,
        args=(engine, scope, owner, stop),
        name='audit-stage-lease-refresh',
        daemon=True,
    )
    heartbeat.start()
    try:
        yield
    finally:
        stop.set()
        heartbeat.join(timeout=2)
        try:
            with engine.begin() as connection:
                connection.execute(delete(table).where(
                    table.c.scope == scope,
                    table.c.owner_token == owner,
                ))
        except SQLAlchemyError:
            # If release cannot reach the database, the lease expiry is the
            # recovery path. Never mask the stage's original result/error.
            pass


def _refresh_database_lease(engine, scope: str, owner: str, stop: Event) -> None:
    table = StageLockModel.__table__
    while not stop.wait(_LEASE_REFRESH_INTERVAL_SECONDS):
        try:
            with engine.begin() as connection:
                renewed = connection.execute(update(table).where(
                    table.c.scope == scope,
                    table.c.owner_token == owner,
                ).values(lease_expires_at=_utc_naive_now() + _LEASE_DURATION))
                if renewed.rowcount != 1:
                    return
        except SQLAlchemyError:
            # Try again at the next interval. The lease bounds the time a
            # failed worker can exclude another request.
            continue


def database_stage_busy(db: Session, scope: str) -> bool:
    try:
        with database_stage_lock(db, scope, 'This audit stage is already running.'):
            return False
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        return True
