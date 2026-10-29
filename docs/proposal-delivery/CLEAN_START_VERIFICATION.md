# Isolated clean-start verification

**Date:** 27 October 2026 (Australia/Sydney)  
**Base revision:** `f9f777ee11813642e280ec1885ab8d867011ebdd`  
**Source state:** Modified working tree packaged with per-file hashes in `source-manifest.json`.

## Environment and result

The assessed-source ZIP was extracted to a new temporary directory and started with a unique Docker Compose project, `proposalclean20261027`, a new PostgreSQL volume, and alternate frontend port `15173`. The test configuration used rule-based pipeline/evaluation settings and blank cloud API keys. It did not connect to the existing project database or call any model.

- PostgreSQL 16 started healthy.
- Backend dependencies installed from the packaged requirements: Python 3.12.16, FastAPI 0.115.6, SQLAlchemy 2.0.36, and psycopg 3.2.3.
- Alembic reached head revision `0038_benchmark_plans` on the fresh database.
- `GET /api/v1/health` returned HTTP 200 with the database ready.
- Frontend dependencies installed from the included lockfile: Node 22.22.2 and npm 10.9.7; Vite 8.3.5 served the page.
- `npm run build` passed, including TypeScript type-checking. Vite emitted its existing large-bundle advisory.
- `npm test -- src/pages/NewAudit.workflow.test.tsx` passed all 39 tests. React printed existing `act(...)` warnings during one synthetic-example test.
- A separate focused Python run passed 46 package/evidence-inventory and Phase 4 review-gate tests; the local assisted return was rejected because it does not declare independent completion.
- In a later focused backend run, 2 API integration tests and 88 tests across eight targeted modules passed (90 total in those backend checks). These used a temporary SQLite test database, rule-based providers, and blank cloud API keys. The API cases covered an authorised audit workflow with private target context kept off the API, plus paired experiment history and CSV export. The additional modules covered operator access, conversation lifecycle/import, CSV export, trace/test review, evidence correspondence, experiment analytics, and score/evidence consistency. One Starlette deprecation warning was reported. This was a targeted test selection, not the full backend suite or a full model-backed audit.
- The browser rendered `/new-audit`. The synthetic presentation conversation was present, authorisation remained unchecked, and “Continue to Ground Truth” remained disabled. No conversation was submitted.

The isolated test services and their new database volume were removed after verification. The assessed-source archive and manifest remain in `output/proposal-delivery/source/`.

After this check, the delivery notes and the offline evidence-inventory script were updated before regenerating the final source archive. The application code, dependency lockfiles, and Compose files are identical to the clean-start snapshot; the final archive's manifest records every included file hash.

## Verification boundary

This proves that the packaged source can install, migrate a clean database, serve its frontend and backend, and pass the focused configuration-flow test in this local environment. It is not a full live end-to-end audit, a provider availability check, a semantic review of the synthetic answers, a security certification, or evidence that proposal Experiments A, B, or C passed. No current-version model-backed audit was executed.

The targeted backend tests provide additional engineering evidence for isolated API and evidence/export paths. They do not replace the final source-bound walkthrough, a complete regression suite, independent human labels, or the proposal's experiment-specific evidence. Docker daemon access was unavailable during the latest follow-up, so container health was not rechecked at that point; use the last successful clean-start health result above as historical verification only.

## Follow-up: remote evidence restore and review analysis — 28 October

After remote `main` advanced to `40876e47e44f2af18187766a46976fe3bb15c3a5`, the added Phase 4 archive was independently checked against its manifest: archive SHA-256, CRC, all 360 member hashes, and the 85,083,014-byte uncompressed total matched. All member paths were checked for traversal and existing destinations before restoring the files to their original locations.

The formal-review analyzer now preserves conflicting full-coverage/candidate-validity labels and marks only that coverage item unresolved, and accepts known-exposure names for a later recheck without editing frozen input packets. The full `scripts/tests` suite passed **75 tests**, including the updated analyzer and current-source tutor-repair evidence-inventory cases. Re-running the 216-item post-disagreement review yielded 32 unresolved items; the tool correctly reports it as not blind eligible and not formally ready. No model calls, app database writes, or changes to raw reviewer returns were made. See `docs/proposal-experiment-audit.md` and the local review analysis in `output/proposal-evaluation/`.

