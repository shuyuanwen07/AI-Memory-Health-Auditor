"""Shared fixtures for tests that exercise saved audit workflows."""

import pytest


@pytest.fixture
def saved_suite(monkeypatch, tmp_path):
    # Reuse the established synthetic API fixture without duplicating its data
    # setup. Keeping the wrapper in conftest makes it available to all modules.
    from test_execution_coverage_gate import saved_suite as existing_fixture

    yield from existing_fixture.__wrapped__(monkeypatch, tmp_path)
