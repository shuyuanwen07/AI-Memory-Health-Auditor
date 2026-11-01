# AI Memory Health Auditor — latest Astra MAX experiment report

**Evidence cutoff:** 2 November 2026 · ELEC5623 Group 2 · Track B
**Main question:** Can a traceable memory audit find useful problems, guide a repair, and show what changed under controlled retesting?

The implemented workflow and the observed repair results support that use case. They do **not** establish that every proposal hypothesis succeeded or that every memory-failure category is reliably classified in natural answers. A separate balanced diagnostic now shows all four categories can be recognised on deliberately constructed clear cases, with no observed benefit from a revised rubric. The user confirms that **two people independently checked every item** in the 552-answer A/B/C/AC3 review package and, separately, the new 150-case diagnostic references. Both are AI-assisted human verification, not blind first-pass human annotation claims. Earlier, explicitly confirmed AC1, AC2 and writer-repair judgments retain their original provenance.

This is the current main report. [The earlier report](EXPERIMENT_REPORT_2026-10-28.md) remains a historical archive with its original models, conditions, failures and review records. Historical Luna outcomes are not relabelled as Astra outcomes or pooled into the new denominators.

## 1. What the system does

The web application imports an authorised conversation, extracts memories and their relationships, lets an operator confirm them, generates source-linked behavioural questions, runs a controlled memory-enabled target, and reports the observed answers and evidence. The four abilities are **Accuracy**, **Freshness**, **Conflict Resolution** and **Appropriate Use**. A person can inspect the source, approved memory, question, expected behaviour, answer and assessment for a failure, then repeat frozen questions after a change.

There are three different outcomes to measure: whether a **question is valid**, whether the **target answers correctly**, and whether the **Auditor detects and classifies that answer correctly**. These denominators are kept separate. A target failure can reveal a useful audit case; it is not automatically a software error in the Auditor.

## 2. Model provenance and study controls

All model-backed **experimental stages used for the current main results** below have retained direct OpenAI receipts for `gpt-6-astra` with requested reasoning effort `max`. This includes the new A/B/C targets, new AC3 target and taxonomy judge, and the retained AC1/AC2 product and writer-repair stages. Deterministic templates, the archived rule-scoring baseline, statistics and export checks are labelled as code rather than falsely described as model calls. Requested MAX is observable in the receipts; the provider's internal computation is not independently observable.

| Study | Frozen comparison | Collected evidence | Reference status |
| --- | --- | --- | --- |
| A: audit methods | Four histories; direct, fixed-template and contextual methods; 16 answers per method | 48/48 Astra MAX answers | Two MAX AI reviews independently checked and accepted by two people, as reported by the user |
| B: retrieval policies | Four related histories, 16 questions, four policies, three repetitions | 192/192 answers; 48 per policy | Same confirmed AI-assisted human verification; unresolved cases retained |
| C: external compatibility | 16 fixed LongMemEval Oracle questions, four policies, three repetitions | 192/192 answers; 48 per policy | Same confirmed AI-assisted human verification; four source/reference pairs remain flagged |
| AC3: scorer reliability | Same 120 new answers across 30 histories; archived rule scorer versus MAX taxonomy judge | 120/120 target answers and 120/120 candidate judgments | Same confirmed AI-assisted human verification; incomplete type references retained |
| AC3: balanced diagnostic | New 30 fictional histories; 150 curated answers; original versus revised rubric on identical inputs | 300/300 Astra MAX judge calls | Two independent MAX AI reference reviews, then user-confirmed independent two-person checks of the 150 references; automatic predictions are not human-approved labels |
| AC1, AC2 and writer repair | Previously collected Astra MAX product-stage evidence | Retained unchanged | Prior user-confirmed independent human checks of AI-assisted judgments; original reviewer settings retained |

