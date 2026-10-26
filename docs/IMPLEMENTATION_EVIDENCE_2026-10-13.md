# Implementation Evidence — 13 October 2026

This record describes engineering checks and local model behaviour for this
workspace snapshot. It is not a research result or a human-reviewed release.

## Source provenance and extraction-concurrency follow-up

Conversation intake now records an operator-declared source origin:
`synthetic`, `authorised`, `deidentified`, or `unknown`. The UI stores the
selection through draft and request recovery; API exports include the category
and a research-use notice. The declaration does not establish permission,
research eligibility, or independent labels. Migration 0035 preserves
unclassified historical rows as `unknown` and binds the one documented,
user-approved synthetic Meadow/Cedar smoke (`RUN33F698DCBA6E4DABB8E4BAFB37002D44`)
to `synthetic`. Formal synthetic-matrix conversations are also marked
synthetic when materialised.

PostgreSQL continues to use session advisory locks. Persistent non-PostgreSQL
stores now use `stage_locks` renewable database leases (three-minute expiry,
30-second refresh) so a second process cannot persist duplicate extraction
rows while a request is in flight. A crashed process releases its exclusion
after lease expiry. Separate in-memory SQLite databases remain process-local.

Focused verification after these changes:

- Backend conversation-origin, export, formal synthetic-matrix, and
  cross-process SQLite stage-lock checks: **74 passed**.
- Frontend source-origin control, API request, and intake-recovery checks:
  **28 passed**.
- TypeScript and production build passed; Vite still reports the existing
  approximately 1,090 kB main-bundle advisory.
- A disposable SQLite database already at revision 0034 upgraded through 0036;
  the approved Meadow/Cedar run became `synthetic`, an unrelated historical row
  stayed `unknown`, and the lease table was created.
- A fresh full-chain SQLite migration attempt stops at the pre-existing 0013
  constraint-drop operation, which requires PostgreSQL. This did not reach the
  new migrations; the 0035–0036 tail was checked from a 0034 schema snapshot.
- The full backend suite then passed **1145 tests with 7 skipped** in 87.85
  seconds; the full frontend suite passed **428 tests with 1 skipped across 53
  files** in 192.63 seconds. The frontend skip is the sandbox-restricted
  loopback proxy integration fixture. Ruff and `git diff --check` passed.

## Automated checks

- Backend: `PYTHONPATH=backend:. pytest -q backend/tests` — **1143 passed,
  7 skipped** after the atomic relationship, slot-alignment, relationship-coverage,
  pilot-fingerprint, source-ID-as-memory rejection, defect-mapping, answer-export,
  endpoint-specific relationship evidence and coverage-repair feedback fixes.
- Focused generator contracts: `PYTHONPATH=backend python -m pytest -q
  backend/tests/test_llm_pipeline.py` — **23 passed**. Planned slots now require
  an exact dimension, test type, and supporting-memory set; semantic review also
  receives the slot's relationship signature and intent. Repair batches map by
  slot structure even when the model returns them out of order. Rejected candidate
  dimension/type/evidence/reason details are fed into the next bounded repair
  prompt, and exhausted repairs save a failed coverage gate with the remaining
  slot evidence. The
  same suite confirms extraction fails closed, saves no candidates, and records
  a distinct failure when a model uses a source-message ID as the entire memory
  value. This directly covers the malformed `SYN001` output observed in the
  earlier Qwen receipt. A new live model call is documented below; it returned
  factual candidate text, so the source-ID rejection branch itself remains
  exercised by the regression test only.
- Experiment path contracts: synthetic Experiment A API flow — **1 passed**;
  Experiment B matrix execution, saved summary and export receipt — **19 passed**;
  Experiment C live-adapter, imported semantic review, and ranking-agreement contracts — **61 passed**;
  CSV encoding/export contracts — **24 passed**. These checks use rule-based or
  mocked outputs and synthetic fixtures; they verify paths and limits, not
  model quality, human review, or an official LongMemEval result.
- Experiment export controls: the latest `ValidationWorkbench.test.tsx` run —
  **22 passed**, including a regression that edits a rule-generated fixed-template
  question and requires researcher confirmation before freezing.
  ranking/live benchmark and saved experiment export UI — **28 passed** across
  three files. They cover visible A results JSON, B experiment downloads, and C
  live/ranking evidence downloads.
- Experiment C policy alignment follow-up: focused `LiveBenchmark.test.tsx` and
  `BenchmarkRankingAgreement.test.tsx` — **9 passed**. The live default now uses
  Weak `weak_first_hit` and Strong `strong_rule_based`, and ranking qualification
  rejects optional ablation pairs such as `scope_aware`. These remain synthetic
  contract checks; no licensed LongMemEval subset or official result was used.
- Latest full frontend verification: `cd frontend && npm test -- --run` —
  **425 passed, 1 skipped across 53 files**. The proxy integration test detects
  `EPERM` when this sandbox disallows binding a loopback server and skips with
  cleanup; its HTTP-forwarding assertions remain active where loopback binding
  is available. The prior timeout was a test-harness failure, not a product
  request failure.
- Current backend regression: `PYTHONPATH=backend:. pytest -q backend/tests` —
  **1143 passed, 7 skipped**. PostgreSQL-only API integration:
  `PYTHONPATH=backend pytest -q backend/tests/test_postgresql_api_smoke.py` with
  an isolated migrated PostgreSQL 16 `_test` database — **7 passed**. The full
  migration chain through revision 0034, its downgrade to 0033, and re-upgrade
  were verified on disposable PostgreSQL; the cluster was removed afterward.
- Pilot readiness: `backend/tests/test_pilot_annotation.py` and
  `backend/tests/test_formal_synthetic_matrix.py` — **84 passed** together,
  including the missing dataset-fingerprint blocker.
- Python compile check, Ruff, and `git diff --check`: passed.
- Frontend TypeScript check and production build: passed. The main JavaScript
  chunk is 1,089 kB, above Vite's 500 kB warning threshold.
- `NewAudit.workflow.test.tsx`: **28 passed**. The structured target-writer
  dropdown now disables virtualization so option selection works in the
  accessible UI and browser workflow.
- Focused checks for Experiments A/B/C, prompt-injection boundaries, Qwen
  pipeline contracts and target providers: **245 passed** across selected
  backend suites, then included in the complete passing backend run. Ruff,
  Python compile checks and `git diff --check` passed for the current snapshot.
- Historical frontend check before the current continuation: `npm run build`
  and `npm test` — TypeScript/build passed and **418 tests passed across 53
  files**. The latest snapshot's full-suite results are recorded below.
- Alembic: the full migration chain through revision 0034 was upgraded on a
  disposable local PostgreSQL 16 cluster using a private Unix socket. Revision
  0034's four `human_validity_*` columns and default were inspected; downgrading
  to 0033 removed them, and re-upgrading restored them. The cluster was stopped
  and removed after the check. SQLite was unsuitable for the full chain because
  pre-existing revision 0013 drops a constraint using a PostgreSQL-style
  operation.

## Local Ollama Qwen 3 1.7B smoke

All model inputs below were synthetic and sent to the local Ollama service at
`127.0.0.1`; no cloud provider or real conversation history was used.

The read-only model inventory probe for this continuation confirmed that the
local service has `qwen3:1.7b` installed (Ollama ID prefix `8f68893c685c`).
`ollama show qwen3:1.7b` reports Qwen 3 architecture, 2.0B parameters, Q4_K_M
quantization, a 40,960-token context, and metadata defaults temperature 0.6,
top-p 0.95, top-k 20. This inventory check sent no prompt; it does not describe
the settings of prior smoke calls, which are taken from their saved receipts.

1. The extraction pipeline invoked three distinct roles. Memory extraction and
   relationship analysis returned structured replies reporting model
   `qwen3:1.7b`. The relationship reply included a cross-topic edge that joined
   the Kestrel database update to the programming-language requirement. The
   independent memory-review reply failed its output contract. Both outcomes
   were recorded as model-stage evidence; neither was treated as validated
   memory truth.
2. The coverage planner initially selected five slots for a four-slot budget,
   including two Accuracy slots. The server rejected the plan. The planner
   response schema was tightened to make candidate IDs and per-dimension item
   counts explicit. Its next local run selected exactly one slot in each of
   Accuracy, Freshness, Conflict Resolution, and Appropriate Use.
3. Test generation returned four candidates; two passed local checks and two
   were rejected. The rejected candidates either did not cite both endpoints of
   an UPDATE for Freshness or exposed an answer value in the question. Three
   bounded repairs repeated the same failure classes. The generator therefore
   stopped and saved no partial suite. Semantic review, target execution, blind
   evaluation, and post-run diagnosis were not reached in this smoke.

The local Qwen run verifies provider identity, structured-stage invocation,
quota enforcement, answer-leakage/freshness gates, and fail-closed repair limits.
It does **not** show that Qwen 3 1.7B can produce a valid complete question suite,
and it is not a persisted API audit run.

### Unsaved extraction rerun after the source-ID guard

An unsaved replay of the same synthetic Meadow/Cedar source used the updated
`memory-extraction-agent-v7` prompt and the local Ollama model `qwen3:1.7b`.
The host shell could not resolve the Docker-only `host.docker.internal` alias;
the replay therefore used a process-local `OLLAMA_BASE_URL=http://127.0.0.1:11434`
override without changing project configuration. Memory extraction completed
and returned three factual candidate values citing `SYN001`, `SYN003`, and
`SYN004`; none was a message-ID placeholder. Relationship analysis failed its
output contract, while the advisory independent memory review completed. The
returned candidates and model review were not saved, confirmed, or used for
coverage planning. This confirms the updated prompt's live extraction path but
does not exercise the source-ID rejection branch (covered by the regression
test), validate relationship meaning, or advance the audit to test generation.

### Temporary API persistence replay

The same synthetic source was also run through the conversation import and
extraction API using a temporary SQLite database. Import returned HTTP 201 and
extraction returned HTTP 200 with three candidate memories. The temporary
database saved all three memory rows and the Agent stage receipts: extraction
`memory-extraction-agent-v7` completed with reported model `qwen3:1.7b`,
relationship analysis failed with `PipelineRequestError`, and the independent
memory review completed with reported model `qwen3:1.7b`. The temporary
database was deleted at the end of the smoke; the user's existing isolated
database was not changed. This verifies the live API persistence and provenance
path only. The source-ID rejection branch did not trigger, no candidate was
human-confirmed in this replay, and the failure in relationship analysis means
no audit or four-dimension coverage run was started.

### Later persisted API extraction smoke

A separate synthetic API smoke was run through `TestClient` using an isolated
temporary SQLite database and the real local Ollama endpoint. Import returned
HTTP 201 and extraction returned HTTP 200 with configured and reported model
`qwen3:1.7b`. The saved API candidates had the literal values `SYN001`,
`SYN003` and `SYN004` instead of factual memory text. The persisted advisory
memory review completed with three `unsupported_fact` findings and proposed
source-linked corrections. This is a substantive extraction-quality failure,
not a pass. After reviewing the source, the user edited and confirmed the
PostgreSQL candidate from `SYN003` and the Rust candidate from `SYN004`, and
rejected the `SYN001` label-only candidate. This authorization was explicitly
limited to the synthetic engineering smoke; it is not research gold or an
independent human annotation. The saved four-dimension coverage preview then
reported `minimum_met: false`: the confirmed facts support Accuracy, but there
is no confirmed UPDATE/CONFLICT relationship for Freshness or Conflict
Resolution and no CONTEXTUAL_OVERRIDE for Appropriate Use. A read-only replay
of the coverage-preview API against the isolated database returned HTTP 200
with the same result: Accuracy had 2/2 available slots, while Freshness,
Conflict Resolution and Appropriate Use each had 0/2 and named the missing
relationship evidence. At the time of this extraction review, no audit had
been created from this conversation. The six separate PILOT candidates in the
same isolated database were left untouched.

The user's later approval authorized these two edits for this synthetic
engineering smoke only. Read-only inspection confirms the saved values are
`Meadow’s current production database is PostgreSQL; SQLite is no longer
current` and `Use Rust for Cedar backend services`, both `confirmed`; `SYN001`
remains `rejected`. The original isolated database still has no relationship
rows; the subsequent audit attempts are described below. These records are not
research gold.

### User-approved Qwen target and evaluator smoke

After the user approved the two corrected candidates for engineering smoke,
the same four synthetic Meadow/Cedar source messages were loaded into a fresh
temporary SQLite database using the current ORM schema. The review path seeded
the label-shaped candidate values `SYN001`, `SYN003`, and `SYN004`; `SYN003` was
edited to `Meadow’s current production database is PostgreSQL; SQLite is no
longer current`, `SYN004` was edited to `Use Rust for Cedar backend services`,
and `SYN001` was rejected. Only the two edited candidates were confirmed. This
replayed the approved review action; it was not a new extraction call.

