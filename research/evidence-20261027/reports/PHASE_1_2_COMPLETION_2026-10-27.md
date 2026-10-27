# Phase 1 and Phase 2 — completion record

Date: 27 October 2026 (Australia/Sydney). Scope: current-code engineering acceptance, not a formal research evaluation. Final Report, Word and presentation materials were not changed.

## Completion decision

**Phase 1 COMPLETE. Phase 2 COMPLETE for the specified engineering workflow and critical functional checks.** Completion does not mean every possible input is supported or that independent research reliability has been established. Phase 3 and formal Phase 4 experiments are outside this completion decision.

## Phase 1 — actual environment and verification

Container runtime: Python 3.12.15, FastAPI 0.115.6, SQLAlchemy 2.0.36, Pydantic 2.10.3; Node 22.22.2, npm 10.9.7, PostgreSQL 16.15. Host backend test venv uses Python 3.12.14. Vite 8.3.5, Vitest 5.0.5.

The earlier frontend native-binding startup issue came from sharing host node_modules with the Linux container. docker-compose.yml now uses a separate named frontend_node_modules volume. Dependency lockfile was updated; npm audit reports zero vulnerabilities. Services are loopback-bound and PostgreSQL stays inside the Compose network.

Environment checks: .env is ignored and untracked. API key, database and pipeline/writer configuration match the container runtime by hash comparison; their settings are documented in .env.example. Actual values are not included in the verification output. Scanning this turn's saved text evidence found zero occurrences of the configured key.

| Verification | Final result | Evidence under artifacts/local/phase12-20261027/ |
|---|---|---|
| Complete backend offline suite | 2699 passed, 8 PostgreSQL-only skips, 1 upstream Starlette deprecation warning | backend-final.log |
| All skipped PostgreSQL fixtures, separately on migrated isolated test DB | 8 passed, 1 upstream deprecation warning | postgresql-final.log |
| Frontend typecheck and production build | passed | frontend-full.log |
| Complete frontend suite in Linux | 581 passed, 62 files, zero skipped | frontend-full.log |
| Engineering script tests | 25 passed | script-tests.log |
| Dependency audit | zero vulnerabilities | npm-audit.json |
| Whitespace/patch check | git diff --check passed | final source checks |

The skips do not conceal unexecuted tests: all eight are gated by database isolation in the offline harness and all eight were executed separately against memory_auditor_stabilisation_20261027_test. The earlier frontend proxy-port skip also executed successfully in the final Linux frontend suite. The application PostgreSQL database was not used for integration fixture cleanup.

Commands:

```sh
.venv/bin/python scripts/run_offline_backend_tests.py --evidence-dir artifacts/local/phase12-offline-final
docker compose exec -T frontend npm run check
docker compose exec -T frontend npm audit --json
# Isolated test DATABASE_URL override, pipeline/evaluator rule_based:
docker compose exec -T -e DATABASE_URL=postgresql+psycopg://auditor:auditor@db:5432/memory_auditor_stabilisation_20261027_test -e PIPELINE_PROVIDER=rule_based -e EVALUATOR_PROVIDER=rule_based backend sh -c 'alembic upgrade head && python -m pytest -q tests/test_postgresql_api_smoke.py'
.venv/bin/python -m pytest scripts/tests -q
```

The database credentials shown above are the repository's disposable local Compose test defaults, not provider credentials.

## Phase 2 — full actual workflow

Source: datasets/smoke/qwen-four-dimension-source-v1.json, SHA256 e84fb0e564c7439ce3edf0fc6ebf7b25a681c9bb9dd209b1b97eb5d5d8a7d406. Eight synthetic user messages, no participant data. The existing exact-source approval is reused only as synthetic engineering review; it is not independent human gold.

The supported live API uploaded a new history to the actual PostgreSQL application; ran deterministic extraction; saved extracted candidates; reviewed/corrected the inventory through supported reject/add/relationship/confirm controls; froze a shared four-question suite; initialized actual controlled-memory targets; executed OpenRouter responses; evaluated; displayed Dashboard/report/failure details in Safari; and exported both browser CSV/JSON and backend bundles. Prior runs and scores remain intact.

