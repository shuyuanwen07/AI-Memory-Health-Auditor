"""Isolated AC3 provider-dispatch recovery experiment, never real transport.

The provider protocol is deliberately restricted to the local fixture class;
this module is not wired into the app, cannot bill, and cannot use its database.
A real provider adapter, verified budget reservations and authentication remain
necessary before any formal execution. Database rows contain synthetic data.
"""
from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Protocol

from scripts.ac3_fixed_suite_adapter import compile_mock


class ProviderInterface(Protocol):
    def respond(self, question: str) -> str: ...


@dataclass
class FixtureProvider:
    response: str = '[SYNTHETIC RESPONSE: NO PROVIDER CALLED]'
    calls: int = 0
    fail: bool = False

    def respond(self, question: str) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError('synthetic provider failure')
        return self.response


class FixtureDispatchLedger:
    """Durable state transitions over a purposely isolated temporary SQLite file."""
    def __init__(self, path, frozen_path, frozen_sha256, reservation='0'):
        path = Path(path)
        root = Path(tempfile.gettempdir()).resolve()
        directory = path.parent
        if (path.name != 'ledger.sqlite' or directory.is_symlink() or path.is_symlink()
                or directory.resolve().parent != root or not directory.name.startswith('ac3-dispatch-test-')
                or not directory.is_dir()):
            raise ValueError('Only an isolated temporary test database is permitted')
        self.path = path
        self.frozen_path, self.frozen_sha256, self.reservation = frozen_path, frozen_sha256, reservation
        # Validate the actual frozen package before creating an isolated ledger.
        self._plan()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600) if not path.exists() else None
        if fd is not None: os.close(fd)
        with self._connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS requests (request_key TEXT PRIMARY KEY, frozen_sha TEXT NOT NULL, test_id TEXT NOT NULL, request_sha TEXT NOT NULL, state TEXT NOT NULL, response TEXT, error TEXT)')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            yield connection
        finally:
            connection.close()

    def _plan(self):
        stage = compile_mock(self.frozen_path, self.frozen_sha256, self.reservation)
        return {item['test_id']: item for item in stage['items'] if item['grounding_review'] == 'valid'}

    def dispatch(self, request_key, test_id, provider):
        if type(provider) is not FixtureProvider:
            raise ValueError('Only the local fixture provider is supported')
        if not isinstance(request_key, str) or not 0 < len(request_key) <= 120:
            raise ValueError('Invalid request identity')
        plan = self._plan()
        if test_id not in plan:
            raise ValueError('Question not eligible in the frozen suite')
        question = plan[test_id]['question']
        request_sha = hashlib.sha256(json.dumps({'frozen_sha256': self.frozen_sha256, 'test_id': test_id, 'question': question}, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT frozen_sha, test_id, request_sha, state, response FROM requests WHERE request_key = ?', (request_key,)).fetchone()
            if row:
                if row[:3] != (self.frozen_sha256, test_id, request_sha):
                    raise ValueError('Request key was previously bound to another request')
                if row[3] == 'settled':
                    con.commit()
                    return {'state': 'settled', 'response': row[4], 'duplicate': True, 'synthetic_only': True}
                raise ValueError('Previous dispatch is unresolved; do not retry')
            # Durable before dispatch: a crash after commit is treated as unknown.
            con.execute('INSERT INTO requests VALUES (?, ?, ?, ?, ?, NULL, NULL)', (request_key, self.frozen_sha256, test_id, request_sha, 'dispatched'))
            con.commit()
        try:
            # Validate again after durable pre-dispatch record. If sources changed,
            # fail closed and retain an unresolved reservation; never send.
            self._plan()
            response = provider.respond(question)
            if not isinstance(response, str) or not response.strip():
                raise ValueError('Invalid fixture response')
        except Exception:
            with self._connect() as con:
                con.execute('UPDATE requests SET state = ?, error = ? WHERE request_key = ? AND state = ?', ('unknown', 'fixture dispatch failed; no retry', request_key, 'dispatched'))
            raise
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            updated = con.execute('UPDATE requests SET state = ?, response = ? WHERE request_key = ? AND state = ?', ('settled', response, request_key, 'dispatched')).rowcount
            if updated != 1:
                raise ValueError('Unexpected request state; no retry')
            con.commit()
        return {'state': 'settled', 'response': response, 'duplicate': False, 'synthetic_only': True}

    def inspect(self, request_key):
        with self._connect() as con:
            row = con.execute('SELECT state, response FROM requests WHERE request_key = ?', (request_key,)).fetchone()
        if not row: return None
        return {'state': 'unknown' if row[0] == 'dispatched' else row[0], 'response': row[1], 'synthetic_only': True}
