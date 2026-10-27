# Phase 4 evaluation status — 27 October 2026

Status: **partially complete**. B and C automated candidate collections finished. Experiment A is prepared but has not executed. Independent human reliability metrics remain unmeasured. The user confirmed that two real independent reviewers can provide results later and chose to review A's pre-execution materials later. These pending declarations have not been fabricated.

## Code and validation

Phase 4 adds frozen collection, recovery, request verification, review preparation and analysis scripts. Production application files have not changed since the Phase 3 source freeze. Final Report, Word and presentation files were not edited. Current source is the dirty worktree at `b44ced90ea39eb569eaa6ea01dee4c3df5712085`; `protocol.json` binds every production Python source hash. This is additional evidence after Phase 3, not a new before/after repair comparison.

Commands: `python3 -m unittest discover -s scripts/tests -v` → **31 passed**, including six new review-validation tests; `python3 -m py_compile scripts/*phase4*.py` and `git diff --check` passed. The frozen production-source hash check passed. Earlier full application verification remains in PHASE_1_2_COMPLETION_2026-10-27.md and PHASE_3_COMPLETION_2026-10-27.md; those suites were not rerun solely for these experiment scripts.

## B — Weak / Strong automated candidate comparison

Three new authorised synthetic histories, four canonical questions per history, two retrieval policies and three repetitions: **72 included real target answers**. All four dimensions are covered. Both policies use the same Strong reader instruction; only retrieval strategy changes (`weak_first_hit` / `strong_rule_based`). Model is `openai/gpt-6-luna`; rule evaluator is v64; extraction v27; controlled target v35. Capacity50, retrieval maximum50 records, context16000 characters, output2048 tokens, rule writer and update-aware consolidation are shared. Actual INGESTED event writer versions and expanded profiles match C.

Requested temperature0 and recorded seed42 are configuration provenance only. Actual HTTP receipts show **model-default sampling**, with temperature and seed absent. Repetitions are not bit-for-bit deterministic.

| Dimension | Weak pass / decided | Strong pass / decided |
|---|---:|---:|
| Accuracy |9/9|9/9|
| Freshness |0/9|8/8, plus1 uncertain|
| Conflict Resolution |0/9|8/9|
| Appropriate Use |0/9|9/9|

Pooled tested-dimension macro-average: **Weak25.00%, Strong97.22%**. Weak9 pass/27 fail/0 uncertain; Strong34 pass/1 fail/1 uncertain. Strong repetition macro scores100%,100%,91.67%; population SD3.93 percentage points. Weak is25% in each repetition. Uncertain answers are excluded from decided-score denominators and remain explicitly counted.

Mean paired history macro delta is+72.22 percentage points. A descriptive history bootstrap interval is[66.67,75.00] points; exact two-sided history sign p=.25. There are only three template-related histories. These statistics do not establish population independence, confirmatory significance or generalisation.

The sole Strong conflict failure contains both North/South and asks “Which source should govern before proceeding?” It is a **candidate lexical-evaluator false positive** requiring independent review; its original failure label is retained. The uncertain freshness answer states PostgreSQL but adds a Java/course explanation. Its assessment stays uncertain. Human critical-error count is **unmeasured**, not zero.

All72 B request bodies were reconstructed from retained context and verified against original HTTP-boundary SHA256; no reconstruction was sent to a model. The request artifact clearly records this provenance.

## C — LongMemEval local compatibility comparison

Official author Oracle file and original evaluation source were independently downloaded and pinned. Original population500; a response-independent SHA256 rule selects two cases from each of seven strata, **14 original IDs**. All source sessions and reference answers are retained. Each policy runs all14 cases three times: **84 actual answers and84 usable semantic judgements**.

The pinned original `get_anscheck_prompt` and yes-substring parser are used. Judge is dated `openai/gpt-4o-2024-08-06`, user-only prompt, n1, temperature0, max_tokens10, through OpenRouter. Gold answers are available to the grader only; target tests have empty expected behaviour/supporting gold IDs. Original question IDs are retained in `hypotheses/*.jsonl`.

| Repetition | Weak semantic pass | Strong semantic pass | Within-set order |
|---|---:|---:|---|
|1|5/14 (35.71%)|11/14 (78.57%)|Strong higher|
|2|5/14 (35.71%)|10/14 (71.43%)|Strong higher|
|3|5/14 (35.71%)|9/14 (64.29%)|Strong higher|

