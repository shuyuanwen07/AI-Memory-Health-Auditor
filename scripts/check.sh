#!/usr/bin/env sh
# One portable repository-level command for the offline CI-quality checks.
set -eu

(cd backend && sh scripts/check.sh)
(cd frontend && npm run check)
python -m unittest discover -s scripts/tests -q
