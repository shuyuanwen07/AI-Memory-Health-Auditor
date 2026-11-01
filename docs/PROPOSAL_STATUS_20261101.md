# Proposal and tutor requirements: evidence status

This is an evidence map, not a claim that every hypothesis has succeeded.
The authoritative specification is the Group 2 proposal, Sections 3 and 7;
the tutor additionally asked for a diagnosis → improvement → retest chain.
Earlier results remain in [the experimental report](EXPERIMENT_REPORT_2026-10-28.md).

| Requirement | Evidence and interpretation | Remaining limitation |
|---|---|---|
| FR1–FR12: authorised input, memory review, question generation, controlled target, scoring and evidence | The [product review](proposal-product-acceptance.md) maps each requirement to implementation. A new Astra `max` synthetic integration run saved four questions, answers and assessments; details and run ID are in the [Astra retest](AC2_ASTRA_PRODUCT_RETEST_20261101.md). | This one source uses simulated operator confirmation; it is not a complete independent acceptance of every input and provider. |
| NFR1–NFR5: consent, access protection, explanations, guided workflow, reproducibility | The same product review maps implemented controls and prior engineering checks. Saved runs retain model and settings; Astra receipts distinguish model-controlled sampling from a fixed temperature. | Consent and authorisation are declarations. Local prototype controls and old test results do not establish production security, usability for all users, or deterministic output. |
| AC1: memories and relationships validated against labelled scenarios | On 27 complete histories, the selected reviewed reference has 204 fully covered, 9 partial and 3 missing facts, and 53 correct-type / 1 partial selected relationships. A separate [four-history Astra source-only pilot](../research/astra-ac2-20261101/ac1-astra-four-source-evidence.zip) yielded 30/30 source-supported candidates, 32/32 reference records fully covered, and 12/12 correct extracted relationships, according to two AI reviews later independently checked by two people as reported by the user. | Selected references are not exhaustive; partial matches are not full recall. Three incomplete histories are separately retained. The four-history pilot uses related, previously studied synthetic sources; reference records may combine facts and multiple candidates may cover a record, so coverage is not strict atomic recall. Human identities and exposure to AI judgments are not independently authenticated. |
| AC2: executable and supported questions | On 30 previously studied histories the original candidate had 62/120 scheduled slots valid; a direct Astra condition had 120/120 under the user-reported human-checked AI review. A four-history product-flow follow-up produced 16 reviewed-valid questions. A separate [ten-history product-flow study](../research/astra-ac2-20261101/ac2-astra-ten-source-product-evidence.zip) exposed a material failure: 14 valid, 14 invalid, and 12 ungenerated out of 40 planned slots. Two AI reviewers agreed, then two people independently checked their judgments according to the user. | The 30-history conditions differ in generator input and review procedure and are not held out. The ten histories share a synthetic conflict pattern; the operator confirmation was simulated. A new conflict guard rejects all 14 invalid questions in a post-discovery replay without rejecting the 14 valid ones. A [separate four-source guard retest](../research/astra-ac2-20261101/ac2-conflict-guard-four-source-retest.zip) produced no complete suites; extraction and planning failures also contributed, so this is not an isolated guard effect. Later generation repairs require their own reviewed retest. Reviewer identity and AI exposure were not independently authenticated. |
| AC3: failure detection and classification on held-out data | A recorded 118-answer consensus subset of the earlier frozen retest gives 61/68 detected failures, 54/61 classified detected failures, and 0/50 false positives; those descriptive thresholds were met on that selected sample. | Two answers were disputed; reference review was AI-assisted and reviewer identity/independence is user-reported. Related synthetic histories, pilot threshold caveats, and a detection difference interval including zero limit generalisation. The candidate is not the default evaluator. |
| AC4: dimension scores, failures, traceable evidence | Saved reports, exports and source links exist. A [read-only API evidence check](../research/astra-ac2-20261101/ac4-ac5-readonly-check.zip) cross-checked one failure's IDs, source, question, expected behaviour and response against its report and exports. | The checked run predates the latest code changes. In the Astra end-to-end smoke one failure category remains unclassified. A successful export is not proof of judgment validity. |
| AC5: repeated frozen inputs and recorded settings | Existing paired and repeated comparison receipts and export checks are preserved. The same read-only check confirmed identical frozen questions and recorded settings in two paired runs, except for their intentionally different writer. | This pair is not an identical-configuration repeat. Repetitions share cases; real model sampling is provider-controlled. Historical reports and new runs must not be pooled as independent samples. |
| Experiment A: equal-budget methods, failure detection, discovery and category coverage | The [source-bound historical summary](../research/astra-ac2-20261101/experiment-a-historical-metrics.json) records each method's 11/11 human-labelled failures detected and 3/9 frozen defects found across three related histories. A later four-scenario diagnosis is also preserved. | Only one human-pass answer per method was available. The hypothesised contextual-method advantage was not observed; counts from different studies must not be conflated. Category coverage requires separately verified question validity and is not derived from response labels. |
| Experiment B: controlled policies and four dimensions | Four strategies and their paired outcomes are shown in the Dashboard. | The documented relationship-priority vs first-match comparison exceeded it in two of four dimensions, rather than the proposal's expected three. Results are not a universal policy ranking. |
| Experiment C: LongMemEval ranking agreement | The [experimental report](EXPERIMENT_REPORT_2026-10-28.md) describes a three-repeat ordering comparison on 14 selected compatible cases and separately reports an expanded 30-case study. | Only subsets of LongMemEval were used; repeats reuse cases. The separate studies do not establish a full benchmark result. |
| Tutor: discover, improve, retest | The [retrieval retest](RETRIEVAL_RETEST_20261030.md) preserves four scenarios and paired before/after results. A separate Astra diagnosis found missing venue memories; the [four-history writer comparison](../research/astra-ac2-20261101/four-writer-prospective-evidence.zip) then obtained 12/16 → 16/16 human-checked passes (4 improved, 0 worsened). | The histories are related synthetic cases; the follow-up questions and conditions were frozen before collecting its answers, but the intervention was selected from earlier observations. Human checks were AI-assisted and user-reported. Neither result establishes population-wide benefit. |