The new A/B/C target calls used an output budget of 8,192 tokens and one provider attempt. All planned answers returned; no missing response was converted into a pass or failure. Protocols, actual delivered-memory receipts, runtime hashes and error/recovery journals are preserved. B's pre-dispatch suite-lock conflicts made no provider call; post-persistence logging errors were recovered read-only without paying for another answer.

Independent **AI** research reviewers received sources and answers under opaque handles, without policy names, repetition labels, automatic scores or the other review. Separate review sessions reduce direct contamination but do not remove shared-model bias: the reviewers and candidate judge are from the same model family. The later two-person verification was independent according to the user, but its package exposed AI opinions; human blindness to automatic scores is not newly established, and reviewer identities were not independently authenticated. Statistical plans and frozen execution protocols are retained with their actual timing; exploratory post-discovery analyses are not described as preregistered trials.

## 3. Experiment A: which method exposes the frozen candidate problems?

The approved COMMUNITY, SHOP, GARDEN and RESEARCH sources were tested using the same three methods and equal question budgets. The target reader and deterministic writer were shared across methods. The candidate inventory contains **16 potential failure patterns**, not 16 independently proven target bugs.

| Method | Target answers passed | Failed | Distinct inventory patterns exposed by both reviewers | Mapping disputes |
| --- | --- | --- | --- | --- |
| Direct questions | 5/16 | 11 | 1: `RESEARCH-D3` | 1 answer |
| Fixed templates | 5/16 | 11 | 1: `GARDEN-D3` | 0 |
| Contextual/indirect Auditor tests | 5/16 | 11 | 3: `GARDEN-D3`, `GARDEN-D4`, `RESEARCH-D3` | 0 |

The contextual method exposed more distinct **listed** patterns in this collection, while target-answer pass counts were identical. This is descriptive discovery evidence, not an estimated recall over all real defects or proof of a general method advantage. There is only one answer per method/question slot. Some failed answers cautiously withheld information, or made errors outside the frozen inventory; those remain failures for answer completeness without being forced into an inventoried defect category. The one disputed Direct mapping remains unresolved.

Evidence: `output/proposal-delivery/a-astra-max-retest-20261101-v2/analysis.json`, `read-only-final-snapshot.json`, `delivery-control-check.json`, and the two files under `review-max/`.

## 4. Experiments B and C: four policies, equal denominators

The policies differ in **which memories they select**, while model and reader settings are common within each new study:

| Policy | Selection rule |
| --- | --- |
| First-match retrieval | Return the first relevant memory record. |
| Relationship-priority retrieval | Follow update/conflict relationships and their priorities. |
| Match the task and project | Filter or rank memories for the current task and project scope. |
| Consider time and importance | Rank relevant memories using time and importance signals. |

Each study has **16 unique questions × 3 repetitions = 48 planned answers per policy**. All 384 answers returned and were reviewed. The main fraction below is **verified passes / all planned slots**. Unresolved cases are shown separately; they are not silently counted as model failures or removed from the sample.

| Policy | B: pass / planned | B: fail / unresolved | C: pass / planned | C: fail / unresolved |
| --- | --- | --- | --- | --- |
| First-match | 9/48 (18.8%) | 39 / 0 | 8/48 (16.7%) | 28 / 12 |
| Relationship-priority | 33/48 (68.8%) | 12 / 3 | 28/48 (58.3%) | 7 / 13 |
| Task and project | 19/48 (39.6%) | 26 / 3 | 26/48 (54.2%) | 10 / 12 |
| Time and importance | 33/48 (68.8%) | 12 / 3 | 27/48 (56.3%) | 8 / 13 |

| Study / policy | Repeat 1 passes / 16 | Repeat 2 passes / 16 | Repeat 3 passes / 16 |
| --- | --- | --- | --- |
| B / First-match | 3 | 3 | 3 |
| B / Relationship-priority | 11 | 11 | 11 |
| B / Task and project | 7 | 7 | 5 |
| B / Time and importance | 11 | 11 | 11 |
| C / First-match | 3 | 3 | 2 |
| C / Relationship-priority | 10 | 9 | 9 |
| C / Task and project | 9 | 9 | 8 |
| C / Time and importance | 9 | 9 | 9 |

