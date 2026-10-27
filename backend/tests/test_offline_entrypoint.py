"""The isolated test entry works without a caller-supplied import path."""
import os
from pathlib import Path
import subprocess
import sys


def test_direct_offline_entry_collects_repository_script_contracts(tmp_path):
    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    result = subprocess.run(
        [sys.executable, str(root / 'scripts/run_offline_backend_tests.py'),
         '--backend-root', str(root / 'backend'), '--evidence-dir', str(tmp_path / 'evidence'),
         '--', '--collect-only', '-q', 'tests/test_reliability_review_pack.py'],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'test_reliability_review_pack.py::' in result.stdout
    assert 'ISOLATION_EVIDENCE' in result.stdout
