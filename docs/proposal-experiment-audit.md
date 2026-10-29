# Proposal experiment evidence audit

**Audit date:** 27 October 2026 (Australia/Sydney)  
**Repository revision at initial inventory:** `f9f777ee11813642e280ec1885ab8d867011ebdd`  
**Scope:** This audit began as a read-only review of locally available experiment and handoff evidence. A dated update below records the authorized C candidate run and its analysis; the earlier result files remain unchanged.

## Subsequent evidence update — 29 October 2026

The table and reconciliation below describe the 28 October snapshot and remain historical. Experiment A has since received two user-confirmed independent, score-blind, AI-assisted reviews: the reviewers agreed on 33 failures and 3 passes in the 36 saved answers. Each method exposed and the Auditor detected 3/9 frozen defect IDs; 18 failures per reviewer did not map to that inventory. This is inventory-limited discovery, not discovery across all possible defects. See the [A analysis](../output/proposal-delivery/experiment-a-human-return-20261029-v1/analysis.json). AC3 also has a newer prospective paired retest documented in the [experiment report](EXPERIMENT_REPORT_2026-10-28.md). A new B four-strategy collection completed 36 runs and 144 answers, with human review still pending; it must not be conflated with the older two-policy B result below.

## Current evidence update — 28 October 2026

Remote `main` has since advanced to `40876e47e44f2af18187766a46976fe3bb15c3a5`; it adds `research/evidence-20261027/`, including an experiment archive and readable reports. The archive SHA-256 (`9eb48374b22834370d3c283d531cd66686c8aae9cf1e255610940116f9fb89b4`), ZIP CRC, manifest count (360), every member hash and total extracted bytes were independently checked. After verifying that all archive paths were safe and had no existing destination, its files were restored to their original ignored paths. This supersedes the early local-inventory statements below that A/B files and Phase 4 metrics were absent.

| Study | Current original-run evidence | Supported result | Boundary |
|---|---|---|---|
| A | `artifacts/local/phase4-20261027/A-live.json`, condition map, request receipts, nine exports, frozen defects and review materials | 36 actual target answers (3 histories × 3 methods × 4 questions); the retrospective review resolves 30/36 (27 fail, 3 pass), with 6 uncertain. | The formal distinct-defect discovery rate remains null. Ambiguous questions, unresolved mappings and reviewer-provenance conflict prevent a formal discovery claim. |
| B | `B-live.json`, 72 verified request bodies, canonical suites, recovery logs and analysis | 72 included answers over three repeated First-match retrieval / Relationship-priority retrieval runs. Current retrospective human agreement is 71/72: 27 TP, 1 FP, 8 FN, 34 TN, plus one unresolved; decided recall 27/35=77.14%, or 27/36=75% when the automated-uncertain human failure is included. | Three related synthetic histories, repeated cases, default sampling, and retrospective review constrain inference. Four noncanonical recovery answers remain excluded. |
| C (archived Phase 4) | `C-live.json`, source-pinned Oracle subset, target receipts, official-prompt-compatible grader requests and interruption/recovery records | 84 target answers and 84 usable judgements over 14 Oracle IDs, two policies and three repeats. First-match retrieval 15/42; Relationship-priority retrieval 30/42; Relationship-priority retrieval is higher in all three paired repeats. | Only 14/500 cases, adapted local compatibility run, shared target/grader model family, and no independent human calibration. |
| C v5 (separate local candidate) | `artifacts/local/phase4-c-openrouter-20261027-v5/` | Separately saved 84 target answers and 84 GPT-6 Luna grades; First-match retrieval 12/42, Relationship-priority retrieval 35/42, Relationship-priority retrieval higher 3/3. | Do not merge its answers or scores with archived Phase 4 C. Local lexical proxy is not the Auditor's four-dimension score and is not the formal C ranking comparison. |
| Current-source Auditor demonstration | `output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/`, app group `EXP77CB1B845E75465ABDF7C8FC986113E4` | Six GPT-6 Luna runs (3 per condition), same confirmed synthetic history and frozen eight-question suite. Runtime source digest `7d303324…`, suite fingerprint `4bb4a2…`; First-match retrieval 3 pass/16 fail/5 uncertain, Relationship-priority retrieval 15/4/5. Relationship-priority retrieval has more decided passes in all three pairs. Offline verifier passed six runs, 48 exact input checks, JSON/CSV reconciliation, and all 60 API steps. | Current-source repeat binds to the delivered code, but it uses a single synthetic case and automatic evaluations. Ten answers remain uncertain; it does not establish human Auditor accuracy or replace the separate diagnosis-led tutor-loop results. |