Final experiment: EXP516FBF1D71F14F1C9E64893547F2FCAE.

| Condition | Run ID | Accuracy | Freshness | Conflict | Appropriate use | Macro score | Pass / fail / uncertain |
|---|---|---:|---:|---:|---:|---:|---|
| Weak | RUNBB911DBBD52D45F4A0D05CAD37B4D098 | 100% | 0% | 0% | 0% | 25% | 1 / 3 / 0 |
| Strong | RUND6DDD016CBF844BBAE9C6748F6B22BC5 | 100% | 100% | 100% | 100% | 100% | 4 / 0 / 0 |

One question per dimension per condition, one run per condition. Same GPT-6 Luna model, approved source history, questions, evaluator v63, memory capacity 50, retrieval ceiling 50, context budget 16000 characters, output limit 2048 tokens. Append-only retention preserves historical states; weak_first_hit versus strong_rule_based changes retrieval, and Weak/Strong target instructions differ as recorded. Strong receives more context by design. Configured temperature is 0, but Luna uses model-default sampling; no seed was sent or reproducibility of exact answers promised. No auxiliary model calls were enabled. Runtime versions: controlled-memory-v35, target-memory-policy-v42, rule extractor v26, rule test generator v27, quality validator v24.

These are engineering smoke results and must not be reported as a held-out repeated Weak/Strong experiment, effect size, independent failure-detection recall, or general performance estimate.

### Critical requirements and evidence

| Requirement | Verification |
|---|---|
| Obsolete values not treated as current | Strong actually answers PostgreSQL and explicitly replaces MySQL; weak's missing current evidence is retained as a failure. Supersession/append-only tests passed. |
| UPDATE vs CONFLICT | Reviewed source has UPDATE database pair, unresolved North/South CONFLICT and Java/Python CONTEXTUAL_OVERRIDE. Strong actually identifies North vs South and asks which controls. Relationship isolation/lifecycle regressions passed. |
| Target store separate from auditor gold | Independent target ingestion and delivery receipts persisted. test_target_ground_truth_isolation.py and test_target_context_isolation.py passed. |
| Expected answer not leaked | Eight exact request bodies recovered from source-derived delivered IDs and frozen templates; all match original wire payload SHA256. No expected_behavior is interpolated. Payloads contain target-owned source excerpts, not auditor-only answers. |
| Weak/Strong settings applied | Stored configurations, per-answer sent memory IDs, instructions and input hashes verified; same base model and budgets. |
| PASS/FAIL/UNCERTAIN | Live workflow includes pass and fail; uncertainty and truncated-output integration fixtures passed without scoring them as failures. No live uncertain answer was fabricated. |
| Score denominators | Four equal dimensions in live results; uncertainty/excluded/unassessed denominator contracts passed in test_quality_workflows.py and test_score_evidence_consistency.py. |
| Dashboard / persisted evaluations / exports agree | Safari shows final Strong 100%, Weak 25%; failure panel includes actual response and source evidence. Dashboard shows 5 complete reports, 0 unfinished and 0 interrupted. Browser and API CSV/JSON match evaluation IDs, outcomes and scores. |
| Interrupted calls / retries | test_audit_execution_service.py verifies partial execution reuses saved answers, partial evaluation reuses responses, provider failure does not suppress peer conditions, and cancellation is terminal. Runtime freeze, creation recovery and execution coverage tests passed. These are controlled failure-injection tests, not claims that the live provider failed. |
| Model identity / effective generation settings | Eight actual responses identify openai/gpt-6-luna, with request contract, finish status, provider routing, attempt count, token usage and delivery hashes. |

Browser JSON deliberately sanitizes target_memory_profile from result.reproducibility and exports a sanitized configuration separately. The verifier accounts only for that documented difference; the remaining result object is equal. Browser CSV answer IDs and pass/fail outcomes match stored evaluations exactly.

### Confirmed defects fixed