The saved audit `RUN33F698DCBA6E4DABB8E4BAFB37002D44` completed with a two-test
budget. The rule-based generator produced two grounded Accuracy questions;
Freshness, Conflict Resolution, and Appropriate Use remained unmeasured because
the approved source has no saved relationship edges. Local target model
`qwen3:1.7b` answered both questions, and both responses and input receipts were
saved. The strong rule-based target selected the corresponding current Meadow
and Cedar records; the old SQLite record was marked superseded and was not
selected. The deterministic evaluator (`rule-based-v56`) scored **0/2**. Its
failure notes cited the omitted terms `longer` and `services`. The responses
included PostgreSQL and Rust respectively, but no human assessment was
collected, so this result does not establish whether either verdict was a false
negative or whether an answer omitted a required nuance.

The deterministic diagnosis endpoint returned HTTP 200 with two evidence-bound
cases. Its exact-fact correspondence proxy did not match the target's stored
paraphrases; the endpoint itself warns that exact-text differences do not prove
semantic failure or causation. The model-based post-run diagnostic Agent was
not run because this smoke deliberately used the rule-based pipeline. A first
attempt against the older isolated extraction database failed before test
persistence because its `test_cases` table predates the `human_validity_status`
column; it left run `RUN009382C403634BDBA9ECB5835CC99D91` in `CREATED` with zero
tests and responses and made no target call. The completed run above used the
fresh current-ORM-schema database. Both runs and all source data remain local
and synthetic. This demonstrates the target/evaluator API path, not four-
dimension coverage, semantic evaluator validity, or research evidence.

### Saved-answer Qwen assessor contract follow-up

The first saved-answer reassessment `RUNEA1A1B8863D94415B4785A55E1E269AC`
made two local Qwen calls, but both returned unusable verdicts and were stored
as `uncertain_fallback`; no target calls were made. A no-save probe identified
the contract error: Qwen cited a `source_message_id` instead of a permitted
`memory_id`, and paired `passed=true` with `failure_type="accuracy"`. The
server rejected the inconsistent output and retained no raw provider response.

The judge prompt and structured schema were tightened: source-message IDs are
no longer exposed to the judge, `evidence_memory_ids` is constrained to the
current test's allowed memory IDs, and the prompt makes failure-category rules
explicit. The prompt receipt version is now `llm-judge-structured-v2`; strict
server validation and the independent rule cross-check remain in place. The
focused judge contract suite passed (**64 passed**).

Using the exact two saved target answers, with zero new target calls, the local
Qwen 3 1.7B reassessment `RUND8A6FEF53E724F6BB0A5CCA0C9104606` completed both
evaluator calls and cited only each question's allowed memory ID. Qwen marked
the Cedar/Rust answer as pass, while the deterministic rule check marked it
fail for omitting “services”; the system correctly left it unscored as
`review_disagreement`. Both checks marked the Meadow/PostgreSQL answer as fail;
Qwen's explanation incorrectly described the question as asking for the
user's recorded database technology, so this remains an automated, uncalibrated
judgement, not validated evidence. No human labels were added, and no result in
this synthetic run counts as research evidence.

### Relationship analysis v2 replay

A no-save local Ollama replay used only the authorized Meadow/Cedar synthetic
source. Under the prior relationship prompt, Qwen proposed an UPDATE citing only
the current-side message and a cross-topic override between Cedar's Rust fact
and Meadow's database fact. The server rejected the response atomically because
the endpoint evidence did not support both candidate records; no edge was
persisted. Relationship-analysis v2 now supplies source text grouped by
candidate and requires separate current/prior evidence lists. On a second
no-save replay, Qwen 3 1.7B returned a valid empty relationship list (HTTP 200);
no edge was saved. This avoids unsupported links but fails to detect the
expected update and is not a relationship-detection pass. These synthetic
replays are engineering evidence only, not accepted human relationship labels.

### Expanded four-dimension synthetic extraction smoke

A second authorised synthetic source was imported and processed through the
local Ollama API with configured and reported model `qwen3:1.7b`. Its six source
messages cover a Kestrel database migration, a general Python preference and a
Cedar Rust exception, and two Atlas deployment-region requirements with no
stated precedence. The extraction Agent returned six source-linked candidates.
Relationship analysis and the independent memory reviewer did not satisfy
their output contracts in the saved traces; their output is not accepted as
validated semantic review.

The same extraction was accidentally submitted twice while the first local
request was still running. Both requests persisted an identical six-candidate
set, leaving 12 candidate rows in the isolated SQLite smoke database. Treat the
duplicate rows as a request-concurrency artifact, not as distinct facts or two
independent extraction runs. The latest extraction trace referred to the
second six-candidate set, so that set was retained and the duplicate set was
marked rejected as technical cleanup. A relationship edge remained attached
after that Agent stage failed; the edge was cleared, and neither copy is treated
as validated relationship evidence. The user was asked to review the six
unique facts and proposed source-grounded links before any are edited,
confirmed, or used for question generation. PostgreSQL's cross-worker advisory
lock protects the production stage path; the accidental duplicate invocation
occurred in the isolated SQLite smoke. No research labels or results are
claimed.

This failure exposed a partial-mutation defect in `RelationshipAnalysisAgent`:
it could append an early valid edge, then reject a later invalid edge, leaving
the stage failed but the partial edge in memory. The agent now validates every
edge, including evidence from both endpoint memories, before attaching any
link. `backend/tests/test_relationship_topic_isolation.py` covers a valid edge
followed by an invalid edge and confirms the failed stage attaches none; the
focused relationship/pipeline checks passed **28 tests**, and the full backend
suite passed **1116 tests with 7 skipped** after the subsequent coverage-slot
change.

## Follow-up engineering completion checks

The semantic question reviewer now receives the relationship signature and
intent for each structurally assigned coverage slot. It can return a cited,
slot-specific mismatch; the generator routes that issue through bounded repair
and fails closed if the mismatch persists. This is an automated quality gate,
not a human question-validity label.

Experiment A now accepts a separate, researcher-confirmed response-to-defect
mapping for each completed condition. It binds every saved response (including
an explicit empty defect list) to the frozen inventory and stores a mapping
fingerprint in run provenance. Failure Discovery Rate counts distinct defect
IDs only when they are mapped to a response with a resolved independent human
failure label. Duplicate evidence signatures can represent distinct defect
IDs. Missing or inconsistent labels or mapping keep the rate unmeasured; the
mapping records reviewer declarations but cannot authenticate the person or
their decisions.

Experiment reports expose every uniquely paired saved test/response, including
pass, fail, uncertain and unassessed outcomes, through the result page, API,
CSV and reproducibility JSON. The CSV and JSON retain run, test, response and
assessment IDs; the page displays source evidence and IDs, with original
source statements behind a disclosure. Duplicate or cross-run answer links are
omitted rather than selected by database order. The dashboard dimension summary
also provides keyboard-accessible links to matching evidence, and comparison
charts preserve decided-answer denominators and show missing data as unmeasured.

Earlier follow-up verification (before the A/B/C gates and migration 0034
updates below): the full backend suite passed **1124 tests with 7 skipped** and
the focused `ValidationWorkbench.test.tsx` run passed **22 tests**. That snapshot
also passed TypeScript, production build, Ruff and `git diff --check`. Automated
checks do not substitute for a novice walkthrough or independent human study
evidence; the latest snapshot results are recorded below.

`docs/NOVICE_ACCEPTANCE_WORKSHEET.md` now provides a release-specific session
record, unprompted task wording, observer rules, dashboard-to-evidence checks,
and JSON/CSV reconciliation steps. It is prepared but blank; no novice-user
session or usability result is claimed.

## Experiment A and B protocol gates

Experiment A keeps automated question quality/grounding separate from human
validity. Each question must receive an explicit researcher decision before
target execution, and Category Coverage counts only questions accepted by all
three checks; coverage stays unmeasured until every question has a human
decision. The fixed-template arm is seeded by the deterministic rule generator
and then reviewed, edited, and confirmed by the researcher before freezing.
Its third arm now uses `contextual_indirect`, which excludes direct-recall
items, while all three arms retain the same frozen test budget. These are
workflow safeguards, not evidence that any question has been reviewed.

Formal Experiment B now requires an explicitly frozen analysis design and
development split, paired Weak/Strong conditions under one target
provider/model/temperature, and at least three repetitions for every condition,
including the deterministic `rule_based` baseline. The API and UI route
unplanned or smaller engineering matrices through a separately tagged
exploratory path. Neither route creates human labels or independent held-out
evidence.

Verification for these changes: focused backend checks across
`test_experiment_a_contextual_indirect.py`, `test_quality_workflows.py`, and
`test_formal_study_design.py` — **80 passed**; focused Experiment A review UI —
**31 component tests and 11 API tests passed**; Experiment B repetition UI —
**33 passed**. The latest `npm run build` (including TypeScript typechecking)
passed; Ruff, Python compile checks, and `git diff --check` passed. The main
JavaScript chunk remains 1,089 kB and triggers Vite's 500 kB advisory. Revision
0034 is now included in a PostgreSQL migration round-trip check.

After these changes, the full backend suite passed **1143 tests with 7 skipped**;
the PostgreSQL-only API suite passed **7 tests** on an isolated `_test` database.
`ValidationWorkbench.test.tsx` passed **22 tests**, and the complete current
frontend suite passed **425 tests with 1 skipped across 53 files** because the
sandbox returned `EPERM` when the loopback proxy test tried to bind its fixture
server. `npm run build` reran TypeScript and the production build successfully;
the main JavaScript chunk remains 1,089 kB and triggers Vite's 500 kB advisory.
Docker daemon access was unavailable, so the migration and API checks used a
private-socket PostgreSQL cluster under `/private/tmp`, removed afterward.

The latest engineering follow-up also closes three evidence/reporting gaps.
Scope-aware retrieval and the offline target baseline no longer branch on the
auditor's test-dimension label: UPDATE history is selected from explicit
question wording and target-owned records, with regressions for both a current
state question and a time-ordered comparison whose dimension is relabelled.
Provider-reported target model IDs are stored in `ExecutionMetadata` only after
a 120-character identifier allowlist check; provider tests cover accepted IDs
and reject multiline/control strings. The result API now returns every saved
target response—including unassessed responses—with its status, references and
source statements; the dashboard, CSV and JSON expose the same saved answers,
source evidence and sanitized run settings, and dimension links include pending
and unassessed answers. Focused checks: target isolation/provider and rule-based
tests **49 passed**; result/export tests **7 backend and 33 frontend passed**;
the comparison-response regression **1 passed**.

Formal Experiment B now rejects persisted plans below three repetitions as
well as new requests without a frozen design, development split, paired Weak /
Strong policies and fixed target provider/model/temperature. Partial histories
are unmeasured until all planned repeats are complete. Focused Experiment B
summary/design/matrix/history/saved-run checks: **105 passed**; the broader
formal creation/summary contract set: **125 passed**. Small engineering matrices
use the explicitly tagged exploratory route. Experiment A's fixed-template arm
is rule-seeded and then researcher-reviewed/edited/confirmed before freeze;
this is a workflow rule, not a completed human review.

### Four-dimension Qwen extraction smoke (v8)

The reusable source is `datasets/smoke/qwen-four-dimension-source-v1.json`. It
contains eight synthetic user messages intended to provide one stable fact, an
explicit database update, a general preference with a project-scoped override,
and two unresolved deployment-region statements. The data is marked synthetic
and is not participant evidence or a human-labelled research release.

An initial API attempt with extractor v7 returned a source label as the entire
memory value. The endpoint rejected that response and saved no candidates. To
reduce this field-confusion failure, extractor v8 showed Qwen only positive
ordinal source refs, timestamps and source text; the actual message IDs remain
server-side and are restored after strict ref validation. The source ref to ID
mapping is recorded in the Agent trace, but is not sent to the model.

