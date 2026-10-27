# Phase4 engineering follow-up — 27 October 2026

Status: **engineering fixes and additional verification completed; formal human-reliability/discovery validation remains partial**. This work follows the user's request to continue after identifying six ambiguous questions and unclassified failures. Final Report, Word and presentation materials were not edited.

## Changes and root causes

1. Updated-database accuracy questions asked about a “recorded” value while their references required the current replacement. Historical MySQL replies could therefore be true but incomplete under an unstated temporal scope. New rule generator v28 explicitly asks for the current value on UPDATE-backed database facts. The direct/fixed/contextual generators have distinct new versions v4/v3/v2; contextual current-state profiles also make temporal scope explicit. No answer value is included in the prompt. The inventory schema accepts historical fixed-template-v2 releases and new-v3 releases. Previous test assertions were updated only for these deliberate version changes.
2. Evaluator v64 classified affirmative stale-value/override selections but intentionally left most information abstentions untyped. Evaluator v65 adds a bounded source-abstention classifier. It uses the actual question, explicit response abstention and confirmed typed source relationships, never the test dimension, expected-answer string or retrieval metadata. Unique source-backed missing-current-database, missing-project-language and missing-unresolved-region responses can receive a category. Missing keywords alone, truthful history, hypothetical/example prose, absent edges, unrelated projects or ambiguous multi-topic tasks retain abstention. Its reason explicitly distinguishes observed missing answers from their internal cause. This is a bounded rule extension, not general semantic understanding.

Changed production files in this continuation: `backend/app/evaluator/rule_based.py`, new `source_abstention.py`, `backend/app/test_generator/rule_based.py`, `baselines.py`, and `backend/app/schemas/domain.py`. New regressions: `backend/tests/test_phase4_followup.py` (23 parameterised cases). Three existing test files update current generator-version assertions. Weak retrieval and all original research labels/answers are unchanged.

## Verification

| Check | Result |
|---|---|
| Targeted backend evaluator/generator/API checks |371 passed|
| Complete isolated backend suite |2738 passed,8 PostgreSQL fixtures skipped|
| Those PostgreSQL fixtures on isolated migrated test DB |8 passed|
| Existing script suite |37 passed|
| Compilation and diff whitespace |Passed|

The full backend suite uses a disposable SQLite DB and strips real provider credentials; no external network attempts were recorded. PostgreSQL fixtures run against `memory_auditor_stabilisation_20261027_test`, not the application DB. A Starlette/AnyIO deprecation warning remains. Frontend code did not change; frontend tests were not repeated solely for these backend changes.

## Same-answer classification comparison

The ordinary immutable reassessment API created9 new development assessment runs over the exact36 original A answers. Every answer text/source link was checked and every original pass/fail verdict stayed identical. New target requests for reassessment:0. Source A-live SHA256 matches the earlier saved source. Original evaluator-v64 outputs remain intact.

Among the27 AI-assisted/user-confirmed failed memory tasks, classified outputs increased **0/27 →26/27**:8 freshness,9 appropriate-use and9 conflict-resolution omissions. This is development classification coverage, not independently validated classification accuracy. One freshness answer remains unclassified because its coordinated “no current database choice or replacement is recorded” phrasing is outside the narrow abstention pattern; the rule was not loosened merely to type every observed case. The six ambiguous original accuracy questions also remain unclassified and reference-uncertain. No original score was changed to improve a result.

## Six new unambiguous development probes

Six separate ordinary development audits were created for the two histories × three methods affected by the accuracy ambiguity. Each has one clearly current-state question, the original source-supported expected answer, the same target model/reader/profile/Weak strategy, and an explicit one-question evidence coverage contract. They pass the ordinary grounding/quality gate. Human-validity remains pending and their role says development clarification; no formal Experiment A review gate was bypassed or human approval invented.

Actual result: **0/6 pass,6/6 fail**. The answers still omit the current database, and the final memory-input receipts still contain only the historical MySQL record. This demonstrates persistent Weak retrieval omission on these explicit-current development prompts, without establishing which method is superior. These are new answers to changed prompts; they do not retrospectively resolve or replace the original six uncertain cases.

All6 actual request bodies were reconstructed and checked against original HTTP-boundary SHA256, without resending them. Estimated recorded usage$0.0012044, within the original authorised budget, not a provider billing receipt. No paid semantic judge was added.

## Inventory and human-review boundary

Original frozen defect definitions are narrower than several observed omissions. `future-inventory-draft-v2.json` prepares broader omission-inclusive definitions **for future development only**, explicitly derived after observing these outcomes. No human approval or pre-outcome freeze is claimed. These definitions are ineligible for original A's formal discovery denominator. The old inventory and original discovery metrics remain unchanged/unmeasured; matching a question dimension is not a valid response-to-defect mapping.

B's pending independent review material now has readable HTML copies in `B-readable-review/reviewer-1.zip` and `reviewer-2.zip`. Each includes72 actual answers,12 question-validity checks and3 extraction/relationship histories. The frozen JSON materials and blank worksheets are byte-identical to the original packets; method labels and automatic scores remain omitted. Reviewers must disclose prior automatic-result/AI exposure. No human worksheet was filled automatically. Readable copies do not by themselves establish blindness or independent authorship.

Remaining formal work: genuinely independent B response/extraction/relationship references; documented resolution or exclusion rules for the original six uncertain A items; a valid explicit response-defect mapping under a defensible frozen inventory; and independent validation of the new classifier before research reliability claims. A shared AI-assisted review does not supply those independent labels. All possible engineering checks above are completed without claiming full Phase4 certification.

## Reproducibility

Primary evidence directory: `artifacts/local/phase4-followup-20261027/`. It contains targeted/full/PG/script logs, `saved-answer-reassessment.json`, `clarification-live.json`, six verified request bodies, versioned inventory draft, pending B review packets and `verification-summary.json`. `evidence-manifest.json` records new source/evidence hashes and the dirty worktree commit.

Scripts: `reassess_phase4_followup.py` (idempotent saved-answer reassessment), `prepare_phase4_clarification.py` (refuses duplicate probe preparation), `run_phase4_clarification.py` (at most six source-bound one-answer probes), `verify_phase4_requests.py` (request SHA verification), and `prepare_phase4_b_readable.py` (copies original blank worksheets).

An initial reassessment export checker used the wrong result-envelope key; it stopped after the first completed local reassessment. The checker was corrected and resumed from saved records; no target request or evidence was repeated. The initial failure log is retained. No cloud-call failure occurred in the six new probes.