The assessed-source archive was then refreshed from the current modified working tree. It is separate from the experiment-evidence archive, which intentionally contains reviewer identity/outcome bindings and is unsuitable for blind-review distribution. This refresh does not constitute a new clean-start installation or full current-tree application test.

## Current working-tree verification — 28 October

After the current-source tutor replay and delivery edits, the complete frontend check passed: production typecheck/build and all **581 frontend tests** passed, with one test skipped. The build emitted a bundle-size advisory for a generated JavaScript chunk above 500 kB; this did not fail the build. The complete backend suite passed **2,749 tests**, with eight skipped. The project scripts suite passed **75 tests**. The diagnosis-led result was reopened in the running UI at `EXP627CCD21BC1D465996A30FF0E630739B`; its six shared decided questions show 1/6 baseline versus 3/6 targeted, while five of 24 labels remain uncertain across all conditions.

The assessed-source ZIP was rebuilt from the modified working tree and independently checked: **889 files**, ZIP CRC, embedded and external manifest agreement, and every per-file SHA-256 passed. The package excludes generated experiment outputs and private review keys. The evidence inventory has 76 of 77 expected records; the only missing path is the unrecoverable historical `artifacts/local/owner-c-heldout-v1/results.json`. This does not replace the separately preserved later Phase 4 C ranking comparison. `git diff --check`, the current-source repair/review packet hashes, and local Markdown links also passed. The running application was already in service for the UI check; this was not a fresh database migration or isolated clean-start run.

## Follow-up: in-system diagnosis-led repair retest — 28 October

The local app completed three paired **Repair Comparison** groups using the fictional Harbour history and the same four-question suite. Each compared the saved first-match baseline, a generic instruction control, and the targeted `scope_aware` / “Match the task and project” retrieval setting, with OpenRouter `openai/gpt-6-luna` as target and evaluator. The diagnosis record first requested an answer-time memory-receipt check; inspecting the baseline receipt confirmed that the retired MySQL record was supplied while the stored PostgreSQL update was omitted. The intervention then changed retrieval policy only.

Across the three groups, the baseline and generic control each passed 3/12 answers. The targeted condition passed 9/9 decided answers; three of its 12 answers remain uncertain. All three targeted Freshness receipts show both MySQL history and the current PostgreSQL update supplied. The results use one history and repeated questions; they are exploratory and the assessments are not independent human labels. The app group/run IDs, complete reproduction JSON exports, answer-time receipts, and file hashes are in `output/proposal-delivery/live-repair-loop-2026-10-28/manifest.json`. A 36-answer blinded review worksheet is also prepared; no human return has been received.

This is a real model-backed in-system loop, not a clean-start run of a frozen release. Provider sampling remained model-default despite a recorded temperature and seed. No claim of formal A/B/C acceptance or independent Auditor validity follows from this experiment.

## Follow-up: current-source diagnosis-led retest — 28 October

The current app then repeated the tutor loop under the delivered application digest `7d3033246fffc2d774f282f9e60c6ed6cd85848e540d75019e5764477edb567c`. The system diagnosis showed multiple stored facts absent from answer-time receipts; the GPT‑6 Luna diagnostic synthesis explicitly said this does not establish cause. A targeted task/project retrieval policy was compared with the original and generic-instruction control on the same eight questions, history, model, capacity, instruction set and answer limit.

The app group `EXP627CCD21BC1D465996A30FF0E630739B` completed all three conditions. On the six questions decided in both original and targeted runs, the original passed 1/6 and targeted retrieval passed 3/6 (two target-only passes, no original-only passes, three failures in both). Full runs had original 1/6 decided plus two uncertain, generic 1/6 plus two uncertain, and targeted 4/7 plus one uncertain. Five answers in the group remain uncertain. The comparison demonstrates a current-source improvement on this synthetic fixture while leaving substantial failures in place; the one-run, same-history design and automatic grades do not establish broad benefit.

