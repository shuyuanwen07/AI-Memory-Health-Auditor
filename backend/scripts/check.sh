#!/usr/bin/env sh
# Keep the local backend quality command identical to the CI contract.
set -eu

python -m compileall -q app
ruff check app tests
PYTHONPATH=. pytest -q