**B diagnosis.** The earlier reader retrieved two to five records for advanced policies but delivered only the first record to the target. The new collection uses one common full-reader configuration for all four policies. This changes both memory delivery and reader instructions, so it is a **shared-reader configuration repair**, not an isolated estimate of delivery alone. The original rule writer remains fixed and omits venue records in all four related histories; every policy therefore remains limited on the conflict questions. The earlier paired subset had three histories and one repetition, so its raw denominator is not compared causally with the expanded 48-slot result.

**C objectivity.** C uses the external [LongMemEval](https://github.com/xiaowu0162/LongMemEval) Oracle source pinned to commit `98d7416c24c778c2fee6e6f3006e7a073259d48f`. The deterministic selection uses seed `20261101`, seven question strata and 16 distinct questions, including two preserved historical anchors and two abstention questions. Normalised content checks found no duplicated source session or substantial message overlap among the selected cases. This is an evidence-only Oracle subset with a local adapter, **not an official full-benchmark score**. Prior exposure to the selected cases was not audited, so the sample is not claimed to be held out.

Four C question/reference pairs are flagged: an unsupported “inside the mall” premise, stronger preference claims than the source supports, a misidentified jam-maker, and an artist-name versus description ambiguity. All planned cases remain present. Affected answers remain unresolved in the human-accepted conservative summary; the confirmation does not turn disputed cases into passes. The two independent AI reviewers agreed on 369/384 raw answer verdicts; source validity adds a separate eligibility condition and is not bypassed by answer agreement. B retains nine unresolved answer slots and C retains 50, for **59/384 unresolved slots** in total.

**Interpretation.** Relationship-priority and time/importance tied in B. Relationship-priority had the largest observed C pass count, but its paired differences from the other two advanced policies have descriptive intervals that include zero. This does not establish a universal winner or a complete agreement of policy rankings between synthetic and benchmark data. Equal denominators make the display comparable; they do not equalise dataset difficulty.

The analysis resamples **source clusters**, keeping repeated answers together: 5,000 draws with seed `20261101`, at most four source clusters in B and 16 in C. The resulting intervals describe this selected cohort and cannot remove template similarity or sampling bias. The repetitions are correlated measurements, not 48 independent histories. Decided-only accuracy, per-ability outcomes, paired policy differences and intervals are retained in `output/proposal-delivery/bc-reader-retest-20261101-v2/analysis.json`; the concise [B/C ledger](BC_ASTRA_RETEST_20261101.md) gives the same main counts.

## 5. AC3: is the Auditor's assessment itself reliable?

This check holds the **120 new Astra MAX target answers** fixed and compares the archived deterministic rule-v65 scorer with the Astra MAX taxonomy judge. The latter was run in a frozen research wrapper using the product's rubric and source boundary; it is not an unannounced replacement of the product's default scorer. Input fingerprints verify that the candidate judge received the question, saved answer and approved memories, **not** expected answers, intended dimensions, reviewer judgments or policy names.

The two MAX reference reviews agree on **51 passing and 69 failing answers**, with all 120 questions/references accepted. No scorer response was missing or undecided.

| Measure on the same answers | Archived rule scorer | Astra MAX candidate |
| --- | --- | --- |
| Failure detection | 55/69 (79.7%) | **63/69 (91.3%)** |
| False positives among agreed passes | 18/51 (35.3%) | **0/51 observed** |
| Automatic decided coverage | 120/120 | 120/120 |
| Correct type among detected failures with an agreed single reference type | 0/30 | **35/42 (83.3%)** |
| Verified correct type / all detected failures | 0/55 | **35/63 (55.6%)** |
| Verified detection and correct type / all agreed failures | 0/69 | **35/69 (50.7%)** |

The category reference is complete for only **42/69 failures**: 38 Accuracy, two Conflict Resolution and two Appropriate Use. The other 27 have uncertainty, multiple primary errors or reviewer disagreement; they remain in answer-level denominators. There are **no agreed Freshness-positive failures**, so sensitivity for that category is unmeasured. The candidate correctly typed 33/38 Accuracy cases, 2/2 Conflict Resolution cases and 0/2 Appropriate Use cases. One of the 42 detected classifiable failures has no automatic type and remains in that denominator. The alternative 35/41 fraction excludes that missing type and is not used as the main classification result.

The frozen acceptance checks were detection ≥80%, classification ≥80%, question validity ≥90%, false positives ≤10%, decided coverage ≥80%, and at least 30 agreed passes and 30 agreed failures with all histories represented. The collection meets the answer counts, coverage, validity, detection and observed false-positive checks. **It does not establish complete AC3 acceptance:** the conservative all-detected classification check is 35/63, not ≥80%; reference types are incomplete and there is insufficient positive support across the full four-category taxonomy. The more favourable 35/42 conditional result is reported alongside it rather than substituted after seeing outcomes.

A paired 30-history bootstrap (5,000 draws; seed `20261102`) gives a detection change of +11.6 percentage points with a descriptive 95% interval of **−2.6 to +25.4 points**. That interval includes zero. The false-positive change is −35.3 points, with interval −50.0 to −18.9 points. Observed zero false positives does not establish zero risk in new cases; resampling zero observed events produces a degenerate interval. The cohort is reused and synthetic, and the shared Astra model family can produce correlated reference and judge errors.

Evidence: `output/proposal-delivery/ac3-astra-max-retest-20261101-v2/analysis.json`, `reference-consensus.json`, target/scorer receipt verification files, frozen runtime and original reviews. The user reports independent two-person verification of these AI-assisted reference judgments, including the conservative type limitations. This is not a claim that changing the target from Luna to Astra caused the scorer improvement.

### 5.1. Additional balanced diagnostic: clear categories, unchanged outcomes

To address the uneven category evidence, a **separate controlled evaluator diagnostic** uses 30 new fictional histories, 270 source messages and 150 deliberately curated answers: 30 failures in each of the four actual reference categories and 30 correct controls. These are injected faults and correct examples, **not naturally generated target-model answers**, a target-accuracy benchmark, or a measurement of real-world error prevalence. They are not pooled with the natural 120-answer study above.

| Controlled diagnostic measure | Original rubric | Revised rubric |
| --- | --- | --- |
| Accuracy: detected and correctly typed | 30/30 | 30/30 |
| Freshness: detected and correctly typed | 30/30 | 30/30 |
| Conflict Resolution: detected and correctly typed | 30/30 | 30/30 |
| Appropriate Use: detected and correctly typed | 30/30 | 30/30 |
| All injected failures: detected and correctly typed | **120/120** | **120/120** |
| False positives on correct controls | **0/30 observed** | **0/30 observed** |
| Decided coverage | 150/150 | 150/150 |

All **300 judge calls** completed through direct OpenAI Astra MAX, with 8,192-token output budgets, one provider attempt and no missing/error outcomes. The sole experimental change was the scoring rubric. Each pair used identical question, saved curated answer and source-confirmed memories; expected behaviour, author-intended category, question dimension and reviewer labels were withheld from the judge. The frozen job order balanced which rubric ran first: 75 cases each. All 150 categorical predictions matched between rubrics: **zero improved and zero regressed**. The category point thresholds were met by both rubrics on this diagnostic, so the revised rubric demonstrated **no quality gain**.

**Reference controls and pre-run revision.** The diagnostic was kept separate from rubric development, then underwent two independent MAX reviews before scoring. Both reviewers found one H05 question's labelled-key versus labelled-set wording uncertain. The wording was clarified before any grading call; the original draft and reviews remain under `pre-freeze-v1/`, both reviewers accepted the correction, and the other 149 case judgments were unchanged. Sources and the curated answer for that item were not changed. The actual accepted class counts, dataset, rubrics, thresholds, single-attempt policy and analysis plan were then frozen. Two people independently checked and accepted the 150 source/question/answer/category references according to the user's new explicit confirmation. That verification covers **reference judgments only**, not human approval of the 300 automatic predictions; AI assistance and unestablished blindness to automatic scores remain disclosed.

**What this adds, and what remains.** The balanced set supplies 30 clear, reference-supported positives for each category, including Freshness and Appropriate Use. It demonstrates diagnostic competence under explicit single-error conditions. The earlier natural-answer result remains **35/42 conditional classification, 35/63 verified across all detections, 27 nonclassifiable failures and zero agreed Freshness positives**. A development recheck suggests the earlier Appropriate Use disagreement concerns an operational boundary: omitting a factual instruction is different from explicitly applying a true general preference to the wrong scoped task. It is not sufficient evidence of general model incompetence. The old labels and results remain unchanged rather than being rewritten to agree with the revised guide.

The 30-history paired bootstrap uses 5,000 draws and seed `20261102`. All paired metric changes and their descriptive intervals are zero; the `[0, 0]` change interval reflects a **ceiling on this constructed cohort**, not proof that the rubrics are equivalent everywhere. Likewise, zero observed false positives does not prove zero future risk. The five designed patterns recur across fictional domains, the cases share histories, and judges/reference reviewers share a model family. These clear fault injections are simpler than many natural multi-error answers.

Observed token usage was 169,282 input / 79,861 output tokens for the original rubric and 249,382 input / 71,439 output for the revised rubric. Reasoning tokens are included in output usage. These receipts do not establish billed dollars or a general cost/latency advantage. **Recommendation:** retain the original rubric, keep the revised guide as a research candidate, and require new natural, previously unseen answers before claiming a scoring improvement or promoting the revision.

Evidence: `output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1/` and the retained archive at `research/ac3-balanced-diagnostic-20261102/`. The final `analysis.json` SHA-256 is `e6b0ff4b5e22fcec37cd68d80ddc2e9f1a55772b9d4303613d2b11afa4dedb58`; `human-confirmation.json` is `1244785d4d19aceeb787598c494083dc1e8cef9b228888a0b953804e5d567a67`. The public summary is `frontend/public/reports/ac3-balanced-diagnostic-v1.json`. Original independent reviews, pre-freeze amendment, frozen inputs, raw receipts, paired predictions and analysis remain preserved.

## 6. Retained Astra MAX product results and the tutor's repair loop

The previously verified results below are retained as separate cohorts; they are not added to new A/B/C/AC3 denominators.

| Requirement / experiment | Current retained result | Interpretation |
| --- | --- | --- |
| AC1 extraction and relationships | Four sources: 30/30 candidates source-supported, 32/32 reference records covered, 12/12 extracted relationships correct and reference relationships covered | Selected-source record coverage, not strict one-record-per-atomic-fact recall. Related, previously studied histories. |
| AC2 original-ten product retest | 40/40 current questions valid after review and two actual regenerations; 40 answers and 40 assessments completed | The original 14 valid, 14 invalid and 12 ungenerated slots, and the repaired first review of 38 valid/two uncertain, remain preserved. Current validity is not first-pass automatic perfection. |
| AC2 relationship boundary | 26/32 links confirmed; six uncertain links excluded from confirmed-correct counts | Question validity does not certify every inferred relationship. |
| Tutor writer repair | Same 16 questions across four histories: **12/16 → 16/16** passes; four improved, none worsened | A concrete diagnosis → change → controlled retest on the selected development sources. |
| AC4/AC5 evidence trace | Saved Astra MAX before/after pair, frozen questions, report and JSON/CSV checks | Structural traceability and repeatable settings; export success alone does not validate a judgment. |

The writer experiment is the clearest practical value example: the audit identified missing venue facts in the target store; a structured writer was introduced; the same frozen questions then improved. It supports the claim that evidence from the Auditor can guide a useful repair **on these cases**. The intervention was chosen after earlier observations, histories are related, and human review was AI-assisted and user-reported; this is development evidence, not a population-wide causal guarantee.

Sources: [AC2 ten-scene ledger](AC2_TEN_SCENE_RETEST_20261101.md), `frontend/public/reports/ac1-astra-four-source-v1.json`, `frontend/public/reports/ac2-astra-ten-source-v1.json`, `frontend/public/reports/ac2-astra-comparison-v1.json`, and the source-bound archives under `research/astra-ac2-20261101/` and `research/astra-ac2-ten-completion-20261101/`.

## 7. Proposal status and next decisions

| Area | Status supported by current evidence |
| --- | --- |
| Product workflow and AC4 traceability | Implemented, with saved integration/report/export evidence; prototype scope and selected-run validation remain explicit. |
| AC1 | Source-supported extraction demonstrated on the selected Astra cohort; no exhaustive population recall claim. |
| AC2 | Current reviewed ten-scene suite is complete and executable; first-pass failures and six uncertain relationships remain visible. |
| AC3 | Natural-answer detection improves on the selected cohort, while its classification-reference gaps remain. The separate balanced controlled diagnostic meets point thresholds with 30 positives per category and 30 correct controls for both rubrics; no revision advantage is observed. Neither result establishes complete held-out natural-answer four-category reliability. |
| AC5 | New B/C studies retain three repeats, identical repeated-condition input hashes and all 384 answers; this measures within-case consistency, not independent-case replication. |
| A/B/C research hypotheses | All three collections executed. Some patterns and policies perform better in the observed cohort; universal advantage and full benchmark validity are not established. |
| Tutor closed loop | Diagnosis, implemented repair and same-question retest are demonstrated by the Astra writer comparison. |

The 552-answer verification and separate 150-case diagnostic-reference verification are complete according to the user's explicit confirmations; no repeat confirmation of those packages is required. Future work can separately adjudicate the retained natural-answer source/type disputes, then test new diverse histories and a larger untouched benchmark sample under a frozen protocol. Freshness and Appropriate Use still need enough **naturally observed, independently labelled positive failures** for category-specific external validation; the injected examples answer a different controlled question. Increasing repeated answers alone cannot fill those gaps. Keep the distinction between engineering completion, controlled diagnostic competence and broader validation in the presentation.

## 8. Human verification record and reproducibility entry

The combined local review package, now confirmed by the user, retains its original filename:

`output/proposal-delivery/all-astra-main-results-20261101/Astra-MAX-全部新增实验-待人工复核.zip`

The user explicitly confirms that two people independently checked all 552 A/B/C/AC3 answers and accepted the supplied review conclusions. The separate binding record is `output/proposal-delivery/all-astra-main-results-20261101/human-confirmation.json`. Original MAX AI files remain unchanged. This confirmation endorses conservative handling of the one A mapping dispute, four C source/reference flags, 59 B/C unresolved answer slots and 27 AC3 failures without an agreed single primary type; it does not reclassify them. The pack contains AI opinions, so this is **AI-assisted** human verification. It is not retroactively described as a blind first-pass human study, blindness to automatic scores is not newly established, and reviewer identities are not independently authenticated. Earlier human confirmations remain bound to their original outputs.

The balanced diagnostic has its **own new confirmation**, not one inherited from that 552-answer package: `output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1/human-confirmation.json`. The user reports two independent item-level checks of all 150 references. The retained `AC3-四类诊断150题-待人工复核.zip` filename records the original handoff stage; those reference checks are now confirmed, with the scope stated above. No additional confirmation of the same references is requested.

The new study folders preserve protocols, source snapshots, response receipts, independently authored reviews, conservative consensus, analysis code and retained errors. Public Dashboard summaries are derived from those saved records. Original experiments remain archived. Model keys and private credentials are not part of the evidence package. The latest presentation is maintained as one local PPT and is not uploaded with these code/evidence changes.