The reproduction bundle, source digest, eight-question fingerprint, paired comparisons and 24-answer public review worksheet are under `output/proposal-delivery/live-current-source-repair-2026-10-28/`. Its condition key is private and mode 0600; the worksheet has zero human labels. The group is visible in the running application. This additional live experiment is separate from the clean-start install and the A/B/C evidence.

## Follow-up: evidence-aware question allocation

After the clean-start snapshot, the local working tree changed question
allocation to require at least one evidence-backed question per ability, then
distribute remaining questions as evenly as available distinct evidence allows.
The example with budget 8 and capacities 6/2/1/2 now allocates 3/2/1/2. A
dimension with no supporting question, or insufficient total distinct evidence
for the requested count, still blocks generation.

On 27 October 2026, the updated frontend workflow suite passed **40 tests**.
The backend suites `tests/test_llm_pipeline.py` and
`tests/test_execution_coverage_gate.py` passed **71 tests**. These tests use
mocked providers and local fixtures; no paid model request or audit database
write was made. React `act(...)` and Starlette/AnyIO deprecation warnings were
reported by their respective test runs. These results cover the allocation
change and targeted backend modules, not a complete backend suite or a fresh
clean-start run of this modified source tree.

## Follow-up: live synthetic three-method smoke — 28 October

The already-running local application completed the New Audit workflow using
the fictional Harbour/Orchard presentation conversation. The browser reached
Results, and a fresh read of `/api/v1/health` returned `ok` with the database
ready. Ground truth was source-checked and edited in the review UI to retain
the current and replaced facts and the unresolved deployment and authentication
conflicts. This was operator-assisted synthetic-data setup, not independent
human annotation.

The coverage preview supported two questions in each of the four abilities.
The rule-based generator change (`rule-based-v29`) produced and accepted 8/8
questions. Three runs completed under comparison
`EXP1FBCD4858ABC48B69E296BC41BFB170A`:

| Method | Run | Decided result | Awaiting review |
|---|---|---:|---:|
| Rule tests + rule review | `RUN6A74A303F5024F7B8FFA6F889F4BA07C` | 6/8 passed (75%) | 0 |
| Model tests + rule review | `RUN0EB30D66B66742AB825FD9A30A380DDA` | 3/7 decided answers passed; UI four-ability mean 50% | 1 |
| Model tests + hybrid review | `RUN461847267D604C40A88598C4C008D63A` | 2/5 decided answers passed; UI four-ability mean 50% | 3 |

The two model-test methods used the same generated questions and saved target
answers. Across all methods, 20 of 24 evaluation rows have a decided automated
label and four await human review. The individual averages are descriptive
only: question suites and reviewer coverage differ, and this synthetic smoke
does not estimate proposal performance. It is not a rerun of Experiments A, B,
or C and does not establish AC1 or AC3. The runs were executed against the
modified local working tree based on `40876e47e44f2af18187766a46976fe3bb15c3a5`;
the tree is not committed or pushed. The current results page remains open in
the browser for the user.

This live run updates the older 27 October statement below that no current
version model-backed audit had executed. The clean-start install remains a
separate source-package check; this smoke did not create a fresh application
database or prove that the local working tree is a frozen release.

## Latest live availability check

On 27 October 2026, the already-open local `/new-audit` page rendered the synthetic 28-message example. The authorisation checkbox was unchecked and the continuation button was disabled. A read-only request to `/api/v1/health` returned `{"status":"ok","service":"AI Memory Health Auditor","database":"ready"}`. No source was submitted and no model call was made. The Docker CLI could not enumerate containers in this follow-up because access to its daemon socket was denied; the direct application health endpoint did respond successfully.

## Clean frontend install and full frontend suite — 28 October

The assessed-source archive (`995f3909c03d184d609a1b19295d061d7abd59df5bc7364fb53261c5cc6553de`, 884 source members) was extracted into a new temporary directory. In its `frontend/` directory, `npm ci --no-audit --no-fund --loglevel=error` completed successfully using the checked-in lockfile. The runtime was Node 24.6.0 and npm 11.5.1.