### A status reconciliation

The archived `artifacts/local/phase4-20261027/analysis.json` and its companion
`analysis.log` retain a pre-execution `A_status` string: “awaiting real inventory
and fixed-template review; no formal target execution”. That statement is stale
for the final A target collection. The source-of-record
[`A-live.json`](../artifacts/local/phase4-20261027/A-live.json) reports
`complete_target_collection_independent_response_review_pending`, and
[`A-verification-summary.json`](../artifacts/local/phase4-20261027/A-verification-summary.json)
records 36 completed answers across nine conditions, three histories, and four
questions per condition, with equal target/evaluator settings and budgets
verified. The accurate current status is **A target collection complete;
independent response review, valid-test confirmation, and defect mappings
pending**. The archived analysis and log are left unchanged to preserve their
original hashes and provenance; do not cite their `A_status` string as the
current A execution status.

### AC1–AC3 results derivable from the retrospective review

The current two-return recheck and the preserved retrospective metrics support
the following descriptive counts, but none are independent held-out estimates:

| Criterion | Current descriptive evidence | Formal status |
|---|---|---|
| AC1 — extraction and relationships | 21/27 candidate memories agreed valid; six remain disputed or uncertain. Six reference-coverage decisions remain unresolved, including three “full” claims dependent on unconfirmed candidates, so reference-unit recall is null. Relationship classification is 6/9 (66.67%) on the selected pairs. | Not established: the complete source reference catalogue is unproven, and reviewer provenance is exposed/AI-assisted and disputed. |
| AC2 — grounded test validity | 35/48 questions were agreed valid; 13/48 remain uncertain. The 35/35 (100%) rate applies only to decided items. | Partly evidenced: this does not certify all generated tests as grounded. |
| AC3 — response classification | A: 30/36 resolved (TP27, FP0, FN0, TN3); decided-case precision/recall/F1 100%, FPR 0%. B: 71/72 resolved (TP27, FP1, FN8, TN34, plus one automated-uncertain agreed failure); decided-case precision 96.43%, recall 77.14%, F1 85.71%, FPR 2.86%; recall including the uncertain failure is 27/36=75%. Failure-classification accuracy is 51/51 among cases assigned a class, and joint detection-and-classification recall is 51/61=83.61%. | Not achieved: all figures are retrospective and exposure/provenance limited; no eligible pilot labels or frozen threshold-based held-out result exists. |

These counts are sourced from the [retrospective Phase 4 review metrics](../research/evidence-20261027/reports/PHASE_4_REVIEW_METRICS_2026-10-27.md), the [current recheck analysis](../output/proposal-evaluation/phase4-review-recheck-2026-10-28.json), and the [assisted-return validation receipt](../output/proposal-evaluation/assisted-human-return-2026-10-28.json). The completed return self-declares AI assistance, prior exposure, and non-independent completion; the second return identifies itself as AI-assisted. Later user corrections are preserved but do not independently authenticate these declarations. Do not describe these metrics as independent human gold or formal acceptance.