The v8 retry used an isolated temporary SQLite database at
`/private/tmp/mha-qwen-four-dimension-smoke-20261013-v8.sqlite`. The synthetic
import returned HTTP 201 and Qwen extraction returned HTTP 200 with eight
candidate memories, each citing the expected source message. The model receipt
reported provider `ollama`, model `qwen3:1.7b`, tag digest
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`, sampling
temperature 0, and one HTTP attempt. Extraction used prompt version
`memory-extraction-agent-v8` and took 20,515.82 ms. The model emitted confidence
1.0 for every item; these model estimates are not calibrated confidence or
human confirmation.

The relationship Agent call used the same provider/model and completed in
4,150.71 ms, but returned an empty relationship set despite the explicit
UPDATE, CONTEXTUAL_OVERRIDE and CONFLICT scenarios. The independent memory
review Agent also used the same provider/model, but failed its output contract
after 18,351.05 ms. This describes the original v8 receipt only. The user later
approved the Maple facts and three source-supported edges for synthetic
engineering smoke, as recorded below; that approval does not turn the v8 model
output into independent labels or research gold. No four-dimension plan,
target response, evaluator result or complete end-to-end audit was run from the
original v8 receipt.

After the refactor, focused extraction/time-contract checks passed:
`PYTHONPATH=backend /private/tmp/mha-qwen-e2e-venv/bin/python -m pytest -q
backend/tests/test_llm_pipeline.py backend/tests/test_memory_source_time.py` —
**46 passed**. Ruff and `git diff --check` passed for the touched files. The
Experiment A/B/C export manifest now labels the archived suite digest
`frozen_test_suite_sha256`; its focused API/export regression passed **1 test**.

The historical complete backend check for the v8 extraction and experiment
export snapshot passed:
`PYTHONPATH=backend:. /private/tmp/mha-qwen-e2e-venv/bin/python -m pytest -q
backend/tests` — **1153 passed, 7 skipped in 79.26 seconds**. It emitted one
existing Starlette/AnyIO deprecation warning. This updates the earlier full
backend totals above; it does not change the human-evidence blockers.

### Relationship-model failure and safe review diagnostics

A no-save replay against the eight-candidate synthetic source used local
Ollama `qwen3:1.7b` with relationship prompt v4. The model returned all 28
possible pairwise links, including links between unrelated topics and links
whose proposed current endpoint was older than the prior endpoint. No database
rows were written. This is a semantic failure, not a relationship-detection
success. Relationship prompt v5 now enumerates every unordered candidate pair
and the server rejects a response before attachment if recognized topics
differ or an available timestamp contradicts current/prior direction. It still
requires independent human relationship labels; no v5 live model result or
accepted edge is claimed.

Independent memory-review failures now retain a bounded diagnostic receipt:
stage and error category, safe schema field locations/types, and an allowlisted
Ollama completion reason when available. Raw provider text is not included,
and the done-reason receipt is restricted to the independent memory-review
role. The receipt is exposed through the Agent execution trace and stored in
`agent_executions.error_diagnostics` by migration 0037. Focused regressions
verify schema/evidence/length failure categories, exclude raw response text,
and confirm relationship-analysis receipts do not retain the review-only
completion reason. The focused file passed **6 tests**; Ruff and
`git diff --check` passed.

Migration 0037 was applied to a disposable copy of the current eight-candidate
synthetic SQLite smoke database, marked at revision 0036. The new column and
revision were inspected; downgrade removed the column and restored revision
0036. Counts for conversations, candidate memories, relationship edges, runs,
tests, target responses, assessments and Agent traces were unchanged, and the
original database was not modified. A fresh private PostgreSQL 16 cluster also
ran the full Alembic chain through `0037_agent_error_diagnostics`; the revision
and `agent_executions.error_diagnostics` column were inspected before the
cluster was stopped and removed. The earlier full-chain SQLite limitation at
pre-existing revision 0013 remains.

At the later human review turn, the user approved all eight Maple candidates
and the three specified relationships for a synthetic engineering smoke only.
The three edges were saved through the application API with endpoint evidence:
SYN103 UPDATE SYN102, SYN105 CONTEXTUAL_OVERRIDE SYN104, and SYN106 CONFLICT
SYN107. All eight facts are now confirmed in that synthetic conversation; no
audit run, test, target response, evaluation, research annotation, or gold
release was created. The database retains `source_origin=synthetic`. A rollback
copy and a sidecar record of the approval scope are in `/private/tmp`; the
sidecar explicitly says this is not a research annotation or gold release.

The latest complete backend check after these changes passed **1171 tests,
7 skipped** in 71.66 seconds with one existing Starlette/AnyIO deprecation
warning. Ruff and full-worktree `git diff --check` passed. These results verify
engineering contracts only; they do not change the synthetic-only status of
the model traces or establish research validity.

Frontend release-contract recheck: `cd frontend && npm test -- --run` passed
**436 tests, 1 skipped across 53 files**. The skipped loopback proxy fixture
detects sandbox `EPERM` during bind and skips its HTTP-forwarding integration;
the remaining frontend tests passed. `npm run build` reran TypeScript and the
production build successfully. Vite continues to report the existing main
bundle size advisory at 1,089.58 kB.

## Proposal requirement cross-check — 13 October continuation

The full proposal was checked against the pasted task file and the original
17-page `ELEC5623_Group2_Proposal.pdf`, including Tables 1–8 and Sections
7.2–7.6. The fixed-template arm in Experiment A is now explicitly documented
and tested as rule-generated first, then researcher-reviewed, edited or
confirmed, and frozen. It is a rule-seeded reviewed baseline, not a
from-scratch human-authored baseline.

The Experiment B saved summary now always reports Accuracy, Freshness,
Conflict Resolution and Appropriate Use, the four-dimension Overall Memory
Health macro-average, paired differences, and within-history repeat
variability separately from between-history spread. It averages planned
repeats within each source history before giving histories equal weight.
Incomplete planned repeats and dimensions without valid judged questions
remain unmeasured. The focused summary/export check passed **20 backend tests**
and **4 component tests**; the A/B/C route regression passed **189 tests**.

The consent path now keeps a selected conversation or benchmark file unread
until explicit authorisation. Intake submission is the first API action that
contains conversation data; local drafts are stored only while consent is
checked. LongMemEval, LoCoMo and BEAM validation/run routes, semantic review,
and both inputs to ranking agreement reject a missing authorisation flag
before their adapters or analysis services run. Revocation clears imported
state and invalidates pending reads/results. These checks establish the code
path, not the operator's actual licence, ownership, or participant permission.

Final verification for this continuation:

- Backend suite: **1171 passed, 7 skipped**; one existing Starlette/AnyIO
  deprecation warning.
- Frontend suite: **436 passed, 1 skipped across 53 files**. The skipped test
  is the loopback proxy integration when the sandbox denies binding with
  `EPERM`.
- TypeScript and production build passed. Vite reports a 1,089.63 kB main
  chunk, above its 500 kB advisory threshold.
- Script tests: **15 passed**; Ruff on `backend/app`, `backend/tests`, and
  `scripts` passed; full-worktree `git diff --check` passed.
- The complete Alembic chain through `0037_agent_error_diagnostics` upgraded on
  a disposable PostgreSQL 16 cluster. Revision 0037 upgrade/downgrade on an
  isolated SQLite copy preserved row counts. After the user's separate approval,
  the Maple smoke database has eight confirmed synthetic facts and three cited
  relationships, with zero audit results. Its sidecar records that the review
  is for engineering smoke only, not research annotation or gold.

No research annotation or gold release was created. The software checks and
smoke-only approval do not supply independent human labels, adjudication,
held-out evidence, formal repeated outcomes, or a licensed compatible
LongMemEval subset.

### Latest extraction and coverage attempt (v10; 13 October 2026)

This section supersedes the older v8/v9 extraction status above for the latest
verified engineering smoke. It uses synthetic-only inputs; no participant data
or benchmark data was sent.

- OpenRouter provider `openrouter`, model `openai/gpt-6-luna`: extraction
  returned eight structurally valid, source-cited candidates in one HTTP 200
  request. This was an extraction-only smoke, not a saved end-to-end audit.
- Local Ollama provider, model `qwen3:1.7b`, extractor
  `memory-extraction-agent-v10`: extraction returned eight valid candidates,
  and the independent memory-review Agent passed its output contract.
- Qwen relationship analysis failed the topic-mismatch gate. The unsafe
  relationship response was rejected; it does not count as a model-confirmed
  relationship result. The separately user-approved Maple relationships are
  engineering-smoke inputs only.
- Qwen test generation using the user-approved synthetic facts and relations
  exhausted bounded coverage repair. The run saved no partial suite and did
  not proceed through target answering, assessment, or diagnosis.
- Focused regression checks for this change set: **43 passed**. A full backend
  suite was not run for this v10 delta. Do not carry forward a previous full
  suite count as verification of the current delta.
- A previously saved live failure trace remains on extractor v8 and has no
  field-path diagnostics. Its exact contract mismatch cannot be reconstructed
  retroactively from that trace; the v10 smoke is a separate result and does
  not rewrite it.

The user's approval of the Maple facts and the three cited relations was
explicitly limited to synthetic engineering smoke. It is not independent
annotation, research gold, or held-out evidence. The successful extraction
requests and passing review contract demonstrate those paths for the recorded
inputs only; the relationship gate and bounded generation failure mean a
complete Qwen end-to-end audit remains unverified.

### Extraction-contract and coverage follow-up (v10 / generator v9-v12)

The previous live saved failure used extractor v8 and its trace did not retain
the invalid response or field path. Its exact invalid model field cannot be
reconstructed. The trace did record an HTTP 400 rejection of the provider's
strict extraction schema followed by a JSON-mode fallback and then local
contract failure. Current code removes the unsupported `uniqueItems` keyword
from the provider schema while continuing to reject duplicate source refs
locally. For OpenRouter memory extraction only, a schema HTTP 400 retries once
with JSON mode; the local Pydantic contract and source-reference checks still
gate all persistence. Malformed optional timestamps become null, and safe
validation paths/types are included in the stage trace without raw model text.
The extractor remains v10. On the separate synthetic fixture, OpenRouter
`openai/gpt-6-luna` and Qwen `qwen3:1.7b` each returned eight valid candidates;
Qwen independent memory review passed. These checks do not rewrite the saved
v8 failure.

The test generator now uses agent v9 / structured writer v12. It calls the
writer once per planned slot and constrains dimension, type, count and exact
support IDs in both provider schema and local validation. Coverage retries also
run one slot at a time, keep deterministic quality checks, and stop after the
configured bound. The rule-based template generator is v25; conflict templates
preserve both recorded constraints and request clarification, and contextual
override templates keep the general preference applicable outside the scoped
task.

Verification for this follow-up: `docker compose exec -T backend pytest -q tests/test_llm_pipeline.py tests/test_memory_review_diagnostics.py` returned
**48 passed**; `git diff --check` passed. No full backend suite was run.
Local Qwen generation on the approved synthetic Maple facts still failed the
bounded gate for Conflict Resolution and Appropriate Use; no partial suite was
saved. The rejected candidates either chose a document as authoritative or
missed the task-specific scope. An isolated Qwen semantic review of four
deterministic synthetic templates returned no duplicate pairs but marked all
four slot alignments uncertain, despite the exact relationship signatures and
plain-language slot summaries in its input. No fallback was silently accepted,
and no audit rows were written by these isolated smokes. A complete Qwen audit
through target answer and evaluator remains unverified.

### Execution coverage and scoped-writer follow-up (agent v13 / writer v15)

The execution route previously enforced dimension quotas only when the saved
generator version began with `agent-coverage-semantic-v5`. Newer agents could
bypass that check. `app/services/generation_coverage.py` now enforces the saved
contract independently of version: accepted dimension minimums, exact planned
question type and evidence set, and the frozen total budget. Shared conditions
and answer-reuse routes use the canonical source plan. A failed refill cannot
replace the plan of the persisted suite; the review API displays that same plan.
Already copied answers remain idempotently reusable without new target calls.

Writer v15 receives only the complete evidence for its one planned slot, with
common grounding/security rules and the slot-specific behaviour. The coverage
planner still receives the complete confirmed inventory, and semantic review
still receives the complete suite. Reviewer v5 distinguishes a resolved UPDATE
and a scoped CONTEXTUAL_OVERRIDE from an unresolved CONFLICT even when all use
the Conflict Resolution dimension. No uncertain model findings were silently
accepted and no deterministic fallback was used.

The exact approved synthetic facts were checked read-only against the historical
temporary Maple database. They are verbatim copies of SYN101–SYN108, with the
three user-approved edges. `datasets/smoke/qwen-four-dimension-approval-v1.json`
binds that smoke-only approval to source SHA-256
`e84fb0e564c7439ce3edf0fc6ebf7b25a681c9bb9dd209b1b97eb5d5d8a7d406`.
`scripts/smoke_qwen_generation.py` verifies that binding and runs explicitly
with local Ollama `qwen3:1.7b`, preserving failure traces without audit database
writes. This runner verifies generation/review only, not a complete audit.

The initial two real scoped-writer trials failed after bounded repair. Full structured
receipts are preserved in `docs/evidence/qwen-generation-v10-scoped-2026-10-13.json`
and `docs/evidence/qwen-generation-v11-scoped-2026-10-13.json`. Neither reached
semantic review. The first was still missing Conflict Resolution; the second
was still missing Accuracy and Appropriate Use. The second also exposed a
local false acceptance: a conflict question named North/South while asking for
clarification. Quality validator v21 now rejects source-derived deployment
region values leaked into questions. Template v26 keeps personal location
distinct from deployment region and preserves both conflict constraints while
requesting clarification. The earlier local acceptance is not evidence of test
validity under the strengthened validator. Two subsequent trials, v12 and v13,
both remained short in Appropriate Use under the strengthened validator and
still did not reach semantic review. Their complete traces are preserved as
`docs/evidence/qwen-generation-v12-scoped-2026-10-13.json` and
`docs/evidence/qwen-generation-v13-scoped-2026-10-13.json`. The v13 Agent seeds
the first repair with the actual rejected prompt and reference, and limits
feedback to the current slot's evidence. Model output still leaked the language
answer into the question, so no suite was accepted. These are different prompt
versions and must not be pooled as a formal repeated study.

Current selected regression suite: **319 passed**, with one existing
Starlette/AnyIO deprecation warning. This covers `test_execution_coverage_gate`,
`test_llm_pipeline`, `test_trace_and_test_review`, `test_auditor_method_comparison`,
`test_memory_review_diagnostics`, `test_test_quality_and_baselines`,
`test_rule_based_evaluator`, and `test_api_experiment_flow`. Ruff passed on the
changed code, tests and runner. No full backend or frontend suite was run for
this follow-up. The preserved traces were checked for the exact synthetic source
fingerprint, smoke-only scope and absence of credential/header fields.

The separately recorded local inventory, observed after these model calls,
reports digest `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`,
Qwen3 family, `2.0B` parameter metadata and `Q4_K_M` quantisation for the
`qwen3:1.7b` tag. It is an inventory receipt, not a digest bound retroactively
to the earlier requests. Future runner executions capture inventory before
dispatch. See `docs/evidence/README.md` for reproduction and limitations.

Additional engineering gaps identified by current code inspection remain:
the Experiment B formal materialiser currently declares imported histories
synthetic, so an authorised/deidentified research-source path is not yet
implemented. The former Experiment C pooled-score/single-pair limitations are
addressed by the follow-up below, while its pre-execution plan freeze remains
open. These are implementation gaps in addition to the
external research evidence listed below. The full goal is still active.

### Experiment C macro-average and repeated analysis follow-up

Ranking v2 now calculates Auditor ordering from the unrounded, equal-weight
macro-average of all four dimensions. Per-dimension counts/percentages accompany
the score, and any missing dimension makes Auditor ordering unmeasured and the
agreement inconclusive. Benchmark scores remain response accuracy. A simulated
contract test deliberately has 9/12 vs 3/12 pooled passes but 25% vs 75% macro
scores; the ranking follows the macro scores. This is a math/contract fixture,
not a model result or empirical comparison.

`RepeatedRankingService` adds the read-only route
`/api/v1/research/benchmarks/longmemeval/ranking-agreement/repeated`. An input
declares 3–20 planned trial IDs and the available comparison evidence. Original
audit and benchmark executions cannot be reused to inflate the repeat count.
Successful repeats must bind to the same frozen audit experiment/suite, source
subset, model, reader/profile, output budget, adapter, and assessment standard.
Missing, unmeasured and invalid trials stay in the returned plan, with reasons
and source run IDs. Aggregate means, sample SD and directional agreement are
null for an incomplete plan. Ties have explicit separate counts. Each repeat
has equal weight; the two question sets' absolute scores are not compared.

The frontend includes single-pair macro score labels, dimension drill-down,
missing-dimension states and a repeated-results panel with source consent,
input template, trial status table, within-suite mean/variability and JSON export.
Consent revocation invalidates in-flight reads and results. The display and
export use the same returned report. Weak/Strong selection excludes optional
scope-aware ablations. A read-only browser DOM walkthrough confirmed the new
panel loaded with upload/analysis disabled before authorisation; no benchmark
source or real conversation was submitted during that inspection.

Verification: **77 selected backend tests passed** (`test_ranking_agreement`,
`test_repeated_ranking_agreement`, `test_semantic_review`, `test_live_benchmark`),
and **41 selected UI tests passed** across the ranking, repeated-ranking and
research-workspace components. TypeScript, production build and Ruff passed.
The backend retained the existing Starlette/AnyIO warning; parent UI tests
reported existing React act warnings. Vite's main chunk remains 1,089.77 kB,
above its 500 kB advisory threshold. No full backend/frontend suite was run for
this delta.

An actual local API call with the empty evidence template returned HTTP 200,
`status=partial`, three missing planned trials and a null agreement rate. The
response is preserved as
`docs/evidence/experiment-c-repeated-missing-evidence-2026-10-13.json`. It contains
no benchmark source, labels or model results; it verifies the missing-evidence
response only. Contract fixtures above are simulated and made no real model
calls. No original audit data was edited by this work.

The analysis plan is caller-declared at analysis time, and its fingerprint binds
declared execution/source identities rather than outcome labels. It is not a
server pre-registration receipt. A persisted pre-execution Experiment C plan,
licensed actual subset, independent semantic labels and real repeated execution
evidence remain required before reporting formal Experiment C completion. The
full engineering and research goal is not complete.

## Experiment B research-source materialisation

The former synthetic-only materialiser now supports a separate
`POST /api/v1/research/formal/research-matrix` contract. It requires the exact
`deidentified_research` origin, an exact-dataset permission receipt, research and
operational-storage authorisation, deidentification, and exclusion of demo-only
personal history. Cloud providers need an additional cloud-processing
permission. It retains the existing formal study design, distinct development
histories, matching reviewed pilot, same target settings, paired Weak/Strong
conditions and at least three repetitions.

Research histories retain `source_origin=deidentified`. The receipt is part of
the saved acceptance protocol, recovered manifest and frozen input fingerprint;
a changed receipt prevents execution. The research page selects the dedicated
route and requests a permission file plus server-storage confirmation. The
unapproved permission template and team workflow are in
`datasets/templates/research-source-permission-template.json` and
`docs/HUMAN_EVIDENCE_HANDOFF.txt`.

Validation used simulated research-permission and human-label fixtures in an
isolated database; no real research dataset was imported. Fourteen targeted
backend tests passed, including import/restore, deterministic target execution,
scoring, source/fingerprint/permission gates and receipt tampering. The preceding
combined run also passed all 107 existing formal study/history/summary/saved-run
regression tests; its new suite initially had one test using a field omitted
from the public projection. That assertion was corrected to inspect the saved
metadata, and the complete new suite was rerun. Frontend TypeScript passed and all 34
ResearchValidation tests passed, including the research-storage consent gate
and dedicated endpoint dispatch. The first UI run had five old completion-text
expectations; these were updated to the source-neutral completion message. Ruff
and git diff --check passed. These contract
fixtures prove engineering behavior, not actual human authorship or permission.

Real reviewed source releases, independent labels, pilot/held-out evidence and
actual repeated model outcomes remain missing. The full goal is still active.

## Experiment C server plan and execution receipt delta

Migration 0038 adds benchmark_plans containing frozen metadata and per-trial
execution states/fingerprints. The new create/read/execute/analyse plan endpoints
reject post-answer planning, reused audit IDs, incomplete/changed suites, unequal
settings, altered source, duplicate dispatch, changed evidence or evaluator
standard. The normal audit execution/evaluation boundary also checks C input
fingerprints. Source payload and full benchmark replies remain request-scoped;
the caller must preserve the returned original evidence under its permission.

Verification: 97 tests passed across test_benchmark_plan.py,
test_ranking_agreement.py, test_repeated_ranking_agreement.py,
test_formal_research_matrix.py and test_formal_study_design.py. The new plan suite
covers a complete simulated API sequence: server freeze, six original Auditor
executions, three benchmark dispatches and receipt-bound repeated analysis.
Provider responses and imported review labels are simulated. This is not a real
Qwen run, official benchmark score or human research evidence. Ruff and diff
checks passed. The new-table migration completed without editing existing audit
records. Earlier new-fixture runs failed due to a wrong canonical test ID and
identical prompt wording; fixtures were corrected and the final combined suite
was rerun, preserving the existing duplicate-question execution gate.

A dedicated plan UI, real licensed subset/repeated model evidence and independent
labels still remain. The older repeat upload UI/API continues to be a descriptive
analysis path and does not acquire server-freeze status automatically. The full
goal is not complete.

## Experiment C plan UI and recovery delta

BenchmarkExecutionPlan is integrated into the repeated ranking panel. It gates
file reads on processing consent, separately requires metadata-storage consent,
and exposes freeze/restore/find, per-trial status and explicit dispatch. Original
answer evidence is retained on screen even if status refresh fails; later repeats
do not overwrite earlier files. Downloads use those exact in-memory objects.
A late file read after consent revocation cannot restore the source. Repeated
analysis with a plan ID uses the receipt-bound endpoint and labels server-frozen
provenance; without an ID it remains descriptive caller-declared analysis.

GET /benchmarks/longmemeval/plans retrieves up to 50 metadata plans, allowing
recovery after a lost creation reply. It dispatches no calls and returns no
benchmark source. The actual local page rendered the new controls with source
consent off and file/creation/analysis buttons disabled. A read-only Find action
returned No saved benchmark plans found. No source was uploaded and no model
was called through the browser. The temporary browser tab was closed after
DOM and viewport inspection.

Validation: 16 backend plan tests passed (including the original complete
simulated execution/analysis and new listing boundary); 14 frontend tests passed
across BenchmarkExecutionPlan, RepeatedBenchmarkRanking and
BenchmarkRankingAgreement. Production build including TypeScript passed, with
the existing large-main-chunk advisory. Ruff and diff checks passed. Simulated
API replies/labels remain engineering evidence only. Real repeated Qwen calls,
a licensed representative subset, independent human evidence and novice-user
acceptance still remain; the full goal is not complete.

## Local Qwen scoped-language and semantic-repair delta

Three additional real local trials used the exact previously approved synthetic
Maple facts/relations. v14 uses a focused Appropriate Use instruction that asks
for a task recommendation instead of copying the concrete Java/Python choices.
That removed the old leakage, but deterministic topic detection failed to
recognise “backend language”. Shared memory_topics now recognises software
language category wording while keeping spoken languages and navigation outside
that category (quality validator v22).

v15 then filled all four initial evidence slots. Semantic review flagged the
suite, including questionable neutral-wording/relationship findings. Batched
semantic repair changed a frozen dimension/evidence contract and was blocked.
v16 repairs each flagged question through the single-slot schema, preserving
its type, dimension and exact evidence set. Citation order can be normalised
without treating reordered identical evidence as a changed source set. Local
checks still reject missing/extra/duplicate evidence and hidden audit IDs.
Its conflict repairs emitted hidden memory IDs in expected_behavior; after the
bounded repair limit, the run failed and no partial suite was saved.

Actual provider/model: Ollama qwen3:1.7b, with inventory/digest observation in
each report. No cloud fallback, human research label, target answering,
evaluation or operational-database write was introduced by these trials.
Reports and SHA-256 values are in docs/evidence/README.md. Reproduction uses
scripts/smoke_qwen_generation.py; indexed progress now exposes each writer
invocation even when several are semantic repair calls with the same stage.

Verification: 134 tests passed across test_llm_pipeline.py,
test_test_quality_and_baselines.py, test_language_topics.py and
 test_semantic_review.py; Ruff and diff checks passed. The new focused-prompt
unit fixture initially omitted generator observation setup; it was corrected
and the complete selected suite rerun. These tests prove mechanical boundaries,
not that Qwen semantic review is reliable. Full local Qwen end-to-end acceptance
remains unverified; the next issue is the semantic review/repair handoff.

## Evidence still required

- The repository also contains a declared human double-annotation package for
  the synthetic Pilot v2 set. It has 25 paired labels and 25 adjudications, but
  lacks the exact dataset fingerprint and has no item-to-source mapping in this
  checkout. The analyser returned 100% agreement; kappa was 1.0 for two tasks
  and undefined for three constant-label tasks. The formal-readiness gate now
  blocks this package until it is bound to the exact validated dataset. The app
  does not authenticate the claimed human authorship or reviewer independence.

- Human source/relationship review, independent question-validity labels,
  blind evaluator labels, adjudication and agreement.
- A complete saved audit whose real model calls reach target response,
  evaluator, and (where failures exist) diagnostic stages. The two-confirmed-
  fact API smoke is missing three dimensions. The expanded Qwen candidate set
  has user-approved facts and relationships for engineering smoke only; it
  still needs an independently reviewed research inventory before coverage
  planning and question generation can support research claims.
- Novice-user acceptance and reconciliation of saved UI, JSON, and CSV results.
- Frozen repeated Experiment A/B evidence and an authorised, compatible
  LongMemEval subset for Experiment C.

The synthetic fixtures and model outputs above must not be counted as human gold
labels, held-out evidence, participant data, or benchmark results.

## User-authorized GPT 6 Luna migration (2026-10-13)

The user explicitly superseded the earlier local-Qwen-only instruction for future model calls. New configured extraction, planning, writing, reviewing, target answering, and judging use OpenRouter `openai/gpt-6-luna`. The running backend was recreated and its nonsecret configured identities verified. New benchmark UI defaults and plan templates use the same model. Historical frozen experiments and explicit legacy provider choices remain readable; rule comparison arms and mechanical checks remain part of the experiment design. The native Mem0 pilot is still a separately selected local-Qwen-only integration and was not migrated or dispatched.

Actual approved synthetic Maple generation (Agent v20 / writer v18 / reviewer v8) completed four dimensions. One semantic quality repair was followed by a clear final review. This is engineering evidence, not independent human research evidence. Target and judge smoke supplied all eight approved memories in full context; it is not a Weak/Strong comparison or an official benchmark. All four target replies completed; all four judge requests returned valid contract data without fallback. Accuracy is decided positive. Freshness, Conflict Resolution and Appropriate Use retain null verdicts because the model judge and deterministic cross-check disagree. No audit database writes occurred. This does not establish formal research completion.

Verification: 32 backend provider/default/live-benchmark tests passed; 47 relevant interface tests passed; interface typecheck passed. The previous selected pipeline/generation regression run passed 142 tests.

Retained Qwen v17/v18/v19 runs failed; the isolated thinking probe succeeded, but no complete Qwen target/evaluation run was produced. A passive clarification false rejection was fixed in quality v23 after v19. Those failed receipts remain available and are not relabelled as passed.

## Evaluator and Experiment B controls follow-up (2026-10-13)

Rule evaluator v58 selects explicit current database values, recognizes user clarification of controlling constraints, checks separately scoped task/general language values, and recognizes source-derived deployment alternatives without demanding the literal word “conflict”. It still rejects denied clarification, missing alternatives, reversed task language scope, and choosing an unresolved region while asking for clarification. The database replacement check requires the earlier value when the question asks for replacement.

The first new v57 Luna target/judge trial yielded three decided positive cases and one conflict disagreement: its answer explicitly contrasted North/South and asked which controlled but lacked a literal conflict keyword. The exact four saved replies were then reassessed with actual Luna judge calls and v58 local cross-check, without replaying target requests. All four are decided positive; this is approved synthetic full-context engineering evidence, not a formal Weak/Strong run, independent gold, or an external benchmark score. Original v56/v57 disagreement files are retained unchanged.

Experiment B new matrices are v9, with protocol v2 and reader_control=fixed_strong_reader. Every strategy uses the same Strong reader. Restore, direct frozen-input/execution/acceptance guards, saved-run validity and condition-summary checks protect that control. Historical protocols retain absent control as None; their records/results remain preserved and cannot gain formal B certification from schema defaults. The settled focused formal regression passed 114 tests.

Saved intake now offers an explicit switch to the current OpenRouter model (GPT 6 Luna). Switching changes the next extractor selection only, sends no request, and preserves the exact saved source, request identity and acknowledged conversation ID. Continue resumes that conversation; completed extraction is still read without redispatch, and already-used conversations retain the existing audit guard. Five focused intake/recovery UI tests passed, with 26 unrelated tests excluded by the name filter; TypeScript passed.

Settled combined evaluator/formal-study verification: **400 backend tests passed**, one existing Starlette/AnyIO deprecation warning, 111.96 seconds. Ruff checks for changed backend files and final diff check passed. No live database records were changed by these tests or smokes.

## Intake recovery and entry-page verification (2026-10-13)

Historical Ollama submissions were incorrectly rejected by the browser checkpoint reader even though the application supports local models. The reader now accepts a nonblank local model identity while preserving the original source, source origin, message IDs/timestamps, request key and acknowledged conversation ID. Explicit Luna-switch recovery is covered for both cloud and local saved submissions. Existing completed-extraction and audit-use guards remain active.

The current running entry page was inspected at default desktop size and 390×844. OpenRouter GPT 6 Luna is visibly selected, and consent-dependent import/Continue controls remain disabled until authorization. The catalog/status text had no layout spacing; a small grid layout now separates those messages and the selected-model check button. Screenshots are synthetic/default entry data only; no source was submitted and no availability inference was requested in this visual check. This checks the entry screen, not full-screen acceptance or novice usability. Temporary viewport override was reset and the inspection tab closed.

Focused model-picker/checkpoint tests: 9 passed. The preceding recovery-selected run: 9 passed, 25 unrelated tests excluded by name filter. Production build and TypeScript passed; the existing large main-chunk advisory remains.

## Isolated API smoke: preserved incomplete attempts (2026-10-13)

`smoke_luna_isolated_api.py` creates a new temporary SQLite database before importing the application; it sends real API requests and actual OpenRouter Luna calls. Source bytes and prior user approval are SHA-bound. Engineering confirmation rejects model candidates and adds only the exact eight previously approved synthetic statements/three edges through supported routes. This reuses prior approval; it is not new human research annotation.

Attempt v1 completed extraction, relationship analysis and independent memory review, all reporting Luna; the harness then misparsed a successful empty HTTP204 response. That failure is preserved rather than relabelled. Attempt v2 corrected empty-body parsing and completed the Weak policy's own-history controlled-store generation, four target answers, blind model assessment and results. Its score was25.0, 1/4 positive, with0uncertain/excluded decisions. It then stopped on an actual diagnostic Agent HTTP502 before the Strong condition. Therefore v2 is incomplete, not a successful paired comparison or full pipeline. Temporary SQLite cleanup occurred; actual diagnosis failure details remain limited because the first harness did not fetch the failed Agent receipt before teardown.

Attempt v3 has been launched with explicit diagnostic failure retention, failed-Agent receipt collection and independent Strong continuation. Its final status is not yet established here. Inspect the live process or final receipts before deciding the next action; do not restart on an observation timeout. Original operational database records are untouched.

## Completed isolated API pair and remaining release evidence (2026-10-13)

Attempt v4 preregistered both runs before the shared suite froze. Actual Luna extraction, relationship analysis, independent memory review, four-dimension planning/generation/review, eight controlled-store target replies, blind assessments and both diagnostic v2 syntheses completed. The supported API result/JSON bundle/CSV identities, answer text, scores and dimension denominators reconcile. Target store IDs are disjoint from approved auditor IDs and retain original source references; source inspection separately confirmed target ingestion receives original conversation history. This is observational delivery evidence, not proof of provider attention.

Weak:1/2 decided answers positive,2pending,overall50.0 and formal overall null. Strong:3/4positive,0pending,overall/formal75.0; Conflict Resolution is a failure. These are one-repeat approved-synthetic engineering results, not formal Experiment B or independent evidence of strategy superiority. The full instruction hash includes memory JSON and differs between inputs; verification reconstructs each full hash and compares only the reader-policy suffix. The Maple pair had identical policy suffixes.

All8 historical judge receipts had configured Luna but missing provider-reported identities. They remain unknown. The verifier was corrected to report judge_actual_model_verified=false rather than incorrectly importing the target’s identity. After this v4 record, the evaluator now saves sanitized model/modelVersion identifiers when actually returned (judge meter v3); a real diagnostic-free saved-answer probe returned reported_model=openai/gpt-6-luna with a valid judgment. No target request or historical result was rewritten by that probe.

The Strong reader’s previous conditional extra guidance depended on retrieved context. After v4 it now always includes the same conditionally phrased conflict guidance, so retrieval changes only evidence JSON rather than which policy text is added.119 selected backend judge/provider/formal-design checks passed on settled code. This latest reader/metadata delta has not yet been rerun through a fresh full API pair; v4 proves the earlier frozen runtime only.

Diagnostic v2 increases its finite output allowance to4096–12000tokens. The exact saved synthetic input failed at1200(noJSON,1200reportedoutputtokens) and completed at4096(1406reportedoutputtokens). Shared pipeline receipts now record requested limits and safe finish reasons, reject reported length even if text parses, and preserve that metadata in Agent traces.78 selected diagnostic/pipeline/trace tests passed. Old diagnostic failures remain retained.

Temporary v4 SQLite was actually removed after context exit. A separate synthetic-only snapshot is retained at /private/tmp/luna-isolated-api-e2e-v4-synthetic-only.db for local evidence inspection; it is not the operational database. SHA25686cc9ec35a272782a116d25ce252319df83523430424c60f16a86f82221e2161. No production database writes occurred.

Complete interface run:451passed,1failed across55files; the failed fixture still selected the old default provider. It was corrected to switch to the other provider and its2targeted tests passed. An attempted VM worker rerun was incompatible with installed Ant Design/rolldown dependencies and cannot count as release verification. The supported isolated fork-pool rerun with2workers is live (session32854); final outcome pending. The standard production build/TypeScript passed earlier in this turn.

Final interface verification update: supported command `docker compose exec -T frontend npm test -- --pool=forks --maxWorkers=2` completed **55files /452tests passed**, 435.44seconds, no skipped tests. The earlier default-provider fixture failure and incompatible VM-pool attempt remain historical outcomes, not current release failures.

Current model receipt follow-up: actual saved-answer probe using judge meter v3 returned configured and provider-reported `openai/gpt-6-luna` with valid judgment. The source v4 report SHA is retained in the probe; original8unknown model identities and judgments remain untouched. `probe_luna_judge_identity.py` makes no target request or database write. Full integrated evidence on the final fixed reader/identity metadata runtime remains next work; formal research and novice acceptance remain pending.

## Latest integrated runtime verification and separate reassessment (2026-10-13)

Isolated API v5 completed on the final fixed reader and judge meter v3 runtime: all model-backed roles and all eight target/judge calls report OpenRouter openai/gpt-6-luna. Both diagnostic v2 calls completed. Strict verification (--require-reported-models) passed shared four-dimension suite, exact previously approved8facts/3edges, source/store separation, reconstructed instruction hashes, one fixed reader-policy suffix, and API/JSON/CSV identity/answer/score/denominator correspondence. Disposable SQLite removal was checked after context exit; production database writes0. No snapshot was requested for v5; its complete report, bundle and CSV are retained.

Original v5 decisions: Weak1/4positive,0pending,overall/formal25.0; Strong2/3decidedpositive,1pending,overall66.7/formalnull. The Strong Freshness answer was correct (“PostgreSQL applies now; it replaced MySQL”), but its reference used “current system” rather than “current database”; the local lexical parser wrongly selected the explanatory word “previously”. Rule v59 now recognizes an explicitly current database value without requiring that category noun. Eight positive/negative category tests and the selected evaluator/judge suite passed275tests.

A separate actual Luna reassessment of the exact eight v5 saved answers under rule v59 completed: Weak1positive/3negative/0pending, Strong3positive/1negative/0pending. Every new judge receipt reports Luna. Target requests0, database writes0. This changes the assessment of the saved Freshness answer; it does not demonstrate improved target behavior. Original v5 records and exports remain unchanged. The reassessment is linked by SHA256 to the original report and is synthetic engineering evidence only, not independent human annotation.

Verifier now rejects historical runtime mismatch before reconstructing instruction receipts. A no-inference check on preserved v4 evidence under current runtime confirmed that refusal. A future historical reconstruction requires its original application source; the old verification supplement remains the check performed at that time. Requirement/Agent table column counts were also corrected and checked.

Research remains pending genuine independent labels/adjudications, held-out releases/repeated studies, authorised compatible LongMemEval data and novice usability observations. These were requested from the user; none are inferred from the synthetic approvals. Current rule v59 delta is verified by focused tests and exact-answer model reassessment, rather than a newly regenerated full pair.

## Read-only report inspection and team handoff (2026-10-13)

The user confirmed that genuine independent annotation/adjudication, authorised LongMemEval subset/permission/citation material, and real novice acceptance records will be supplied by the team later. These remain pending; synthetic engineering approvals do not satisfy those research requirements. Do not repeatedly request these deferred inputs or fill them with invented observations.

The preserved v4 synthetic snapshot was served using two temporary loopback-only inspection containers, a read-only SQLite mount, GET/HEAD/OPTIONS-only middleware and empty cloud keys. The actual Strong report showed75%,3/4passed, four decided dimensions; its conflict detail expanded to the saved question, actual answer, North/South reference memories and original timestamped messages. The actual Weak report showed50%,1/2decidedpositive and2awaitingreview, with Freshness/Conflict displayed as awaiting review rather than zero or passed. Its percentage explicitly excluded undecided answers and warned that old rule versions retain their saved verdicts. These are historical v4 display checks, not current v59 performance results.

Desktop screenshots and a390×844 Weak screenshot were saved. DOM widths were390/390, with no horizontal overflow. The browser download event tool timed out and did not provide a file path; actual browser download remains unverified. Prior API/JSON/CSV reconciliation and frontend export tests remain separate evidence and do not substitute for observing a browser-saved file. No additional model calls or research labels were produced. The viewport was reset, the temporary tab closed and both named inspection containers removed. The snapshot SHA256 remained86cc9ec35a272782a116d25ce252319df83523430424c60f16a86f82221e2161.

## Migration 0038 release check (2026-10-13)

A separate Compose project mha-goal-migration-check created a fresh PostgreSQL16 tmpfs database with no published ports, no operational volumes and no .env import. The full Alembic chain upgraded to0038_benchmark_plans; alembic check reported no new upgrade operations. Static checks passed. The migrated PostgreSQL/API checks plus Experiment C plan contracts passed24tests (one existing Starlette deprecation warning). A new PostgreSQL persistence test verifies plan protocol/fingerprint and failed/completed execution metadata across separate sessions, without corpus storage. The plan contract fixtures explicitly use OpenRouter Luna and mocked transport with a synthetic credential; they are not actual model evidence.

The first combined run had15passes/9failures because stored Qwen fixture settings differed from the new Luna request default. After aligning settings,21passed/3failed because the isolated environment correctly had no OpenRouter credential. The final fixture uses a scoped synthetic test credential with mocked transport, and all24passed. The intermediate failure transcript is retained. This fixes test reproducibility without weakening configuration binding.

Migration0038 was downgraded to0037 and upgraded again on the disposable database; the final structure check passed and revision0038 is head. This is a schema roundtrip, not a claim of preserving benchmark-plan rows through a downgrade that deliberately drops their table. docker-compose.ci.yml now checks model/migration drift and includes plan contracts. No operational database or historical result was changed.

## Full backend regression and simulated fixture repair (2026-10-13)

The complete current backend was checked in a network-disabled temporary container with no .env or operational database and read-only code mounts. Ruff passed; first complete run:1236passed,5failed,70setup errors,8PostgreSQL skips, one existing Starlette deprecation warning (210.66seconds). The migration/PostgreSQL path is covered by the preceding independent integration run. Initial full failure transcript and source manifest are preserved. No model performance claim follows from this run.

The new OpenRouter Luna default exposed simulated fixtures that patched transport but still depended on a real configured credential. Only those mocked-transmission tests now use scoped synthetic keys. The next focused run revealed missing explicit answer budgets in ranking fixtures and implicit local-model assumptions in native Mem0 fixtures. Ranking fixtures now freeze256tokens; the intentionally local native compatibility tests explicitly select their historical Ollama/Qwen profile. These are mock contracts, not new Qwen calls. Application credential checks, unknown-budget rejection and native compatibility gates remain intact. Final relevant five-file suite:84passed, one existing warning,14.66seconds; Ruff passed. Intermediate failures remain retained.

A fresh complete backend rerun is active via execution session38484, container mha-goal-backend-regression, log /private/tmp/mha-full-backend-regression-20261013-final.txt. Its result is pending; do not infer a full pass from the84focused checks. No application source was changed by this fixture repair.

Paper-artifact and independent-review import contracts: python3 -m unittest discover -s scripts/tests -v completed15tests,OK,0.906seconds. These validate artifact/label-file correspondence, invalid/tampered/assisted returns and missing-evidence handling; fixture labels do not constitute real human judgments. The novice worksheet now states the current selected-service/model task and pending team session, rather than assuming the superseded local-model default.

## Settled complete backend verification (2026-10-13)

Execution session38484 terminated successfully: Ruff passed; the complete backend suite passed1311tests,8PostgreSQL-only tests skipped, one existing Starlette/AnyIO deprecation warning,221.09seconds. The full final transcript is retained. The eight isolated-PostgreSQL checks are separately covered in the previous24-test migrated PostgreSQL/benchmark-plan run; the current SQLite skip is not an unverified model path or a claimed PostgreSQL pass. All260Python files in the final source manifest were rehashed with no change during the run. The network-disabled container was removed automatically after exit. No real credentials, provider calls, operational database writes or new human labels were involved.

Current broad engineering checks: complete backend1311passed/8isolated-PostgreSQLskips, separate migrated PostgreSQL/plan24passed, complete frontend452passed across55files, selected settled evaluator/judge275passed, script contracts15passed, and actual integrated Luna v5 receipts with strict identity/export correspondence. Their scopes differ: green contracts do not establish independent research validity, a real novice session, actual browser-saved downloads, or repeated formal A/B/C model outcomes. These remain pending rather than implied complete.

## Predeclared repeated Luna engineering smoke v6 (2026-10-13)

The isolated API harness now accepts1–3predeclared repetitions per strategy (default1). All members are registered before a single shared suite freezes; repetition labels are separate metadata and do not change the model, reader policy, source, test budget, seed or retrieval profile. The no-inference verifier now checks all members share the suite and policy, two condition groups have the declared repeat counts, and independently recomputes condition means/population standard deviations and dimension denominators from saved results before comparing JSON/CSV. Missing decisions remain unmeasured, with no substitution of zero. Twenty script contracts passed; Ruff passed. The aggregate helper also checked the original v5 single-pair exports, without invoking the historical full-runtime verifier or changing those files.

Actual v6 run is active in execution session7557. Command: docker compose exec -T backend python /scripts/smoke_luna_isolated_api.py --repetitions 2 --output /tmp/luna-repeated-isolated-api-v6-2026-10-13.json --snapshot /tmp/luna-repeated-isolated-api-v6-synthetic-only.db. Host observation log:/private/tmp/mha-luna-repeat-api-v6-20261013.log. The script creates its only application engine after selecting a new temporary SQLite file. It reuses exact SHA-bound user approval of8synthetic facts/3edges and produces no new independent human annotation. Source/approval fingerprints and declared repetition count are saved before outcomes. No operational database write is intended or performed by the harness. Do not restart because an observation wait expires.

Observed actual progress: extraction, relationship analysis and independent memory review completed and each provider reportedopenai/gpt-6-luna. All4runs registered. Shared four-dimension generation and the first target execution returnedHTTP200; first blind assessment was active at the last read. This is not a completed repeated comparison yet. All result/export/actual-model verification remains pending terminal status; retain failures and uncertain decisions. Requested seed does not establish provider determinism. This one-source synthetic engineering trial does not constitute formal Experiment B, independent scenario sampling, human gold, or model superiority evidence.

## Completed real Luna repeats and v60 wording repair (2026-10-13)

Actual isolated v6 completed all4runs:Weak/Strong each2repetitions, same4question frozen suite and same Strong reader policy. Every model-backed role and all16target/16judge calls reportedLuna;4diagnostic calls completed. The strict no-inference verifier passed exact source-approved inventory/edges, target-store ID separation, reconstructed instruction receipts, repeat membership, JSON/CSV answer/score correspondence, independently recomputed condition means and population standard deviations. Temporary SQLite cleanup confirmed. The separate synthetic snapshot SHA256 is a7bedb5ae0180321a816ae2ff4b0d1527a77938cddcbc5023252deac954581bf. The application source was archived before further evaluator changes, excluding credentials, databases and source history;124files with their content manifest allow restoration of the verifier's original runtime.

Original saved observations:Weak25.0/25.0%,2/8positive,0pending,mean25.0%,populationSD0.0pp. Strong66.7/75.0%,5/7decidedpositive,1pending; descriptive mean70.85%,populationSD4.15pp. Strong repeat1formal overall isnull because Freshness is pending. The available-score mean does not resolve that missing judgment. This is a one-source approved-synthetic engineering repeat, not formal Experiment B, independent sampling, human gold or strategy superiority evidence. Requested seed is not proof of provider determinism. All original scores remain unchanged.

A new v6 reference said “The current system is PostgreSQL; it replaced MySQL, which was used previously and is no longer used for that backend.” The v59local parser incorrectly demanded the tailword“backend” from an answer “PostgreSQL applies now; it replaced MySQL.” Rulev60recognizes both value-first and category-first explicit current-database statements; correct and reversed-answer tests cover database/system/engine/datastore. Selected evaluator/judge regression283passed; Ruffpassed. This is a post-run software change, not part of the original v6runtime.

A separate actual Luna assessment of exactly that one saved question under v60returnedpassedtrue and provider-reportedLuna. It is SHA-bound to the original v6report, targetrequests0, databasewrites0; stored apart from the original archives. It does not replace v6scores or establish improved target memory behavior. The v60delta has focused regression and a real exact-answer reassessment; it has not been subjected to a new full backend suite or regenerated repeated pair. Read-only comparison screens and actual browser downloads remain next engineering work. Team research and real novice records remain pending.

## Actual comparison/export UI acceptance (2026-10-13)

A temporary read-only server mounted the completed v6 synthetic snapshot read-only, blocked all non-GET/HEAD/OPTIONS requests and had empty cloud keys. The current interface was inspected for both actual repeat pairs. Repeat1 showed25.0/66.7%full-suite scores,3comparable decided questions,+33.3pppaired change,1pendingexcluded, and Freshness notscored/no comparison. Expanding Appropriate Use showed exact expected behaviour, both original replies and assessment reasons. Repeat2 showed25.0/75.0%,4comparable questions,+50.0pp,2improvedanswers and1stillfailing. These are saved automated engineering outcomes, not causal/research assertions.

Actual browser download files were obtained for comparisonSVG, reportJSON and reportCSV. The SVG includes saved scope/model/policy labels, counts and Freshness“Not scored” rather than a zero bar. The downloaded JSON/CSV were reconciled with the original savedv6run:all4question/response/evaluation identities, exact prompt/expectation/reply/assessment, source statements, outcome states, selected model/strategy and summary/dimension denominators correspond. Current runtime-version warnings can differ; originalscores remain66.7%,2/3decided,1pending. A separate correspondence receipt retains hashes. This closes the previously unverified browser-save observation for these exports; the earlier failed download-tool observation remains historical.

A real390×844comparison check found long selected audit labels expanded the grid to838px. Scoped minimum/maximum width and full-width select rules now constrain both labels/selects; reread DOM gave390pxpage/viewport and324pxselectors with rightedge357px. The chart remains horizontally scrollable inside its own bounded area. Before/after screenshots are retained; the“narrow”file is the pre-fix failure, and“narrow-fixed”is the corrected view.49comparison/report/chart UI tests passed across3files; production build/typecheck passed with the existing large-main-chunk advisory. This delta was not followed by another complete frontend suite; prior complete452passresult is separately scoped.

Viewport reset, temporary browser tab closed and only the two named inspection containers removed. Synthetic snapshot SHA256 remaineda7bedb5ae0180321a816ae2ff4b0d1527a77938cddcbc5023252deac954581bf. No model calls, writes to the snapshot, operational database modifications or human labels were produced. Real novice and formal A/B/C research records remain team-pending; these automated/browser checks do not satisfy novice usability. Other primary screens and formal experiment workspaces still require release-specific acceptance before claiming all engineering requirements complete.

## Research-workspace acceptance and newly found consent gap (2026-10-13)

The actual v6experiment workspace correctly displayed4/4completed runs separately from questions passed,2condition groups,1pending answer, mismatched score coverage, and decided-answer/measured-run counts. Repeated means matched25%/70.9%display rounding, with0/4.1population standard deviation. A/B/Centry guidance explicitly required independent labels/frozen sources, benchmark actions were disabled with no permitted input, formal thresholds were blank and uncreated plans were not marked complete. These checks do not supply research evidence.

Code inspection found that annotation/prediction/pilot/development/permission file imports could call FileReader without a research-source permission gate. The browser now requires an initially unchecked Research file source authorisation checkbox before reading those files. Import handlers also check a current permission ref; revocation clears loaded source/prediction/development/pilot/receipt state and reports, invalidates file-read/request revision tokens, resets operational-source confirmations and remounts file controls. Validation/pilot dispatch checks permission again. Model calls and storing histories still use their separate existing confirmations. Browser DOM confirmed the three initially visible research file readers disabled and permissionfalse.390pxworkspace pagewidth remained390; internal charts use bounded scrolling.

Repeat error-bar labels now use“pp population SD”, and the caption explains population standard deviation across available scores rather than a confidence interval. A regression was added for that unit and for prepermission read blocking and discarded late validation responses. The first two-file UI run had50passes/2failures (an automated fixture-edit referenced nonexistentuser in a no-upload test, and a forced disabled file event reused the same native selection). Those fixture/control-reset issues were corrected. Final production/typebuild passed; the settled two-file rerun is live in execution session56940, log/private/tmp/mha-research-permission-ui-tests-20261013-final.txt. Do not claim the full UI pass until that handle terminates.

Important remaining NFR1gap: annotation validation, validity-report and pilot-analysis API wrappers currently do not carry an explicit source-authorised flag. The browser-side fix does not establish equivalent direct-API enforcement. This server contract and caller/test migration is the next engineering action. Do not mark all consent boundaries complete. The temporary read-only tab was closed, viewportreset and only its two named inspection containers removed. SnapshotSHA256remain a7bedb5ae0180321a816ae2ff4b0d1527a77938cddcbc5023252deac954581bf. No model calls, real labels or operational writes occurred.

## Research-source server permission enforcement (2026-10-13)

The preceding browser-only permission rerun terminated successfully:52tests passed across ResearchValidation/ResultVisualizations,174.78seconds. This verifies pre-read blocking, clearing/remounting file controls and ignoring an in-flight validation response after revocation, plus explicit population-SD units. It predates the subsequent API argument migration; its result is retained with that scope.

AnnotationImportRequest,ResearchValidityRequest andPilotAnalysisRequest now carry outer source_authorised:StrictBool=False. The annotation-validation,validity-report andpilot-analysis routes reject missing/false permission before invoking their analysis/report service. Strings and numeric truthy values do not count as permission. The API helpers default tofalse; ResearchWorkspace passes its current explicit checked permission. Revocation still prevents the next dispatch and invalidates pending browser material. Saving histories and model calls retain separate existing gates. The short failure message describes the required processing permission without an internal field name; strict-input UI errors use “Source processing permission”.

The no-network disposable backend check passed92tests across research API, pilot, research validity, research matrix, formal design and acceptance tests; Ruffpassed,10.05seconds,one existing Starlette warning. New rejection tests cover3routes×missing/false/stringtrue/numeric1 with their downstream analysis functions replaced by fail-on-use spies. Existing authorized tests still calculate the expected metrics/readiness. This proves declaration and dispatch boundaries, not source ownership/licence, participant permission or reviewer independence. Request JSON must still be parsed/structurally validated to inspect its declaration; no claim is made of refusing to receive raw request bytes.

The flag lives outside the dataset/package, so annotation/pilot content fingerprints and archived files are unchanged. Older direct clients must explicitly add this flag; omission now yields422. API/Development documentation includes examples and migration guidance. No real dataset was replayed or modified. Production/typebuild passed with the existing large-chunk advisory. The final ResearchValidation/API-client two-file regression is live in session25694, log/private/tmp/mha-research-permission-api-ui-tests-20261013.txt; its result is not yet claimed. The previously open direct-API NFR1gap is implemented and backend-tested; final interface/whole-release reconciliation remains next.

Final client-argument verification terminated successfully:50tests passed across ResearchValidation/API client,158.23seconds. Production/typebuild and92backend tests passed as above. Fresh complete backend and frontend reruns were launched on this settled source set; logs:/private/tmp/mha-full-backend-current-permissions-20261013.txt and/private/tmp/mha-full-frontend-current-permissions-20261013.txt. Source content hashes were captured before checking; do not infer current whole-suite success from historical1311/452passes or the focused results. No live model requests are running.

Settled full-regression handles:backend28220,frontend22411. Poll those existing handles before deciding whether another run is needed; an observation timeout is not a failed process.

## Current completion audit and target-boundary repair (2026-10-13)

The proposal PDF Tables1–3 and Sections7.2–7.6 were reread with the PDF skill. The two user-pasted briefs are byte-identical, SHA256d765aff9ce4f248ba874873d21ee472a9b4a8d9ad53bf7a4be764fc3f808ddef. The original scope and the user amendment to the fixed-template baseline remain intact.

Complete backend session28220terminatedsuccessfully:Ruffpassed,1320tests passed,8PostgreSQLskips,one existing warning,777.73seconds. This was before the newly discovered target-adapter isolation fix below. All340source files in its manifest were rehashed unchanged before that fix. Current operational Alembic revision was read-only inspected and is0038_benchmark_plans(head); no migration or data mutation was performed by that inspection.

Complete frontend session22411terminatedwith453passes/3failures across55files(991.58seconds). One accessible-name assertion still expected the obsolete±0%unit after populationSDlabels changed topercentagepoints. The report-recovery test exhausted the defaultshort lookup wait under shared resource load; it now waits a bounded15seconds for the same explicit recovery state. The bounded-repeat input test exceeded60seconds with repeated per-character updates; each invalid value is now pasted as a complete value, keeping all0/6/2.5/3xrejection assertions and valid3run dispatch. No product gate or test coverage was removed. All3files then passed64tests,213.06seconds. Initial failures remain retained. A fresh full frontend rerun is still needed.

Source audit found that the supplemental-source diagnostic branch queried auditorMemoryModelduringanswering. Formal guards already excluded it from primary experiments, but that did not satisfy the user's unconditional target-stage ground-truth boundary. Controlled adapterv3now prepares a diagnostic source packet duringingestfromonlyits original authorised user messages, independent of audit memories, questions, expected answers and review labels. Answering reads only target-owned records. Incoming expectedbehaviour/supportingmemoryIDs are cleared before retrieval and provider execution. Packets remainDIAGNOSTIC_ONLYand excluded from ordinary ranking; this remains an exploratory input intervention, not a production repair, demonstrated failure cause or held-out outcome. Existing records/scores are untouched and previous adapter versions remain historical.

Source replay respects the frozen record count and character budget. An oversized full source is explicitly rejected before store ingestion/modelwork; remaining ordinary records are included only while both limits allow. Missing user messages return422; unauthorised source returns403beforeinspection/ingestion. Missing original timestamps are shown astimenotrecorded, not relabelled from ingestion times. A SQLAlchemy event guard fails on any auditorMemoryModelquery duringtargetingest/answer. Poisoned auditor facts and expectedanswers never reach captured target input. Record limits1/3, budget overflow, absentuserhistory and missingpermission are covered. Final119plusboundarychecks became122passed across6files,40.52seconds;Ruffpassed. The initial role-case/stub and profile-mirror fixture failures are retained. This is simulated transport/contract evidence, not a new Luna target trial or new human annotation.

The diagnosticv3delta has focused verification; the previous1320whole-suite pass does not certify this later code. The original real Luna v6receipts and its frozen source archive remain unchanged. Fresh full settled regressions remain necessary before a whole-engineering completion claim. Formal A/B/C outcomes, independent labels/adjudication and authorised LongMemEval plus novice sessions remain team-pending.

A separate complete frontend rerun was launched after the64test repair check, log/private/tmp/mha-full-frontend-after-regression-repairs-20261013.txt. Source manifestcaptured; no complete backend job runs concurrently. Full backend v3verification should follow its terminal result rather than being inferred from the preceding1320/122checks.

Live complete frontend handle94016; inspect its existing session/log before dispatching a new test run. No model inference or other complete regression process is live at this point.

## Current normal target-input correspondence (2026-10-13)

A no-inference/no-database check rebuilt16originalv6normal target instructions under currentcontrolled-adapterv3, explicitly clearing expectedbehaviour and supportingauditmemoryIDs. Every hash matched its actual stored memory-input receipt. The proof is SHA-bound to originalv6report and states its limits:originally observed target-owned retrieval contexts were supplied; current retrieval/execution was not replayed, historical runtime was not recertified, and no verdict/score was changed. This establishes that clearing those unused private fields does not change the instruction renderer for those actual inputs; it does not certify all future cases.

The complete frontend rerun remains live in94016. All source entries in its frontend manifest were rehashed unchanged. No second complete regression or model process was started while that run is active. Latesttargetv3focused122passresult remains separately scoped from predecessorcomplete1320passresult.

## Settled complete frontend acceptance (2026-10-13)

Existing session94016terminatedsuccessfully:55files/456tests passed,608.40seconds, no skipped tests. Its119frontend source/test/style manifest entries were rehashedunchanged. This supersedes the previous453pass/3failrelease result for the repaired test contracts; the failed transcript remains retained. The final production/typebuild had passed after API-permission migration; remaining repairs changed test assertions/input delivery only.

A separate current backend complete regression is live in session37119, log/private/tmp/mha-full-backend-target-isolation-20261013.txt. It includes controlled-adapterv3, source-budget/authentication edge checks and all other backend contracts in a no-network/no-production-database container. A current app/test source manifest was captured. The earlier1320complete pass predatesv3;122focused checks and16saved-input renderer equivalence are not a substitute for this new complete pass. Poll the existing handle; do not restart on observation timeout. No model job is active.

## Settled complete backend and current live Luna workflow (2026-10-13)

Existing complete backend37119terminatedsuccessfully:Ruffpassed,1325tests passed,8dedicatedPostgreSQLchecks skipped,one existing Starlette warning,244.26seconds. All222app/testsource manifest entries rehashedunchanged. This is the complete controlled-adapterv3source-budget/auth/isolation runtime, not the prior1320result. Complete settled frontend456tests/55files also passed. No operational database changes or model calls occurred in either regression. PostgreSQLschema/API integration was separately checked earlier; no new model/table migration was introduced byv3, while a latest dialect rerun would give stronger whole-runtime evidence.

The requirement matrix's87backtick file references resolved to existing implementation/test/document files; existence is not a feature-passclaim. Proposal/user scope and pending independent research/novice evidence remain intact.

Actual current-runtime v7Luna workflow launched only after both complete regressions terminated. It reuses the exact approved synthetic8facts/3edges, predeclares2repetitionsperWeak/Strongpolicy and preregistersall4runs before shared generation. Command:docker compose exec -T backend python /scripts/smoke_luna_isolated_api.py --repetitions 2 --output /tmp/luna-current-isolated-api-v7-2026-10-13.json --snapshot /tmp/luna-current-isolated-api-v7-synthetic-only.db. Hostlog:/private/tmp/mha-luna-current-api-v7-20261013.log. This creates a new disposableSQLitebeforeappimport, makes realOpenRouteropenai/gpt-6-lunacalls,and writes no production data. No independent human labels are created. The trial terminated unsuccessfully during generation; the terminal outcome and subsequent bounded probe are recorded below.

v7 execution handle80428 terminated with exit1. No successful current-runtime end-to-end result is claimed.


## Current v7 failure and safe completion error receipts

The complete v7 trial terminated with exit1. Extraction and coverage planning completed; relationship analysis, independent memory review and test generation did not complete. No target answers were requested. The original failure report is preserved at `evidence/luna-current-isolated-api-v7-failed-2026-10-13.json`; the temporary database was cleaned, with a separate synthetic-only failure snapshot retained. The previous successful v6 remains historical evidence for its frozen runtime, not a substitute for this failed current-runtime trial.

A subsequent single approved-source relationship probe made exactly one HTTP request with no production database writes or target requests. Its receipt records HTTP200 with a top-level provider error, no reported model or token usage, and safe mapped status502. This confirms an error envelope for the probe, not the precise cause of the earlier v7 failures; the provider's underlying error code was absent or unrecognised by the safe classifier. It establishes neither model incapability nor a billing, configuration or rate-limit cause. No automatic trial retry was dispatched.

OpenRouter documents that completion errors can appear in HTTP200 bodies, at the top level or in a choice: https://openrouter.ai/blog/tutorials/model-routing-for-support-bots-cheap-first-faq-handling/ . Pipeline, target and assessment clients now reject these envelopes even if partial content parses. The pipeline meter v2 and stored Agent receipt retain only safe error scope/status and choice count, excluding raw provider messages and credentials. Focused Ruff plus157tests passed. The complete1325-test backend result predates this delta; the fresh no-network temporary-database regression completed: Ruff passed,1340tests passed,8dedicated PostgreSQL checks skipped,one existing Starlette warning,304.40seconds. All223app/test source hashes remained unchanged. No model calls or production data writes occurred. The456-test complete frontend result remains applicable to unchanged frontend source.

The team explicitly replied “团队后补” for independent human annotation/adjudication, authorised LongMemEval material and licence/citation, and genuine novice acceptance observations. These remain pending research evidence. Synthetic approvals and software checks do not replace them.


## Provider error shape verification

A bounded follow-up probe refined the prior502 ambiguity. The actual top-level error object contains code502, message and metadata; the502 is an observed numeric provider code, not merely a default for an unrecognised code. Safe message-category matching did not identify funding, output budget, routing, unsupported parameters, schema, rate limiting, authentication or a recognised upstream-failure phrase. This does not rule any cause out. Only the error shape and execution receipt were retained; raw message/metadata were not stored. The probe made one real relationship request, no target requests and no production writes. Its initial setup failed on a source field name before any network request; the corrected setup then ran once.

Read-only official endpoint discovery at https://openrouter.ai/api/v1/models/openai/gpt-6-luna/endpoints confirms the model is listed and routes advertise structured_outputs/response_format and output limits above the4096-token request. This is a public capability declaration, not proof that our particular request succeeds or that every JSON schema is accepted. The current client disables upstream fallbacks and requires parameter support; these frozen routing controls remain in place. No full trial was repeated and no model/provider substitution was made. The current engineering end-to-end acceptance remains failed/pending, while independent research evidence remains team-pending.


## Confirmed peak-load budget rejection and bounded output control

A further one-call diagnostic retained a credential-redacted top-level message: the service was under high demand and rejected a request exceeding peak-load maximum usage size, suggesting provisioned throughput. No provisioned throughput was purchased or enabled. The prior shape probes used saved database UUIDs rather than extraction-stage M001aliases; they diagnose HTTP/service handling only, not a faithful original stage replay. A1800budget probe produced valid model JSON but failed the candidate-ID gate for that diagnostic-input mismatch. A corrected M001alias probe at1800completed all relationship gates with the approved facts/source evidence unchanged. Preserve this distinction; neither a UUID probe nor a single successful relation proves the full workflow.

Implemented optional `PIPELINE_MAX_OUTPUT_TOKENS` for OpenRouter pipeline roles, range256–12000; unset preserves existing budgets. Effective limit is min(role limit,cap), or cap for an unbounded role. Declared/cap/effective values are saved in safe execution receipts; cap is part of formal runtime freeze. No evidence shortening, output-contract relaxation, rule/model fallback or automatic capacity retry. Peak-load502receipts use safe categorycapacity_limit and actionable advice. Extraction-stage failures now retain this sanitised service detail rather than a misleading instruction to correct the source. Ruff and105focused tests passed, including budget freeze and error-summary regressions. The fresh complete backend regression for this delta completed: Ruff passed,1352tests passed,8dedicated PostgreSQL skips,one existing Starlette warning,216seconds. All224app/test source files remained unchanged.

Actual v8fullworkflow with2planned repetitionsperstrategy and process-scoped1800cap terminated at extraction with HTTP502capacity_limit; no candidates, test generation or target answers were completed. Original failed report and synthetic-only snapshot were saved; disposable DB cleanup is confirmed. The1800single-relation success does not guarantee peak-load capacity for extraction. The operational `.env` was not changed and no service was restarted to apply this experimental cap. The current fullworkflow remains blocked by observed provider capacity, and formal research materials remain team-pending.

The original failedv8runtime is preserved in a122app-file archive whose source hash exactly matches its original receipt; only the later error-summary edit was reversed in archive bytes. Failure snapshotSHAverified. Current working tree retains the corrected error message. Full frontend456tests remain the earlier unchanged-frontend evidence, not a new run.


## Final bounded route/capacity follow-up and requirement consolidation

Previous goal turns made engineering progress (HTTP200error detection, safe diagnostics, output-cap configuration and full1352-test regression), while the same unavailable-fullworkflow condition persisted. A current-state revalidation found no code drift and no live previous job. One1200-budget v9complete trial kept all source evidence, four-dimensional requirements and2repetitions/strategy. Extraction and independent review completed; relationship analysis and the512-output-budget coverage planner failed with actual capacity_limit502. No target answers were produced; cleanup confirmed. Smaller output budgets therefore do not establish current service usability.

One predeclared same-Luna upstream trialv10used the display nameOpenAI and returned upstream404; its API-level wrapper returned502. Official routing docs specify provider slugs, so corrected v11usedopenai. It also returned upstream404 at extraction and terminated with no target replies. This does not prove the exact account/provider cause; request/account restrictions can combine, and public endpoint declarations are not callable-account evidence. Source: https://openrouter.ai/docs/guides/routing/provider-selection . No account privacy/guardrail changes, alternative model, provider fallback or operational `.env` modification were made. All three failed trials have source-bound archives and original reports; v9/v11snapshot hashes verified against preserved originals.

The active requirement matrix was consolidated into25current FR/NFR/AC/A/B/C rows plus6proposal assumptions/constraints, each with implementation, verification scope and outstanding evidence. The entire prior matrix is preserved in REQUIREMENT_TRACEABILITY_HISTORY_2026-10-13.md so superseded live-session notes do not act as current acceptance claims. No new successful liveworkflow, formal research acceptance or novice observation is inferred.

The remaining genuine blockers are the unavailable current Luna workflow under observed provider capacity/route responses, and team-pending independent annotation/adjudication, authorised LongMemEval material/licence/citation and genuine novice records. Repeated identical attempts or substituting a smaller study would not satisfy the objective. Meaningful completion now requires external service availability/a callable same-model route and the promised team evidence.


Last route checkv12used publicslugamazon-bedrock, which publicly declares max_tokens and structured-output support for Luna. Its real extraction request nevertheless returned upstream404(APIwrapper502), with no candidates/target replies; the disposable database was cleaned. This is account/request-specific observed availability, not a claim that public Bedrock/Luna does not exist. Current frozen archive matches its source signature and synthetic snapshotSHAverified. Backend224sourcefiles and frontend119sourcefiles revalidated unchanged. User input requested only for a currently callable same-Luna route or notification of service recovery; the team-pending research-material request was not repeated.

Blocked audit: across three consecutive goal turns, the current fullworkflow remained unavailable despite verified error handling, complete regressions and bounded unchanged-scope budget/route trials. All jobs are terminal. Proposal acceptance is not achieved; the remaining service and genuine research-evidence conditions require an external-state change or user/team input. Do not continue with identical model trials or declare success from historicalv6/contract tests.


## User-requested service retryv13

The user requested another attempt. One default-route same-Luna complete synthetic workflow was run with process-scoped1200pipeline cap, exact approved source,2predeclared repetitions/strategy and a disposable database. Extraction, relationship analysis, coverage planning, four-dimensional suite writing and semantic review completed. Independent memory review failed with explicit capacity_limit502. Target execution then returned502with the generic provider-completion error; its precise cause was not recorded by the target connector, so it is not asserted to be a proven capacity error. The job terminated unsuccessfully; no fullworkflow or assessor/repeat completion is claimed. SnapshotSHAverified and disposable DBcleanupconfirmed. Original report source signature matches the saved1200frozen source archive; operational data/configuration unchanged. This is improved partial service availability, not a passed engineering or research trial.


## Target failure receipts and verified recovery boundary

The preceding resumed goal turn made progress: actualv13generation and2target replies. Its terminal502could not be retrospectively attributed to capacity because the old target connector discarded safe envelope classification. Current target connector now gives explicit capacity advice and attaches only safe error scope/status/category, HTTPstatus, attempts, elapsed time, output budget and prompt/input hashes to target failures. Target failures are persisted as target_answerAgent executions, without fake response text or lost prior replies. Empty target replies also use the failure-receipt path. HTTP200error envelopes are not automatically retried. Original genericv13failure remains generic; it is not reclassified without evidence.

Ruff and60focused tests passed, including a third-call failure preserving two prior replies, a distinct failed-test receipt, raw-credential exclusion and evaluator-reference isolation. Complete final backend:1355passed,8dedicated PostgreSQLskips,one existing Starlette warning,236.95seconds. All224app/test hashes unchanged. Unchanged frontend456test evidence is retained; no new UI test run is claimed.

One database-free current-connector probe reconstructed the sole unfinishedv13target input using the saved selected target-owned records, cleared evaluator-private fields, retained the original512output budget and made one real Luna request. It completed. It did not retrieve anew, import gold into target context or write either database. This is a single-input diagnostic, not a fullworkflow pass.

Recovery in a disposable copy first correctly failed the runtime-freeze compatibility check after the diagnostic source change; no model call occurred and both saved replies stayed unchanged. A subsequent isolated process restored only the saved originalv13source package, verified exact original runtime signature, and used another copy of the original snapshot. Public retry passed the software guard but target execution returned502again. No completed model request was repeated; two original response rows remained byte-for-byte equal, the original snapshotSHA stayed unchanged and temporary DBcleanupconfirmed. No operational code was reverted and no compatibility guard was bypassed. The recovered failure is kept separate from the originalv13and current single-input success.

Full current audit/repeated-model acceptance remains incomplete, and genuine independent labels, benchmark materials/permission/licence/citation and novice observations remain team-pending. This is the second resumed goal turn; engineering progress does not restart or complete missing research evidence.


## Third resumed goal-turn completion/impasse audit

Previous turn was progress, not a wait/status restatement: target failure receipts were implemented and1355tests passed; actual one-input success and exact-source recovery failure were preserved. Current revalidation confirms all224backend and119frontend source hashes unchanged, no livegoal regression container, terminal trial handles, valid current archive/failure snapshot hashes and all25explicitrequirement rows. The recovery provider detail is exactly a target-provider completion failure, not an input/runtime rejection after restoration. No new completed fullworkflow or team research material is available.

The same unavailable-complete-workflow condition has persisted for3consecutive resumed goal turns, counting the user-requestedv13attempt. Independent labels/adjudication, authorised benchmark materials/licence/citation and novice records remain explicitly team-pending. A passing single question and software checks cannot satisfy missing broad acceptance. The objective is not achieved. Further completion requires external service/route availability and the promised genuine research evidence; identical repeated calls, a reduced study or invented labels do not resolve the blocker. Original data, old failures and saved responses remain preserved.


## Resumed current-runtime full workflowv14–v16 and operational budget application

After intentional interruptions, goal status was active and no old goal-regression container remained. Current1355-test source binding was unchanged. A fresh default-route1200trialv14completed all3extraction roles, the full frozen4dimension suite,16target replies,16assessments and JSON/CSVexports. Two diagnostic calls ended with provider-reported finish_reasonlength at1200; this is output truncation, not a proven new capacity error. Original v14is preserved aspartial_diagnostic_failure. Read-only core verification passed; it is expressly not full-diagnostic acceptance. The original CSV was recovered byte-for-byte from the preserved report request body and matched its recordedSHA; original bundle also preserved from the report.

An1800trialv15was observed complete, and strict verification returnedpassed. Its full temporary report/exports/snapshot and verification file were not copied before backend recreation and were lost. This is an artifact-preservation error, recorded separately; terminal summaries alone are not used as a reproducible full-receipt archive. Originalv14partial evidence and earlier preserved failures remain intact.

Before applying the tested1800setting, the operational PostgreSQLdatabase had0granted stage locks. OnlyPIPELINE_MAX_OUTPUT_TOKENS was set in the ignored.env; keys/model settings were not changed. Only the backend was recreated; database/other services were not recreated and orphan services were not removed. Before/after row counts matched:conversations13,memories48,audit_runs18,test_cases135,target_responses0,evaluation_results0,agent_executions2; schema remained0038_benchmark_plans. These checks establish unchanged counts/schema; no claim is made that counting rows is a full content audit. Restarting the backend cleared its ephemeral/tmpfiles, hence the artifact-loss disclosure above.

Replacement current-runtimev16uses the actual deployed1800configuration and writes reports/exports/synthetic-only snapshot directly to a mounted workspace directory, which is ignored byGit. All evidence was then copied to docs/evidence; its snapshot and122app-file frozen source are also stored in one durable ZIP. Full workflow completed:Weak/Strong each2repetitions on one shared4dimension suite,16real target replies,16real blinded assessments,4completed diagnostics,all3extraction roles completed,and no failedAgentstage. Strict reported-model/own-store input/policy/suite/repeat/JSON/CSV verificationpassed. All actual role/target/assessor identities areopenai/gpt-6-luna. Production writes bysmoke0; disposable DBcleanupconfirmed; current224backend app/test sources remain the1355-test source. Unchanged frontend retains456tests/55files and older actual-browser evidence.

Eachv16run has1uncertain judgment,4total. Those unscored judgments are preserved; formal_overall_score isnull for all4runs. Provisional scores33.3Weak and66.7Strong are based only on decided answers, not formal research results. No independent label, human gold, held-out result or causal strategy effect is inferred. This resolves the prior engineering whole-workflow evidence gap for the exact approved synthetic fixture/currentsettings, not every possible future input or provider-capacity condition. Two repeats do not satisfy formalB's3repeat requirement. Independent annotation/adjudication, authorisedLongMemEval material/licence/citation and genuine novice records remain team-pending; full objective is not complete.


## Actual v16browser/export walkthrough and rulev61correction

Actual current frontend displayed preservedv16Weak33.3%(1/3decided,1pending,4answers) andStrong66.7%(2/3decided,1pending,4answers). Paired comparison correctly showed4sharedquestions,3comparable decided,1improved,0regressions,1stillfailing andFreshnessnot-scored/no-comparison. ActualSVG/JSON/CSVdownloads completed; all4question/answer/evaluation identities, decided denominators and source-backed texts matched the original frozen result. SVGper-dimension counts sum to3decided questions per side. JSON intentionally omits a duplicated result.reproducibility.target_memory_profile but preserves retrieval/output controls in sanitizedrun_configuration; this is not a changed answer/score. Screenshot andDOM retained.

The first attempted internal-only Docker network did not publish a localhostfront-end port. It was replaced with a temporary publish network for the frontend, while the snapshotbackend remained internal, read-only,GET/HEAD/OPTIONS-only and withoutcloudkeys. The agent tab and both namedinspection containers/networks were removed. No models called orDBwrites during viewing/download; snapshotSHAand119frontendsourcehashesunchanged. Genuine novice observations were not created.

The visibleFreshnessexplanation showed a deterministic rule defect: the reference“currentrecord saysPostgreSQL isused…historicalrecord saysMySQL wasusedpreviously” fell through to the generic lastwordpreviously. This falsely passed the old/unknownWeakanswer and failed correctStronganswers. Rulev61selects a known database only from an explicit affirmative current-record present-tense clause, rejects historical/negated generic tails, and detects an explicitly wrong passive current database assertion. Initial new reverse-answer tests found2remaining failures; the assertions were retained and the contradiction guard fixed.315focusedtests andRuffpassed; fullbackend1366passed,8dedicatedPostgreSQLskips,one existingwarning,218.69seconds;224app/testsourcehashesunchanged.

A zero-model/zero-DB-write rulev61supplement reassessed the4originallypendingv16Freshnessanswers and matched each saved semantic verdict (Weakfalse,Strongtrue). Originalv16pendingresults and scores were not overwritten, and no humanlabels/gold were fabricated. OriginalSourceArchive remainsv60; itsfullworkflow is not evidence of the later source delta.

A separate coldcurrentv61fullworkflowv17then completed allroles with actualLunaidentity,16targets,16assessments,4diagnostics,2repeatsperpolicy,onefrozen4dimensionsuite,stricttarget-owned input/policy/model/repeat/JSON/CSVverification andsnapshot/sourceZIPbinding.2conflict-resolution judgments remain uncertain, retained outside formaloverallscore; their rule/semantic disagreement is not resolved by theFreshnessfix. No new v17browser walkthrough is inferred from thev16screen check. This is engineering-only, not independentresearch; formalA/B/Cand genuine novice/source/label evidence remain team-pending.