Across repetitions Weak15/42=35.71%; Strong30/42=71.43%. B and C orderings agree in **3/3 repeated comparisons**, with no ties. The source cases repeat across runs; this is descriptive automated consistency, not three independent external validations. Scores are compared within each question set; no cross-dataset score subtraction is performed.

Limitations: Oracle14/500 only, not full S/M; controlled-memory reader and source adapter; alternate OpenRouter transport for the official judge; no independent human calibration. These are **local compatibility results**, not official full-benchmark scores.

Pinned sources: upstream commit `9e0b455f4ef0e2ab8f2e582289761153549043fc`; dataset revision `98d7416c24c778c2fee6e6f3006e7a073259d48f`. Hashes and MIT licence declarations are in `upstream/source-binding.json` and retained upstream files.

## A and genuine human review

Three durable A comparison plans exist, each with equal four-question caps for direct / researcher-reviewed rule-seeded fixed / contextual-indirect arms. Twelve fixed draft questions, source messages, memory references and nine potential source-defect candidates are prepared. These are **candidates**, not confirmed defects or human-authored labels. No A condition generation or target execution has bypassed the protocol's inventory and human-validity gates.

Researcher material: `artifacts/local/phase4-20261027/researcher-preexecution/review.html` and per-history JSON. Actual research confirmation, two source-inventory reviewers and subsequent question-validity decisions are still needed before A execution. After actual answers exist, genuine independent judgements and a complete response-to-defect mapping are required for Failure Detection Recall / Failure Discovery Rate. Category coverage is not claimed as human-validated.

Two separately shuffled blind review ZIPs include72 B actual responses,12 source-grounded question-validity items, and three histories' original extraction candidates/relationships. They omit strategy names and automated outcomes. The private identity key is not inside either ZIP. Reviewers should work independently, fill `labels-to-complete.json`, use their own pseudonym and return the results. No message has been sent to an external person.

`analyse_phase4_reviews.py` validates distinct reviewer declarations, exact frozen material identifiers, complete item coverage and source citations, retains disagreement and uncertainty, and calculates only supported response/question metrics. Extraction/relationship fact-unit reconciliation and adjudication are separate source review steps; missing annotations remain unmeasured. LLM labels are not substituted for independent human gold.

## Interruptions, cost and reproducibility

Two B provider503 failures and a C provider503 interruption are preserved. A C grader429 interruption and its attempts are retained. Completed C calls are replayed locally only after exact request-body equality; completed grades are not resent. B terminal failures were retained; recovery uses separate runs. One regenerated recovery suite changed an accuracy slot: its four answers are preserved but excluded, and an exact canonical suite was copied through the application service and rerun. All72 included B cases now have matching question/expectation/evidence signatures across policies/repeats.

`recovery-amendment.json` explicitly records the operational retry amendment. Interrupted cases may exceed the original per-invocation attempt count across recoveries, so this is not represented as an untouched formal collection. Failed target billing is unknown. B completed usage estimate is$0.01697; C usage plus conservative failed-grader reserves is$0.09062. These estimates exclude unknown failed-target usage and are not provider billing receipts. No new budget authorisation is inferred or required; observed use remains well inside the pre-authorised$5 and this round's$2 reservation.

Primary evidence: `artifacts/local/phase4-20261027/` contains protocol, source data, B-live/C-live, verified request bodies, raw grader prompts/verdicts, original interruptions, failure ledger, analysis, hypotheses, blind packets and hashes. Reproduce analysis with `python3 scripts/summarise_phase4.py`. Validate actual returns using `python3 scripts/analyse_phase4_reviews.py artifacts/local/phase4-20261027/private REVIEWER1.json REVIEWER2.json NEW_OUTPUT.json`.

## Remaining work

1. Researcher and independent source-inventory review for A, then generate/review/execute its three arms.
2. Receive the two genuine independent returns, reconcile extraction/relationship fact units and adjudicate disagreements without replacing original automated results.
3. Calculate supported Auditor reliability, critical-error counts and A discovery/detection metrics; retain unsupported metrics as unmeasured.

Release20's historical26/36=72.22%, frozen75% threshold and two unverified critical errors remain unchanged. This small candidate collection does not retroactively resolve missing Release20 evidence or certify formal research success.