The user's 40-item feedback in the 28 October chat has IDs and decisions matching 40/40 entries of the archived `shuyuan-recheck-transcription.json`. It is preserved as a post-disagreement review input. In particular, Shuyuan marks `R-23b35e11a5783061` as an accuracy critical failure while Chongtai's counterpart is uncertain; this remains an unresolved reviewer disagreement. The supplied original JSON provenance declarations conflict with the user's subsequent correction; both source declarations and user-reported corrections remain in the evidence. Metrics in `PHASE_4_REVIEW_METRICS_2026-10-27.md` are therefore explicitly retrospective and conditional, not certified independent reliability or a complete held-out validation.

The read-only formal-review analyzer now handles an inconsistent “full coverage” label (the cited candidate is not confirmed valid by both reviewers) by retaining the source labels and marking only that reference-coverage decision unresolved, rather than aborting the entire metrics calculation. It also accepts explicit known-exposure names for later rechecks without editing the frozen reviewer packets. The focused analyzer/import module passed 21 tests after these changes. No original review, application database, or automated score was changed.

The original inventory and status paragraphs below are historical snapshots taken before the remote evidence archive was received. They remain for audit history; when they say A/B raw files or metrics are missing, that is no longer the current state.

## Finding

The current checkout contains hash-verified archived A/B/C runs, Phase 4 metrics, reproducible local analyses, and a new current-source in-system comparison. All three proposal collections and the local B-to-C rank-direction comparison have been executed. The evidence still does not establish formal completion of AC1 or AC3: human review remains retrospective, exposed, AI-assisted, unresolved in places, or incomplete, and the held-out acceptance thresholds were not frozen from eligible pilot labels before outcome inspection. The C result is a completed local compatibility comparison, not a full official benchmark result. A separate complete 216-item human return is now available with matching material and result hashes; its declarations rule it out as independent blind evidence. See the [assisted-return receipt](../output/proposal-evaluation/assisted-human-return-2026-10-28.json) and the [current requirement traceability matrix](REQUIREMENT_TRACEABILITY_MATRIX.md).

**Historical cross-document discrepancy (superseded):** At the initial 27 October inventory, the latest A/B files and Phase 4 metrics were not present in the local checkout. The 28 October evidence archive restored them and the current sections above use those records. Do not apply the initial-inventory missing-file statement below to the current state.

**Historical cross-document discrepancy (superseded):** The initial readiness summary cited latest A/B runs and Phase 4 metrics under Git-ignored `artifacts/local/` and `output/engineering-verification/`, but those files had not yet been restored to that initial checkout. The 28 October evidence archive subsequently restored the A/B/C originals and metrics. Their current paths and hashes are recorded in the evidence inventory above; the earlier discrepancy is retained here only to explain why the first local audit could not recalculate those summaries.

The proposal requires distinct direct-question, fixed-template, and contextual/indirect strategies for A; controlled Weak/Strong conditions for B; and compatible LongMemEval comparison for C. It requires human-verified references for extraction and auditor evaluation, as well as pilot thresholds frozen before held-out results are examined. It does not prescribe a universal two-question minimum for each dimension or a fixed 75% course pass mark.

The user-supplied Phase 4 files are present locally at
`reviewer-1(1)/material.json` and `reviewer-1(1)/review-result.json`. Their
SHA-256 fingerprints are respectively
`46c5464e5ce8232e5aecc3688584f8e913e9d053d7eca0c58a0fc9d7ee4cda06` and
`387b1915742690c1c0d4b11732e79e330c848ed3532b6cf7bb2edde1852aeabd`. All 216
item IDs in the frozen material have a corresponding return entry, and the
declared material fingerprint matches. The return self-declares that it was
not completed independently, used AI assistance, and had seen automated
results; the formal validator rejects it at the independent-completion gate.
The original return remains outside the assessed-source ZIP. The sanitized
inventory records file hashes without copying review text or reviewer identity.

## Earlier handoff, UI-pilot, and development evidence

The records in this table predate or sit outside the restored Phase 4 A/B/C collections summarized above. Keep their original scope; they do not replace or supersede the current A/B/C run evidence.

