"""Cross-process stage coordination for persistent non-PostgreSQL databases."""
from multiprocessing import get_context
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import Base
from app.services.stage_lock import database_stage_busy, database_stage_lock


def _try_database_stage_lock(database_path: str, scope: str, result_queue) -> None:
    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as db:
        try:
            with database_stage_lock(db, scope, "This stage is already running."):
                result_queue.put("acquired")
        except HTTPException as exc:
            result_queue.put(exc.status_code)
    engine.dispose()


def test_file_backed_sqlite_stage_lease_blocks_another_process_and_releases(tmp_path):
    database_path = Path(tmp_path) / "stage-lock.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    context = get_context("spawn")
    result_queue = context.Queue()
    scope = "extraction:synthetic-conversation"

    with Session(engine) as db:
        with database_stage_lock(db, scope, "This stage is already running."):
            worker = context.Process(target=_try_database_stage_lock, args=(str(database_path), scope, result_queue))
            worker.start()
            worker.join(timeout=10)
            assert not worker.is_alive(), "the competing worker should fail promptly rather than wait"
            assert worker.exitcode == 0
            assert result_queue.get(timeout=2) == 409
        assert database_stage_busy(db, scope) is False

    engine.dispose()
