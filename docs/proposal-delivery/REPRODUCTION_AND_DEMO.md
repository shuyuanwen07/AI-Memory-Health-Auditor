# Reproduction and demonstration checklist

## Clean source archive

1. Review the approved source/data list and any team or data-use permissions.
2. From the repository root, create the assessed-source archive:

   ```sh
   python3 scripts/package_assessment_source.py --output output/proposal-delivery/source
   ```

3. Retain `source-manifest.json` with the archive SHA and per-file SHA values.
4. Extract into a new temporary directory. Compare the archive manifest with its contents; confirm `.env`, databases, `.git`, local outputs, the Owner A custodian directory, and user reviewer files are absent. Publicly tracked Owner A/B/C handoff summaries are allowlisted; Owner A's own README says its labels are AI-assisted, and the Owner C raw archive stays local.
5. Copy `.env.example` to `.env`, then explicitly set `PIPELINE_PROVIDER=rule_based` and `EVALUATOR_PROVIDER=rule_based` for an offline start; the example file defaults both to OpenRouter and leaves the key blank. Keep `TARGET_MEMORY_WRITER=rule_based`, and select the local rule-based target in the UI. Use a new database and a unique Compose project name. Do not point to the operator's existing database. The app/API starting points are `http://localhost:5173` and `http://localhost:8000/api/v1/docs` when those ports are available.
6. For this snapshot, the isolated clean start used Python 3.12.16, Node 22.22.2/npm 10.9.7, PostgreSQL 16, FastAPI 0.115.6, SQLAlchemy 2.0.36, and psycopg 3.2.3. Alembic reached `0038_benchmark_plans`; `/api/v1/health` returned 200; the production frontend build/typecheck passed; and the focused New Audit workflow suite passed 39/39. The exact source archive hash and file hashes are in the adjacent `source-manifest.json`. A successful package check is not proof of model-backed experiment validity.

Do not run `scripts/run_presentation_demo.py --execute` during a no-cost demo: its documentation states that execution sends model requests. At the time of the 27 October 2026 verification, the existing workstation database contained presentation group `EXPD9C66FE3D5F946998AF5A8A0A3B272C9`; this is a local historical observation, not a property of the source archive or a guarantee that another database has the group. The database is deliberately excluded from the source archive, so a clean archive extraction will not contain it. A JSON report by itself does not recreate the database-backed group. If the original group is unavailable, use the bundled synthetic presentation conversation in the ordinary offline rule-based workflow, mark the run as a new illustrative demo, and do not report it as a reproduction of the historical experiment.

## Demo path and fallback

1. Explain the data source and ask the operator to authorise processing.
2. Show source messages alongside candidate memories and relationships. Identify edits and unresolved facts; do not present curated fixture inventories as independent labels.
3. Configure the target and budget. Explain whether calls go to a cloud provider or remain local/rule-based before submitting.
4. Review generated questions for source support and dimension coverage. Show the coverage warning and remedy when a dimension lacks distinct supporting evidence.
5. Run only under an approved service/budget. In an offline demonstration, use the rule-based target and label the resulting data as illustrative engineering output.
6. Open one result and trace its source, ground truth, question, expected behaviour, answer, evaluation, and uncertainty.
7. Export JSON and CSV; compare the same run and response in both exports.
8. Explain that target memory score and Auditor judgement accuracy are separate outcomes. Report unmeasured dimensions as unmeasured.

## Final release record

- Source revision and clean/modified status: remote `main` at `40876e47e44f2af18187766a46976fe3bb15c3a5`, plus the current modified working tree. The package is a local snapshot, not a commit or pushed release.
- Dependency versions and lock-file verification: verified in `CLEAN_START_VERIFICATION.md`; npm reported zero known vulnerabilities in its install audit.
- Isolated database migration and clean-start record: verified in `CLEAN_START_VERIFICATION.md`; test services and database volume were removed afterward.
- Current-running-app diagnosis-led retests: the three earlier-source Repair Comparison groups and nine run IDs are listed in `output/proposal-delivery/live-repair-loop-2026-10-28/manifest.json`; the current-source group `EXP627CCD21BC1D465996A30FF0E630739B` and three run IDs, reproduction bundle, paired metrics and review worksheet are listed in `output/proposal-delivery/live-current-source-repair-2026-10-28/manifest.json`. The latter binds to application digest `7d303324…` and the frozen eight-question suite. Both use one synthetic history and do not establish independent Auditor validity or generalisation. The separate 14-candidate intake retest remains at operator review before target testing.
- Latest source archive: 889 included members; the adjacent `output/proposal-delivery/source/source-manifest.json` records its archive and per-file hashes. This is a local package of the modified working tree, not a committed release.
- Phase 4 A/B/C experiment archive SHA-256 and member manifest: `research/evidence-20261027/manifest.json`. This is a separate research-evidence package, not part of the assessed-source ZIP; it includes reviewer names/outcome bindings and must not be distributed as a blind-review packet. The C grader-review sheet is separately prepared under `output/proposal-delivery/phase4-c-review-2026-10-28/`; only its CSV and instructions are reviewer-facing, while the private key stays local.
- Data, dependency, and citation approvals: human confirmation required; this checkout contains no `LICENSE` file. Do not interpret the source ZIP hash as proof of data-use permission, third-party licence compliance, or reviewer provenance.
- Team confirmation that AI-assisted handoff labels are never described as independent gold: required.