- `npm run build` passed, including TypeScript type-checking. Vite emitted its existing large-bundle advisory.
- The complete `npm test` suite passed: **581 passed, 1 skipped across 62 test files** (582 tests total).

This verifies dependency installation, production build, and the full frontend test suite for that 884-member assessed-source snapshot. The subsequent package refresh added review-packet preparation utilities and updated experiment reporting and source-binding documents; application and frontend test code were unchanged. The final assessed-source ZIP has 889 source members; its adjacent source manifest records the archive hash, member hashes, and embedded-manifest verification. The review utilities passed Python syntax validation; the C utility generated an 84-row packet, and the current-source utility generated a 48-row blind review packet with public-file hashes checked and condition/run IDs/automatic judgments omitted. The results do not verify the backend's complete clean install, formal proposal outcomes, independent human labels, or a frozen/committed release. The full application test suite was not rerun because the package refresh did not alter application or frontend test code.

## Follow-up: saved-run export reconciliation — 28 October

The three runs were exported from the local API as individual result JSON,
experiment reproducibility JSON, CSV, and experiment artifact ZIPs under the
git-ignored `output/proposal-evaluation/live-smoke-2026-10-28/` directory. The
outer evidence manifest (`dbe5c5f209e45b10b4151da8b96c892c3c7c1ba4634f5be464b7ea61d618a646`)
lists ten exports; all ten file hashes matched. Both artifact ZIPs passed CRC
checks and every embedded member hash matched. For all three run IDs, the
artifact `result.json` matched the API result on run ID, score, pass count,
total, and uncertain count; each had eight response and eight evaluation
records. The rule CSV contains eight answer rows; the two model-method CSV
records contain sixteen, eight per run, each with run, response, and evaluation
IDs.

The two model-test methods have different generated test IDs, but all eight
prompt/expected-behaviour pairs match exactly. Every hybrid-review response
links by `shared_source_run_id` and `shared_source_response_id` to the exact
saved target response used by the model-tests/rule-review run. This verifies
the intended shared inputs across those two reviewer conditions. The files
are local synthetic-demo evidence and are excluded from the assessed-source
ZIP; this reconciliation does not convert the run into Proposal A/B/C or
resolve the four answers still awaiting human review.

## Follow-up: current-source presentation demo — 28 October

The running app completed a new six-run synthetic group,
`EXPE1ABDAD8B84F4739A7D0454F24F999C8`, using one frozen eight-question suite,
three Weak and three Strong target runs, and OpenRouter GPT-6 Luna for target
answers and automatic assessments. All 48 answer/evaluation pairs were saved.
Their recorded application source SHA-256 is
`7204fab7d9498f2496b40b253b4f4d44f6dec8938398926adf7342ae7e72868b`. Weak had
3 passes, 16 failures, and 5 uncertain answers; Strong had 11 passes, 4
failures, and 9 uncertain answers. Strong ranked higher in each of the three
repeated pairs. This is an engineering-only single-history demonstration;
uncertainties are not counted as passes, and automated judgments are not
independent human references.

The first memory-extraction request returned HTTP 502 after reaching its
1,800-token output limit. The operator-scripted run continued with the
fixture's source-derived curated inventory, while retaining the failed
extraction record. Offline verification checked 48 frozen answer inputs and
matched all 48 JSON and CSV evaluation IDs, but returned **failed** because
the three extraction roles were not all observed. This is not a full
intake-to-report pass. The complete request log, exports, and failed
verification receipt are stored in
`output/proposal-delivery/live-presentation-demo-2026-10-28/`; the app group
is visible at `/experiments`.

## Follow-up: extraction budget correction and intake retest — 28 October

The 1,800-token extraction output limit was raised to a 2,400-token minimum
for short histories while preserving per-message scaling and the 4,096-token
maximum. The new regression checks passed as part of the full backend result:
**2,749 passed, 8 skipped**.

