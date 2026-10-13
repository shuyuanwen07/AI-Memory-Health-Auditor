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
after 18,351.05 ms. No relationship was inferred in code, and no memory was
confirmed. A human source/relationship review is now requested; its response is
pending. No four-dimension plan, target response, evaluator result or complete
end-to-end audit has been run from this source.

After the refactor, focused extraction/time-contract checks passed:
`PYTHONPATH=backend /private/tmp/mha-qwen-e2e-venv/bin/python -m pytest -q
backend/tests/test_llm_pipeline.py backend/tests/test_memory_source_time.py` —
**46 passed**. Ruff and `git diff --check` passed for the touched files. The
Experiment A/B/C export manifest now labels the archived suite digest
`frozen_test_suite_sha256`; its focused API/export regression passed **1 test**.

The current complete backend check, after the v8 extraction and experiment
export changes, passed:
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
