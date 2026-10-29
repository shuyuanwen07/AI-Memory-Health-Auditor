# Manual review handoff

**Purpose:** identify the remaining decisions that require a person, why the saved AI-assisted or exposed material cannot substitute for that review, and the exact records to review. One complete 216-item human return has been received; its author disclosed AI assistance and exposure to automated results, and declared that it was not completed independently. It can inform corrections but does not count as independent validation. This file tracks that return without treating it as a formal pass.

For one consolidated working file, use [`HUMAN_REVIEW_MASTER_2026-10-28.json`](../../output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json). It contains 686 records across the open A/B, C archived/v5/v6, tutor-loop and intake-candidate queues, with source evidence and blank review fields, plus project-level confirmation forms. The source CSVs and original review materials remain preserved unchanged. The JSON records previous exposure limits: team review can correct labels but cannot be reported as unexposed independent blind evidence.

The archived experiment protocol and study results have already been inspected. They cannot be relabelled as prospective or held-out. The current formal protocol file is a freeze template; Phase 4 `protocol.json` records `B.success_threshold: null`. A pilot-derived threshold can only be filled after the eligible human pilot labels are returned, before a new held-out matrix is created or inspected.

## 1. Fresh intake review in the app

The post-fix synthetic intake retest is visible on [New audit](http://localhost:5173/new-audit). Review all **14 candidate memories** against their cited source messages and choose accept, edit, or reject for each. The second-source agent raised two advisory items: one candidate may state a broader project relationship than its messages support, and one possible preference may be missing. These are prompts for source checking, not automatic verdicts. None of the 14 memories has been approved, and this conversation has no target-test results yet.

## 2. In-system diagnosis-led retest

The three new Repair Comparison groups are visible at the top of `/experiments`. The candidate runs below contain three answers that the hybrid evaluator left **Uncertain**. Open each saved run and judge the answer against the source messages and expected behaviour:

| Run | Dimension | Test ID | Evaluation ID | App report |
|---|---|---|---|---|
| `RUN5E03C2FF549A457EAB342FF397FF1BBF` | Conflict Resolution | `TDA601B2174D34C81A32AF900256FDA23` | `EDA601B2174D34C81A32AF900256FDA23` | [Open candidate run](http://localhost:5173/audits/RUN5E03C2FF549A457EAB342FF397FF1BBF) |
| `RUN1D713A111D1B499A844160F3F2F0665E` | Conflict Resolution | `T2BBDE3109ABA46D780D4D944301F8440` | `E2BBDE3109ABA46D780D4D944301F8440` | [Open candidate run](http://localhost:5173/audits/RUN1D713A111D1B499A844160F3F2F0665E) |
| `RUN1D713A111D1B499A844160F3F2F0665E` | Appropriate Use | `T92089F57410543EA84CDD7F54E8D134A` | `E92089F57410543EA84CDD7F54E8D134A` | [Open candidate run](http://localhost:5173/audits/RUN1D713A111D1B499A844160F3F2F0665E) |

For a source-based independent check of the improvement, use the prepared [36-answer blind review packet](../../output/proposal-delivery/live-repair-loop-2026-10-28/BLIND_REVIEW_INSTRUCTIONS.md). Give the reviewer only `blind-review.csv` and its instructions. Do not provide the reproduction JSON files or `review-key-private.json`; the key discloses conditions and automated outcomes. The current project team has already seen the results, so its later review is useful manual validation but cannot be described as an independent blind review.

## 3. Current-source diagnosis-led retest

The latest tutor-loop group is [current-source group `EXP627CCD21BC1D465996A30FF0E630739B`](http://localhost:5173/experiments/EXP627CCD21BC1D465996A30FF0E630739B). It uses the delivered application digest `7d303324…`, one synthetic history and the same frozen eight-question suite in the original, generic-control and targeted-retrieval conditions. The paired app comparison is [open here](http://localhost:5173/compare?before=RUN42167A38184D40EE8E7AD2A79C25E8DB&after=RUNBA08475F1AD241D883BC811BC85C7652).

The source-based [24-answer review worksheet](../../output/proposal-delivery/live-current-source-repair-2026-10-28/human-review/BLIND_REVIEW_INSTRUCTIONS.md) includes the question, expected behaviour, cited source excerpts and target answer, while omitting condition, run ID, model and automatic judgment. Give a reviewer only `blind-review.csv` and its instructions; keep `review-key-private.json` with the custodian. The public packet has zero labels. The project team has seen the results, so its later review must be reported as exposed manual validation, not as independent blind evidence. Across the three conditions, five of 24 answers remain uncertain; review all 24 rows against the source before using any label as a reference.

## 4. Current-source six-run comparison

The latest application-bound result is [group `EXP77CB1B845E75465ABDF7C8FC986113E4`](http://localhost:5173/experiments/EXP77CB1B845E75465ABDF7C8FC986113E4), with 48 target answers: 38 decisive automatic labels and 10 uncertain answers. A new source-based worksheet is ready under [`live-presentation-demo-current-source-2026-10-28/human-review/`](../../output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/human-review/). It includes each question, expected behaviour, source excerpts, and target answer, but omits run IDs, conditions, repetition, model identity, and automatic decisions.

For a genuinely blinded first pass, give a reviewer only `blind-review.csv` and `BLIND_REVIEW_INSTRUCTIONS.md`; keep `review-key-private.json` with the custodian. The team has already seen the scores, so team-member review must disclose exposure and is useful for correction, not independent blind evidence. This worksheet does not substitute for the separate 216-item A/B/extraction review or the 84-answer C review, and it does not establish AC1 or AC3.

## 5. Proposal A — test validity and distinct-defect discovery

The saved A study executed the three planned methods, but its manual-reference record is retrospective and incomplete. The current cross-review leaves **13/48 test-validity decisions uncertain**, **6/36 response labels unresolved**, and **2 failure-category mappings disputed**. The distinct-defect discovery rate remains null because unresolved response-to-defect mappings change which distinct defects count as discovered. Category coverage also cannot be asserted for a method/history cell until its tests are judged valid.

For the full AC1/A/B review, use the two prepared packets under `artifacts/local/phase4-formal-review-20261027/reviewer-{1,2}.zip`. They contain 216 blinded items: 108 A/B responses, 48 questions, 27 extraction candidates, 24 proposed source-reference units, and 9 relationship pairs. The returned reviewer-1 worksheet is complete, but it is AI-assisted and result-exposed; the AI-generated reviewer-2 file is not a human return. Two new reviewers who have not seen the automatic scores or each other's decisions must complete fresh packets before an independent consensus can be calculated. Each packet's `review.html` explains source citations, validity judgments, response labels, reference completeness, and explicit A defect mappings. Keep the private condition key with the custodian.

Complete test validity and response correctness independently against the original source; then adjudicate the disputed mappings and recompute recall, category coverage, and discovery rate with explicit denominators. Use a reviewer who has not seen these outputs for any claim of blind independent review. If you or another team member has seen results, disclose that exposure; the review can still correct/confirm labels but must not be counted as an independent blind return. Existing exposed/AI-assisted returns can inform discussion but do not count as independent gold.

## 6. Proposal B — human answer references and frozen gates

The B target run is complete: **72 canonical answers** across the paired Weak/Strong settings and three repeats. Current retrospective comparison resolves **71/72** answers (TP 27, FP 1, FN 8, TN 34); one automated-uncertain failure remains outside the decisive confusion matrix. The source review that supplied these labels was AI-assisted and post-exposure. Therefore the target score comparison is usable as exploratory evidence, but it cannot establish independent Auditor precision/recall, classification accuracy, or false-positive rate.

Have the two independent reviewers label the frozen B answers against the source using the 216-item packets above; adjudicate disagreements without seeing the automated outcome where the adjudication protocol permits. The saved Phase 4 `protocol.json` has `B.success_threshold: null`; its 72-answer Weak/Strong comparison is not itself a frozen Auditor-validity study. The formal synthetic-pilot workflow requires a ready, source-verified double-annotation package, then freezes the four threshold values with a server timestamp and dataset/runtime fingerprints before creating and running the held-out matrix. Use the [formal protocol template](../FORMAL_EXPERIMENT_PROTOCOL.md) for that workflow. Do not infer a threshold from Release 20's 75% target-memory gate or backfill a threshold after seeing the same held-out outcomes.

## 7. Proposal C — external-ranking compatibility

The local ranking comparison is already calculated from the saved proposal B and archived C runs. B’s four-dimension Auditor macro and C’s upstream-prompt-compatible LongMemEval score both rank Strong above Weak in all **3/3 repetitions**. The archived C collection contains 84 answers and 84 usable judgments on 14 of 500 Oracle cases; this is a completed local compatibility ranking check, not a full official benchmark result. Do not pool it with the separate C v5 candidate.

For a source-based check of the benchmark grader, use the prepared [84-answer review packet](../../output/proposal-delivery/phase4-c-review-2026-10-28/BLIND_REVIEW_INSTRUCTIONS.md) and `blind-review.csv`. The public sheet omits condition, repetition, run IDs, and automatic grader decisions. Keep `review-key-private.json` with the custodian; do not send it to reviewers. The project team has seen aggregate results, so team review cannot be described as unexposed or independent. Human review calibrates the saved benchmark judgments; it does not change the recorded 3/3 automated rank result or establish full-benchmark generalisation.

## 8. Project-level human confirmations

- Each member completes their own evidence-based entry in [MEMBER_CONTRIBUTIONS.md](MEMBER_CONTRIBUTIONS.md). Planned role descriptions do not prove completed work.
- A team member confirms the benchmark/data licences, source permissions, cloud-processing permission where relevant, and citation details for the final shared package. A local hash proves file identity, not permission.
- The responsible reviewer confirms that AI-assisted handoff labels are not described as independent human gold.

## Completion rule

For each new review return, preserve the original file, record reviewer exposure and AI assistance, hash the inputs, and run the saved structural validation. Calculate consensus metrics only from the required eligible independent returns and adjudication evidence. The 28 October assisted return is already recorded as a separate descriptive source; it does not qualify toward the two unexposed independent reviews. Until those reviews, the source checks, and the specified human confirmations are complete, keep the affected proposal items pending and do not promote exploratory values to formal acceptance claims.