| Evidence | Locally verifiable record | Result and boundary |
|---|---|---|
| Owner A development release | `handoff/owner-a/review_summary.json`, `validation_report.json`, and the frozen development files | 12 synthetic development conversations, 195 AI-assisted label rows, 195 review-decision rows, zero completed human annotators, and `ready_for_formal_evaluation: false`. The eight held-out scenarios are described as a separate custodian package and are not present here. The checksum/schema validation record does not establish human annotation or model performance. |
| Owner B development results | `handoff/owner-b/TEST_RESULTS.md` | The handoff reports 27/27 development memories and 12/12 development relationships matched, seven focused tests passed, and an older backend suite with 136 passed / 1 skipped. It explicitly says no human-labelled evaluation was performed and gives no formal auditor-validity or LongMemEval result. Treat these as historical reported results, not a current independent rerun. |
| Owner C source-only engineering run | `handoff/owner-c/STEP3_RESULTS.md`, `STEP4_RESULTS.md`, `step4_comparison.json`, `step5_metrics.json`, `STEP5_RESULTS.md` | Eight synthetic source scenarios produced nine tests, in accuracy (8) and appropriate use (1) only. The documented reference is 8 passes and 1 failure. Against it the evaluator has TP=0, FP=0, TN=8, FN=1; accuracy/agreement 88.9%, failure recall 0%, failure precision undefined, and kappa 0. The reference macro-average is 50% across the two measured dimensions only; freshness and conflict resolution are unmeasured. Underlying private response/adjudication files are missing from this checkout, so the figures are internally consistent with the tracked summary but cannot be rederived from raw rows here. The handoff also discloses that one review sheet was AI-assisted and reviewer independence was not established. |
| Three-method UI development pilot | `output/auditor-method-comparison/browser-evidence.txt` and its screenshots | One synthetic conversation and one repetition exercised rule-generated tests, model-generated tests, and a rule/hybrid reviewer comparison. It documents a working UI path and two uncertain hybrid answers. Its three conditions do not match Proposal A's direct / fixed-template / contextual-indirect arms. It is explicitly a development pilot, spans generator revisions, and does not establish independent human review or auditor superiority. |
| Saved database-backed presentation comparison | `experiments/presentation-demo-20261023/result/` and running local PostgreSQL group `EXPD9C66FE3D5F946998AF5A8A0A3B272C9` | Local read-only reconciliation found six completed `openai/gpt-6-luna` target runs: three Weak and three Strong, eight questions each, with 48 saved replies and 48 evaluations. The export verifier records 48 exact input checks and corresponding JSON/CSV counts; the content/evidence signature of the eight questions matches across all six runs, although each run recreates its test IDs. App-reported overall mean/SD are Weak 13.9%/1.98 and Strong 75.0%/20.412. Strong has 13 pass, 4 fail and 7 pending answers; Weak has 3 pass, 18 fail and 3 pending. The saved per-dimension outcomes are Accuracy 3/6 vs 6/6; Freshness 0/6 vs 5/5 decided with 1 pending; Conflict Resolution 0/3 decided with 3 pending in both arms; Appropriate Use 0/6 vs 2/3 decided with 3 pending. One source gap was recorded in the first Strong response. The run explicitly declares itself a synthetic presentation demo, creates no human labels, and lacks a final Git commit binding. This is useful paired engineering evidence, not formal B acceptance or independent target scoring. Recompute the sanitized summary with `scripts/proposal_eval_saved_demo.py`; its output contains hashes and aggregate counts, not source or answer text. |
| Unbundled Phase 4 assisted human return | One local user reviewer folder, deliberately excluded from the source archive | The frozen material contains 3 synthetic histories and 216 items (27 candidates, 24 reference units, 9 relationship pairs, 48 questions, 108 responses); the return has matching material hash and a complete label entry for every item. It records candidate validity 21 yes/6 no; question validity 36 yes/12 uncertain; reference coverage 18 full/3 partial/3 none; and relationship labels 3 each for UPDATE, CONFLICT, and CONTEXTUAL_OVERRIDE. Response judgments are A: 33 fail/3 pass across 36 responses, with two defect links; B: 37 fail/35 pass across 72 responses, including one marked critical. The return self-reports `completed_by_human=true`, `completed_independently=false`, `used_ai_assistance=true`, and `has_seen_automated_results=true`. Treat its labels as one assisted, result-exposed review, not independent gold. The project's formal-review validator rejects it because independent completion was not declared. The private condition key and a second eligible return are absent, so do not derive formal arm scores, agreement, or blinded Auditor accuracy from it. |
| LongMemEval two-case pilot | `experiments/longmemeval-pilot-20261015/trial-summary.json`, `pilot-protocol.json`, `provenance.json`, `pilot-report.json` | The local record declares the cleaned LongMemEval source revision and MIT dataset-card license; its SHA-256 is `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`. Two preselected cases, one run per strategy, generated four target replies and four custom Luna assessments. Weak scored 0/2 and Strong 0/2, a tie. This is the separate 15 October pilot, not the restored Phase 4 C collection above. The assessor is neither the official scorer nor independent human review. |
| Release 20 engineering study | `experiments/stability-study-20261023-dev20-evidence-disjoint/FINAL_STATUS.json` | The local final receipt records a failed frozen release: Strong 26/36 (72.2%) versus Weak 3/36, below its 75% study gate, and two source-critical errors in the Strong arm. Preserve this as a failed engineering result; it does not by itself complete proposal B or validate the Auditor. |
| Versioned Phase 3/4 fixtures | `datasets/phase3-engineering-v1/` and `datasets/phase4-candidate-v1/` | These are engineering fixtures. They do not replace the restored Phase 4 A/B/C collections listed at the top of this report. |

