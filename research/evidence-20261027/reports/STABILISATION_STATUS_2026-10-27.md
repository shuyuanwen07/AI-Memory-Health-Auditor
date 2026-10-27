# Stabilisation checkpoint — 27 October 2026

Scope: implementation, engineering verification and evidence. Final Report, Word and presentation files were not edited.

## Environment and pre-UI verification

- Python 3.12 virtual environment, PostgreSQL 16, FastAPI and React/Vite services start.
- Docker frontend native dependencies isolated from macOS host node_modules.
- Vite 8.3.5 / Vitest 5.0.5; frontend 580 passed, 1 skipped; build passed; npm audit 0 vulnerabilities (previous verification).
- Backend pre-UI fixes: 2688 passed, 8 skipped, 1 upstream Starlette deprecation warning. Log: artifacts/local/stabilisation-20261027/backend-full-final-corrected.log.
- PostgreSQL migration/integration verification: 8 passed (previous verification).

## Original user-operated cloud smoke

Run RUN42A5007CD4544156BF15A4E86BE02D70 completed with OpenRouter openai/gpt-6-luna and weak_first_hit. Original inputs, memories, tests, responses, evaluations and retrieval traces are saved in artifacts/local/stabilisation-20261027/ui-smoke-original/; verification.json records hashes and consistency checks.

Results: 3/4 passed (75% micro rate). Displayed 66.7% is the macro average of Accuracy 100%, Freshness 0%, Conflict Resolution 100%. Appropriate Use was not tested. Exported evaluations match the result endpoint and screenshot totals. This is a connectivity/operational smoke, not a valid four-dimension evaluation or evidence of improvement.

Confirmed defects/limitations:

1. Conflict question was based on a false relationship between frontend TypeScript and an instruction separating food from technical work. Its project name was incorrectly inferred as “Or”. Its automated pass cannot establish conflict-resolution ability.
2. Regeneration silently returned the same question, creating a review loop.
3. Freshness target explicitly lacked the database answer. The trace shows weak_first_hit selected the instruction to keep project names rather than the database state. The failure is real for this question; the evaluator explanation mentioning only “backend” is inadequate diagnosis.
4. Ground truth still contains a false UPDATE from a SQLite tutorial mention to “none of that was a database change”. Missing contextual override links prevented Appropriate Use coverage.

## New post-UI fixes

- Regeneration now rejects an unchanged candidate with an actionable error and preserves the review decision. Regression verifies no mutation on this failure.
- Quality validator v24 rejects known cross-topic UPDATE/CONFLICT endpoints and the observed food/technical-separation relationship.
- Named-project filtering excludes conjunctions “or” and “and”.
- Synchronisation tests use a genuinely changed replacement fixture; runtime-freeze test verifies a no-op remains refused after runtime recovery. No production evidence or original score was overwritten.

Post-UI full regression: 2691 passed, 8 skipped, 1 upstream deprecation warning in 71.97 seconds. Log: artifacts/local/stabilisation-20261027/backend-post-ui-fixes-final.log. The initial post-UI run exposed three legacy contracts expecting successful identical regeneration (3 failed, 2688 passed, 8 skipped); that log is retained. Targeted updated contracts passed (22 tests), quality/regeneration suite passed (49 tests).

## Evaluator development replay

Version 61 versus version 62 replay of the same nine saved answers: one verdict changed, A019-T002, from pass to fail. It now detects missing required grayscale charts and agrees with the saved adjudication. Script and raw outputs: artifacts/local/stabilisation-20261027/replay_saved_development_answers.py and development-evaluator-replay.json. No target calls were made. These are previously inspected development cases; independent human label provenance is unverified. Do not claim held-out performance or independent failure recall from this replay.

## Phase completion and remaining work

Phase 1 verified before the post-UI changes; latest regression must remain green. Phase 2 is PARTIAL: upload-to-report and matching JSON export verified, but the requested valid four-dimension Weak/Strong workflow is not complete. Phase 3 has bounded evaluator and quality fixes with development regressions, not a validated Strong improvement. Phase 4 A/B/C NOT COMPLETED: no new formal baseline or repeated Weak/Strong comparison, no official paired LongMemEval comparison, no independent human reliability study. Historical Release20/Harbour raw evidence remains missing; summaries are not reconstructed.

Priority: repair extraction/relationship provenance, regenerate a valid four-dimension suite; verify cloud Weak/Strong under a frozen comparable protocol; improve failure explanations and conflict scoring; then execute A/B and official-compatible C where data and human references permit. Preserve the US$5 cloud budget; this checkpoint made no new model requests.


## Later checkpoint

Phase 1/2 completion was subsequently verified in PHASE_1_2_COMPLETION_2026-10-27.md. The partial status and original run results above are retained as historical observations.


Phase 3 targeted implementation and bounded verification subsequently completed; see PHASE_3_COMPLETION_2026-10-27.md for the exact scope, retained validation limitations and evidence.