The 16-question review return retains the two independent AI preliminary
judgments and a separate user report of two independent human checks.
`scripts/ingest_ac2_astra_four_review.py` checks source/question identity and
retains unresolved judgments when processing an explicitly confirmed return.

After the guard-only four-source retest, a conflict-aware generation change was
tried against the same four saved memory states. The [development retest](../research/astra-ac2-20261101/ac2-generation-repair-retest.zip)
saved 0/16 questions: three histories still failed planning, and one reached
model generation but the separate semantic reviewer failed after three attempts.
Unsaved model outputs are not counted as valid questions. The paired retest is
post-discovery and does not isolate individual code changes or prove AC2 success.

The user subsequently reports that two people independently accepted the
[unsaved-candidate adjudication](../research/astra-ac2-20261101/ac2-unsaved-candidate-human-adjudication.zip):
Accuracy and Conflict Resolution are usable, the Freshness prompt needs a
dimension-specific revision, and Appropriate Use remains uncertain because of
the source's ambiguous restriction. This does not turn the four unsaved model
outputs into an approved, complete product test suite.

The newer [Astra four-strategy collection](../research/astra-ac2-20261101/b-astra-four-strategy-run-evidence.zip)
saved 52/64 planned answers. Only three histories have all four strategies
completed (48 paired answers); the fourth stopped after a provider error.
Two independent AI preliminary reviews give paired pass counts of 3/12 for
First-match, 3/12 for Relationship-priority, and 0/12 for each of the other
two strategies. The user reports two independent people accepted the later
Astra high re-review with the same verdicts; these results do not establish
the proposal's expected strategy advantage or repeat-run stability.

The [isolated Astra LongMemEval development preflight](../research/astra-ac2-20261101/longmemeval-astra-isolated-development-preflight.zip)
completed four calls on two development cases. Each case imported its complete
source history, but the configured store retained 50 records and selected one
for each answer. All four local lexical-match checks failed. This tests
provider compatibility and a limited memory configuration; it is neither an
official benchmark score nor a human-verified policy ranking.
The user subsequently reports two independent people checked and accepted
the two AI reviews of all four answers and reference validity. The separate
[human confirmation](../research/astra-ac2-20261101/c-astra-development-human-confirmation.zip)
records 0/4 passes on these two development cases; it still does not establish
a policy ranking or official benchmark performance.
The later capacity-only development comparison changed 50 to 500 retained
records while keeping the two cases, strategies and reader profile fixed.
Three of four new calls completed and none passed the user-confirmed Astra
high reviews; one failed request has no answer and remains missing.
The [later human-confirmed review](../research/astra-ac2-20261101/astra-high-human-confirmation-and-capacity-review.zip)
also accepts the revised AC2 source and four manually revised questions.
Those revised inputs were then used in a new product-flow generation attempt.
After fixing the planning intent and the transport timeout, the same saved
memory state yielded four saved questions out of four planned. Both independent
Astra high reviews judged all four grounded, executable and reference-valid;
the user subsequently reports that two people independently checked and
accepted those judgments. The [run and frozen runtime](../research/astra-ac2-20261101/ac2-intent-timeout-product-retest.zip)
and [later human confirmation](../research/astra-ac2-20261101/ac2-intent-timeout-human-confirmation.zip)
are separate records. This is one previously studied development history,
with two implementation changes and a previously approved source revision;
it does not establish that the ten-history failures are all repaired.
Some prompts disclose the existence of a conflict, so their validity does not
demonstrate independent conflict-discovery sensitivity.