## LongMemEval C candidate: completed local run

**Additional LongMemEval assets found in the current ignored `output/` tree:**
`output/longmemeval-official-v1/source-manifest.json` binds 500 Oracle and 500
cleaned full-history records to official commit
`98d7416c24c778c2fee6e6f3006e7a073259d48f` (MIT per the dataset card).
`prepared-release.json` freezes 14 candidate-held-out Oracle cases (two per
each of six question types plus abstention) without outcome-based selection.
The frozen `execution-manifest.json` remains the pre-run snapshot, so its
zero-execution count is not a current execution count. A separate GUI
Oracle/full-history pilot saved 21 Oracle
answers and one full-history case, all under Ollama `qwen3:1.7b`, across
`weak_first_hit`, `scope_aware`, and `no_memory`. All 21 Oracle responses had
AI pre-review, none had human labels, and the blind review template is blank.
The latest candidate is frozen at
`artifacts/local/phase4-c-openrouter-20261027-v5/protocol.json` and its
14-question subset is bound by SHA-256
`52d0c2701359d853fb1c28c4a498855202b184e61b987673bd6149c57cbc35c1`. It
completed six conditions (two strategies × three repetitions), producing 84
target responses and 84 usable automated judgments. The uniform scorer used
OpenRouter `openai/gpt-6-luna`, `reasoning_effort=none`, and a strict yes/no
parse. The analysis is reproducibly checked by
`python3 scripts/analyze_phase4_c_candidate.py`; the sanitized result is at
`artifacts/local/phase4-c-openrouter-20261027-v5/analysis.json`.
The v5 protocol SHA-256 is
`736ae69610eca51aac30ea4cc5d0e49e32d26dbc0dbc8ce5460ecdd67f34af80`, the
raw run SHA-256 is
`23f428e60c9aa35f8cdb38dac4b92792ed4303dcc7e77ae40d90db57e0b874d2`, and the
current analysis SHA-256 is
`66ffba9655c2fb61c6d5d83680f2efe0de2111aa227d82177afe4428510195c3`. The
analysis rechecks protocol/subset/run hashes, all 84 target payload hashes and
question/response bindings, the pinned grader prompt for each response, all
84 provider response bodies, strict verdict parsing, and the six-condition
coverage before producing these values.