1. Shared host/container native frontend dependencies: separate Linux node_modules volume.
2. Offline test script could not import repo scripts on direct invocation: explicit repo-root sys.path.
3. Qualified mandatory values lost by evaluator: preserve concrete qualifiers, with conservative uncertainty for generic requirements (earlier v62 repair).
4. Regeneration silently repeated the same test and reset review: now returns an actionable 422 without changing saved decisions.
5. Cross-topic/food separation relationships accepted as valid test evidence: reject them in quality checks.
6. “or”, “and”, “Both” and capstone/frontend modifiers produced false project labels: bounded entity parsing fixes, four modifier regressions.
7. Signed client brief's explicit South region was omitted from target extraction: source-derived deployment-region facts are retained and differing region values remain conflicts.
8. Unresolved-reference status became an answerless accuracy question: omit this status-only candidate from scalar probes.
9. Correct migration answer failed because reference ended in “there”: recognize the explicitly migrated-to database, and reject an obsolete MySQL answer.
10. Conflict answer could pass while omitting a known region: require both source-region options before awarding the conflict pass.

New targeted regressions are in backend/tests/test_phase12_live_regressions.py, test_test_quality_and_baselines.py and test_single_question_regeneration.py. Existing synchronization tests now use a genuinely changed replacement fixture rather than assert that identical regeneration succeeds. Existing runtime drift assertions remain intact.

## Evidence, cost and reproducibility

Main directory: artifacts/local/phase12-20261027/final/.

- input.json: original authorized synthetic input.
- live-verification.json: live API request/response receipts, reviewed inventory, configurations, frozen tests, actual target answers, evaluations, trace and diagnosis.
- verified-request-bodies.json: eight recovered wire payloads, accepted only after matching original payload hashes; no Authorization headers. Recovery is explicitly recorded, never presented as a second execution.
- bundle.json, conversation-export.json, results.csv: server exports.
- browser-report.json, browser-report.csv: actual files downloaded using the browser controls.
- verification.json: export consistency, request hashes, token usage and file fingerprints.
- ui-verification.json, environment-verification.json, credential-scan.json, source-manifest.json in parent directory: UI observations, safe environment checks and exact modified-source provenance.
- source-changes.patch and verified-source-changes.tar.gz: modified source snapshot, including new files, without .env or private database dump.

Reproduction commands (each prepare invocation needs a NEW output directory; execute sends real paid model calls):

```sh
python3 scripts/verify_phase12_live.py prepare --output artifacts/local/phase12-20261027/final
python3 scripts/verify_phase12_live.py execute --output artifacts/local/phase12-20261027/final
.venv/bin/python scripts/verify_phase12_evidence.py
```

Final eight target requests used 12,565 input tokens and 736 output tokens. At the checked standard listing of US$0.10/M input and US$0.50/M output, estimated cost is US$0.0016245, not an invoice. The preceding development workflow made eight additional target requests; all these calls remain far below the authorized US$5 budget. No formal experiment was charged or claimed. Source: https://openrouter.ai/openai/gpt-6-luna.

Base commit b44ced90ea39eb569eaa6ea01dee4c3df5712085, branch codex/owner-c-validation, working tree modified and uncommitted. Actual installed runtime signatures are frozen per run and modified-file hashes recorded; this is not falsely described as a clean committed release.

## Failures and limitations retained

- The first preparation script failed on HTTP 204 empty JSON parsing; script corrected and original partial record retained.
- A prepared pre-fix suite exposed more defects; its run and original 0%/50% results are preserved in attempt3, not overwritten. Obsolete unexecuted attempt2 was explicitly cancelled with evidence preserved.
- Initial targeted regression fixtures lacked required schema fields; these were corrected without relaxing product assertions.
- Earlier no-op regeneration contract failures are retained in the previous checkpoint logs.
- One upstream Starlette deprecation warning remains; no test failure remains. npm audit is zero.
- Rule extraction remains bounded and the ground truth review step remains necessary. Failure categories can remain unclassified when evidence does not establish a unique observed error; the UI states this. Independent human research validity, broad actor/semantic robustness, repeated experiments and LongMemEval ranking remain Phase 3/4 work.
