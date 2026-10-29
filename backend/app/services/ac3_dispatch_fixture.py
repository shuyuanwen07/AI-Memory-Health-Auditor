"""Test-only locked dispatch integration; never calls any model or provider.

Only an in-memory SQLite database is accepted. Response rows are conspicuously
synthetic and disappear with that database. This has no endpoint and must not
be used to authorize paid or real execution.
"""
from sqlalchemy import select
from app.models import TestCaseModel, TargetResponseModel
from app.services.ac3_readiness import inspect_staged_ac3
from scripts.ac3_fixed_suite_adapter import sha


def exercise_locked_fixture_dispatch(db, frozen_path, frozen_sha256, reservation, history_conversations, history_runs):
    from app.api.routes import audit_run_locks
    bind = db.get_bind()
    if bind.url.get_backend_name() != 'sqlite' or bind.url.database not in (None, ':memory:'):
        raise ValueError('Fixture dispatch is restricted to an in-memory SQLite database')
    if db.in_transaction() or db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean idle test session')
    if not isinstance(history_runs, dict) or set(history_runs) != set(history_conversations):
        raise ValueError('Every history must have a mapped audit')
    ids = list(history_runs.values())
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('Audit identifiers must be distinct')
    scopes = sorted(set(ids) | {'suite:' + x for x in ids})
    with audit_run_locks(scopes, db=db):
        db.expire_all()
        with db.begin():
            # Frozen source, review, configuration, tests and memory are all
            # checked again after acquiring the same in-process audit locks.
            observation = inspect_staged_ac3(db, frozen_path, frozen_sha256, reservation, history_conversations, history_runs)
            rows = list(db.scalars(select(TestCaseModel).where(TestCaseModel.run_id.in_(ids)).order_by(TestCaseModel.id)))
            if len(rows) != observation['eligible_question_count']:
                raise ValueError('Test count changed during fixture dispatch')
            for test in rows:
                run = test.run_id
                db.add(TargetResponseModel(id='FX' + sha((frozen_sha256 + '|' + test.id).encode())[:32].upper(),
                    test_id=test.id, run_id=run, response_text='[SYNTHETIC TEST RESPONSE]', model='FIXTURE-NO-MODEL',
                    temperature=0, execution_metadata={'synthetic_fixture': True, 'provider_called': False}))
            db.flush()
    return {'format': 'ac3-locked-fixture-dispatch-v1', 'synthetic_only': True,
            'responses_written_in_memory': len(rows), 'provider_called': False,
            'real_execution_authorized': False}