| Repetition | Weak First Hit | Strong Rule Based | Strong minus Weak |
|---|---:|---:|---:|
| 1 | 4/14 (28.6%) | 12/14 (85.7%) | +57.1 pp |
| 2 | 4/14 (28.6%) | 11/14 (78.6%) | +50.0 pp |
| 3 | 4/14 (28.6%) | 12/14 (85.7%) | +57.1 pp |
| Aggregate repeated observations | 12/42 (28.6%) | 35/42 (83.3%) | Strong higher in 3/3 paired repetitions |

These are repeated evaluations of the same 14 questions, not 42 independent
cases per strategy. This is a local compatibility subset, not the full official
LongMemEval S/M execution. The target uses GPT-6 Luna and the pinned upstream
answer-check prompt uses GPT-4o through OpenRouter; the transport deviation and
absence of independent human calibration remain limitations. The saved C run
is complete for its local subset and is eligible for a qualified rank-direction
comparison; it does not establish full-benchmark performance.

The separate v5 candidate run recorded local lexical-match results of Weak
6/42 and Strong 21/42, and its own GPT-6 Luna grader ranked Strong above Weak
in all three repetitions. Do not treat this lexical proxy or the v5 grader as
the primary cross-metric result. The primary archived C result is compared with
proposal B's saved four-dimension Auditor macro below; the two runs remain
separate and no answer-level data is pooled.

## Cross-metric ranking result

The proposal defines external consistency by the relative ordering of Weak and
Strong, not by subtracting absolute scores across different test sets. The
saved analysis in `artifacts/local/phase4-20261027/analysis.json` applies this
criterion per repetition: proposal B's four-dimension Auditor macro ranks
Strong above Weak in all three repetitions, and archived C's LongMemEval
score does the same in all three. Directional ordering therefore agrees in
**3/3 repetitions**. This is the planned local rank-direction check on the
14-case compatibility subset. It is a descriptive result rather than a
population estimate: B and C use different histories/test structures, C
reuses the same 14 questions across repeats, and the benchmark grader has not
been independently human-calibrated. The prepared C review packet allows a
source-based check of its 84 grader decisions without exposing condition labels.

Execution lineage: v4 remains preserved separately with 72 successful target
receipts and 65/70 usable grades; v5 has 84 newly recorded target receipts and
84 uniform grades, and does not mix v4 scores into its totals. The v5 protocol
amendment described recovery from v4, but the first v5 invocation started in an
empty output directory, so v4 receipts/labels were not imported as that text
intended. Two target calls in v5 returned HTTP 503. v5 retained both failed
request payload hashes and exact question IDs; successful target receipt
`case_index` values are one-based while failed-attempt values are zero-based,
which the analysis script normalizes and cross-checks against each saved
question payload. The v5 reported estimate is about US$0.07894, excluding any
possible billing for failed calls; actual provider billing is not verified.

## Earlier inventory: files absent before the 28 October archive refresh

This dated absence list records the first local inventory. It is superseded by
the verified archive restore at the top of this document and does not describe
the current checkout. Those files were initially not found:

- `artifacts/local/phase4-20261027/A-live.json`
- `artifacts/local/phase4-20261027/B-live.json`
- `output/engineering-verification/PHASE_4_REVIEW_METRICS_2026-10-27.md`
- `artifacts/local/phase12-20261027/final/`
- `artifacts/local/phase4-followup-20261027/`
- `artifacts/local/owner-c-heldout-v1/results.json`

