#!/usr/bin/env sh
# Keep the local backend quality command identical to the CI contract.
set -eu

python -m compileall -q app
ruff check app tests
# Service containers may inherit real provider credentials. Use the same
# isolated defaults and disposable database as the dedicated offline entry.
if [ -f ../scripts/run_offline_backend_tests.py ]; then
  auditor_offline_test_runner=../scripts/run_offline_backend_tests.py
elif [ -f /scripts/run_offline_backend_tests.py ]; then
  auditor_offline_test_runner=/scripts/run_offline_backend_tests.py
else
  echo "Cannot locate the isolated backend test entry." >&2
  exit 1
fi
PYTHONPATH=.:.. python "$auditor_offline_test_runner" -- -q