A separate 28-message synthetic conversation, containing 14 user source
messages, was then processed with
OpenRouter GPT-6 Luna. Memory extraction, relationship analysis, and the
second-source review each completed in one request. Extraction returned 14
candidate memories; the advisory reviewer raised two items for operator
attention. The application still shows all 14 as unreviewed, with zero
accepted, edited, or rejected. This confirms the specific extraction-limit
correction on this case. It is not evidence that all extracted facts are
correct or complete, and no target-behaviour test or human reference decision
was made in this retest. The failed six-run demonstration above remains a
separate retained failure record. The review queue is visible at `/new-audit`.
Compact role receipts and the interpretation boundary are in
`output/proposal-delivery/live-extraction-retest-2026-10-28/receipt-summary.json`.

## Follow-up: clean extracted-source backend suite — 28 October

The assessed-source ZIP with SHA-256
`326031ac1d7df037300af806a0de0c1794a8cca83dbb032670659721e5166728` was
extracted into a new temporary directory. From that clean extraction,
`backend/tests` completed with **2,749 passed, 8 skipped in 114.17 seconds**.
The suite uses its configured test database and rule-based or mocked provider
paths; it makes no live model calls. This binds the backend regression result
to the packaged implementation. A later documentation-only clarification
updated the source-message count in the report and package notes; backend
source and test files were not changed by that correction.

## Source-version reconciliation — 28 October

The current assessed-source ZIP is a separate modified snapshot based on Git
commit `40876e47e44f2af18187766a46976fe3bb15c3a5`; its adjacent
`source-manifest.json` is the authority for the final ZIP and per-file hashes.
The current application-code digest is
`7d3033246fffc2d774f282f9e60c6ed6cd85848e540d75019e5764477edb567c`.
This digest is different from the app-source digest recorded by the six-run
presentation demo (`7204fab7…`) and the three-group tutor repair loop
(`3096dd63…`). Those experiments remain valid historical records, but their
saved outcomes are not runs of the current packaged application. Complete
source snapshots matching those two run digests were not found among the
local archived source bundles or available Git revisions inspected.

The proposal A/B/C Phase 4 protocol provides stronger source identity: its
SHA-256 is
`35b63d0dc8a36f24dc252a0c46f310b3a3e49846e8e9a52d72edaa3a2afd24c6` and its
`app_source` map freezes 136 individual Python file hashes. All 136 exact files
were reconstructed and checked against that map. The resulting code-only ZIP
is `output/proposal-delivery/phase4-app-source/phase4-app-source.zip`; its
SHA-256 is
`abda57e99565c663804d631a4ff925895391e3eedc09e9a3a0dbadd6d91c3f22`. Its
manifest is at
`output/proposal-delivery/phase4-app-source/source-reconstruction-manifest.json`.
This restores the source code identity declared by the protocol, not its
runtime environment, dependency image, hidden state, or external model
sampling. It does not convert the archived results into an independent or
held-out validation.

## Follow-up: current-source six-run repeat — 28 October

After the runtime source digest was reconciled, the running app completed a
new six-run synthetic comparison under group
`EXP77CB1B845E75465ABDF7C8FC986113E4`. The run recorded application-source
digest
`7d3033246fffc2d774f282f9e60c6ed6cd85848e540d75019e5764477edb567c`, matching
the current app digest above, and reused the frozen question-bank fingerprint
beginning `4bb4a2`. The offline verifier passed: 48 input checks were recorded,
JSON and CSV results reconciled, and all 60/60 API workflow steps completed
without failure.

The three Weak runs yielded 3 pass, 16 fail, and 5 uncertain results; the
three Strong runs yielded 15 pass, 4 fail, and 5 uncertain. This is a
source-bound repeated engineering experiment on one synthetic suite. It
supports the claim that the system can execute and expose the repeated
comparison workflow on this fixture. It does not provide independent labels,
show broad generalisation, or establish that Proposal AC1 or AC3 passed. The
report, exported results, source-bound verifier receipt, and blind-review
materials are being retained in the separate experiment-evidence archive;
they are not included in this clean-start note's assessed-source package.