The archive restore subsequently made the A/B/C raw collections and Phase 4
metrics available and hash-checked. The initial inventory's acceptance table
is removed from the current report so its obsolete “latest runs missing” and
“C ranking not complete” claims cannot be mistaken for the current status.
Current AC1–AC3 denominators, the A/B retrospective metrics, C ranking result,
and remaining gates appear in the current tables above and in the
[requirement traceability matrix](REQUIREMENT_TRACEABILITY_MATRIX.md).

## Reproduction

From the repository root, regenerate the local evidence inventory without modifying source records:

```sh
python3 scripts/proposal_eval_inventory.py \
  --output output/proposal-evaluation/evidence-inventory.json
python3 scripts/proposal_eval_saved_demo.py
```

The inventory hashes small files, records tracked/ignored status, skips hashing files larger than 32 MiB, and labels absent paths. The presentation-demo reanalysis validates the saved report hash, verification receipt, all 48 CSV answer/evaluation rows, repeated run count, and identical question/evidence content across runs. These tools verify local evidence consistency only; they cannot authenticate human provenance, consent, semantic correctness, or formal research validity.

## Follow-up reviewer material received on 27 October 2026

The newly supplied `review2-result(1).json` contains 216 label entries and has
SHA-256 `377c5a23db2b38f5f4c3cf7d42b031a60324cac3febe50d273f398ea3ea170bf`.
Its own provenance identifies the reviewer as a Codex AI-assisted reference
review, declares `completed_by_human: false`, `completed_independently: false`,
`used_ai_assistance: true`, and `has_seen_automated_results: true`. Its declared
material hash is `6e6114174f1c7d00f090f38e7c6d54067e970c41f3720e6913b74f250bc3d830`,
but that matching material file was not supplied. The 216 labels therefore do
not qualify as a second human review or as an independently verified complete
return.

The supplied `chongtai-jia-recheck-40.zip` has SHA-256
`06ed0785e36deda11e6e41aa38c05e7ecbb9f7cb99565824f9b507c3f4716e39`. Its
embedded validation report passes 307 checks for completeness, change
comparison, and source references across 40 items. The same archive explicitly
limits its scope to AI-assisted review: it says Codex prepared it, no human
completed it, it is not an independent blind review, and the reviewer had seen
both first-round judgments and prior AI analysis. Its summary records 19
changed items, 21 unchanged items, and uncertainty in 29. These checks validate
the package structure and references, not the truth of labels or a human
reviewer's independence. The archive's declared source-page SHA-256 also does
not match the embedded HTML file's SHA-256, and the original source page was not
supplied, so exact source-page identity cannot be verified.

The 40-item archive and the 216-label AI return disagree on 17 comparable
fields. The latest feedback pasted into the chat also differs from the
archive's `after` state for `R-23b35e11a5783061`: the pasted feedback says
failure with a critical error, while the archive says uncertain for both the
verdict and critical-error status. Preserve these versions as separate
provisional inputs; do not silently merge or overwrite them. No eligible
independent human reference was added, so AC1 and AC3 remain unestablished.
Hashes, counts, and these comparisons are recorded in
`output/proposal-evaluation/review-followup-intake.json`; the received files
are retained under `output/proposal-evaluation/incoming-review/`, outside the
assessed-source archive.

## Next useful actions

1. Recompute the saved A/B/C summaries from the restored run bundles and compare each result to its source manifest before any report revision. The current A/B/C bundles and the separate frozen C v6 extension are present; the 14-case candidate protocol is archived and the expanded 30-case v6 run is complete.
2. Keep source-backed human review and AI pre-review separate. The 216-item A/B return is exposed and AI-assisted; eligible independent reviewers must complete fresh forms without seeing model scores or each other's decisions.
3. Preserve the frozen C v6 protocol and its existing primary selection rule. Do not recast viewed or tuned cases as held-out; any new held-out study needs a newly frozen protocol and threshold before selecting data.
4. Keep unresolved human labels, reviewer provenance, permissions, and team contribution confirmations visibly pending. Report the existing results with their denominators and scope rather than treating the auto-grades as independent evidence.
