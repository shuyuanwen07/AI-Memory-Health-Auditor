# Frozen formal experiment protocol

**Protocol ID:** `mha-formal-v1`  
**Status:** template to freeze before collecting formal results  
**Scope:** controlled memory-policy evaluation; this document does not report results.

## Added auditor-method ablation (development workflow)

New Audit automatically compares rule tests/rule review, model tests/rule
review and model tests/hybrid review when OpenRouter is configured. All use
one source-reviewed ground truth, fixed target settings and equal per-condition
question budgets. The two model methods share a canonical question suite and immutable target
answers. Each hybrid run records its source run/response receipt; it makes no
additional target call. Historical runs without this receipt remain exploratory.
This is a testing/review ablation, not an extraction ablation: the actual
shared extraction configuration is separately persisted. It supplements,
but does not replace, proposal experiments A/B/C below.

For a formal method comparison, freeze independent failure labels and report
failure Precision/Recall/F1/FPR, classification confusion and coverage, test
validity, abstention rate, per-stage cost where observed, and latency. A higher
target pass rate alone does not indicate a better auditor. Rule/model suites
may discover different failures and may differ in difficulty. Semantic/rule
disagreements must remain excluded from target scores and included in coverage.
An abstention on a human-confirmed typed failure is retained in joint
detection-and-classification recall, not silently removed. Cloud repeats use a fresh target answer per repetition, shared within its
rule/hybrid reviewer pair. Report the pair as a correlated observation; do not
count its copied response as an independent sample or a second target request.

### Proposal Experiment A: three test-construction methods

Create Experiment A from one completed, authorised audit. The saved comparison
contains three conditions on the same source and target configuration, with the
same frozen test budget: direct ground-truth questions, a fixed-template draft
generated once by the deterministic rule baseline and then reviewed/edited and
confirmed by a researcher, and a generated Auditor suite containing only
contextual or indirect probes (no direct-recall items). Each arm receives the
same frozen `test_budget` as its maximum question and target-call cap; the
contextual/indirect arm does not use paired-probe budgeting. Before
generating any condition's questions, the team supplies one JSON release that
includes the source-defect inventory and final researcher-reviewed template
questions. The release is SHA-256 bound to the exact source messages and
confirmed memories; it also records separate fingerprints for the initial rule
draft and final reviewed release. Every defect and fixed question must cite
confirmed memory IDs and user source message IDs linked to those memories.
Fixed questions must equal the frozen budget and meet the per-dimension minimum
(for a budget of 20, at least five in each dimension). A researcher must inspect
the draft, edit or add questions as needed, and explicitly confirm the final
release. All three suites still pass ordinary automated quality checks and
require human validity review before execution. This is a rule-seeded,
researcher-reviewed fixed-template arm, not a from-scratch human-authorship
baseline; report that distinction with Experiment A results.

Freeze the release at `POST /audits/{id}/method-comparison-inventory` before
calling `POST /audits/{id}/generate-tests` for any condition. The server rejects
generation before that freeze and rejects changed source or rule-draft
fingerprints, missing human confirmation, invalid evidence IDs, mismatched
fixed-template budgets, or missing dimension minimums. The review flag is a
recorded declaration; it does not authenticate the person or prove review quality.
After question validity review, execute each arm and label every saved response
blind to condition. Experiment A stores this decision separately from
automated question-quality status: a suite cannot execute until a researcher
explicitly accepts every question through the human-validity review action.
The reviewer pseudonym and note are saved with the question; the pseudonym is
self-declared.
Save two independent response judgements or an adjudication citing both
independent reviews. The independent identities and template reviewer/editor
pseudonyms are recorded as declarations; signed worksheets and actual
independence are external evidence the application cannot authenticate.

The saved `GET /audits/{id}/method-comparison-results?comparison_id=...` report
and its JSON download use these definitions:

- Category Coverage = number of the four dimensions with at least one question
  that passes automated quality and grounding checks and has an explicit human
  validity acceptance / 4. The report leaves this unmeasured until every
  question in that condition has a human-validity decision.
- Response-level Failure Detection Recall = TP / (TP + FN), where a positive
  reference is a human-confirmed failure and TP requires the automated evaluator
  to identify a failure. Only two-reviewer agreement or a valid adjudication
  contributes to response metrics.
- False-Positive Rate = FP / (FP + TN), using the same resolved response labels.
- Failure Discovery Rate = distinct frozen defect IDs explicitly mapped by a
  researcher to a response with a resolved human-failure label / number of
  distinct frozen defect IDs. The mapping is a separate fingerprinted release
  bound to the exact comparison, condition, inventory and saved responses.
  Every saved response must appear once, including an empty defect list when no
  known defect was found. No defect is inferred from a matching dimension or
  supporting-memory signature. Only completed runs with a resolved independent
  label for every saved response and a complete, consistent mapping qualify.

The report checks planned budgets and target/evaluator settings separately from
realised target attempts. Attempt counts include recorded provider retries;
missing attempt records remain unknown. Zero known defects, incomplete runs,
missing answers or incomplete independent labels are marked unmeasured rather
than converted to zero. This report describes an experiment; it does not prove
that the researcher reviewed the rule draft or mapping, or that reviewer identity and
independence are authentic. Do not report this rule-seeded arm as a from-scratch
human-authored baseline.

## Proposal scope and required experiments

The user reaffirmed proposal-only development on 2026-10-09. Independent
external-Agent/vendor adapters are optional retained infrastructure, not a
required experiment or a development priority. The prototype uses a fixed
base LLM and configurable target-memory retrieval/update policies.

This document is a draft template, not evidence of a completed protocol freeze.
Formal acceptance must cover all three proposal experiments: A compares
equal-budget direct questions, rule-seeded researcher-reviewed fixed templates
and Auditor contextual/indirect tests against independently labelled failures; B compares
Weak/Strong target-memory policies under the same model and controls; C tests
their relative ranking agreement with technically compatible LongMemEval
semantic evaluation. Extraction/relationship validity, test validity and
failure-detection/classification metrics require genuine independent labels.
An exploratory original/generic/directed repair study does not replace A/B/C.
For C, use the same frozen Weak `weak_first_hit` and Strong `strong_rule_based`
pair as the Auditor comparison. Optional ablations such as `scope_aware` do not
substitute for either proposal condition and cannot qualify as Experiment C.

## Research questions

1. Under a fixed underlying target model and frozen question suite, how do controlled memory strategies affect Accuracy, Freshness, Conflict Resolution and Appropriate Use?
2. Does a scoped/context-aware strategy improve contextual use without reducing performance on stable facts?
3. Are observed differences consistent across repetitions and locally permitted benchmark-compatible subsets?

## Conditions and controls

Compare only predeclared conditions. A formal Experiment B analysis plan must be explicitly frozen with a development split, contain exactly one target provider/model/temperature and both the Weak `weak_first_hit` and Strong `strong_rule_based` policies, and run each formal condition at least three times. The three-repeat minimum also applies to the deterministic `rule_based` target; a smaller unplanned matrix belongs to the separate exploratory route and is not Experiment B. Optional reference ablations `no_memory` and `full_context`, plus `strong_score_based`, `scope_aware` or `temporal_importance`, may be added only when their policy versions are frozen. The reference ablations distinguish a useful policy from both no retrieval and unrestricted context replay. Keep the following fixed within each experiment group:

- authorised/de-identified conversation set and reviewed ground truth;
- canonical shared test suite, suite mode, seed, prompt-template fingerprint and acceptance decisions;
- target provider/model, temperature, retry policy and target-memory writer version;
- evaluator provider/model and evaluator version;
- memory-maintenance policy, retrieval budget and software revision.

Run every formal condition at least three times, whether the target is local Ollama, a cloud model, or the deterministic baseline. Repetitions reveal execution variability; they do not create independent histories.

The system labels each pipeline stage's seed control explicitly. `deterministic_local` means the local rule-based component is deterministic under the saved inputs; `recorded_only` means the seed is retained as configuration provenance but the external provider does not offer a portable seed guarantee. Never describe the latter as bit-for-bit reproducible.

## Data, consent and labelling

Use only synthetic or explicitly authorised, de-identified conversations. Store source conversations separately from research annotation files. Before formal collection, freeze a versioned annotation release containing memory, relationship, test-quality and evaluator labels; record the validation SHA-256 fingerprint. Two annotators independently label a predefined overlap subset, disagreements are adjudicated without seeing automated outputs, and Cohen's kappa is reported where labels permit it.

## Pilot and freeze gate

Run a pilot before formal evaluation. Resolve unclear memory boundaries, leaked-answer tests, ambiguous expected behaviour, and evaluator disagreements. Do not silently change prompts, labels, policies, benchmark mapping or sample membership after the freeze. Any change creates a new protocol ID and a new experiment group.

### Current synthetic-pilot execution path

For a source-verified human-labelled synthetic release, open **Experiments → Research Workspace** and upload the matching annotation dataset and double-annotation package. Bundled Pilot v2 files exercise the format; their filenames and self-declared human provenance are not independent verification that a real review occurred. Analyse the pilot first: memory inclusion, relationship type, test validity, evaluator verdict and failure dimension must all meet the declared coverage and resolution criteria. Only a ready matching package enables **Formal Synthetic Pilot Matrix**. Select the predeclared target models and retrieval strategies. Enter the four pilot-selected success percentages before creating the matrix: failure recall, failure classification accuracy, test validity, and maximum false-positive rate. These values start blank, are saved with server time and dataset/runtime fingerprints, and cannot be changed for existing runs. Then explicitly execute the pending conditions. This freezes the four acceptance thresholds; it does not by itself verify the full sampling/repetition protocol, unseen earlier results, or independent review.

The matrix creates one Experiment Group per synthetic scenario and copies the exact same accepted fixed test suite to every condition. It records the dataset fingerprint, pilot ID, suite version, model, temperature, seed and strategy in durable metadata. It is limited to explicitly declared synthetic data; do not use it to materialise participant conversations. After completion, use **Experiments** to inspect paired comparisons and download the CSV/artifact before generating paper figures.

## Primary outcomes and analysis

The primary outcome is macro-average Memory Health across measured dimensions. A zero-test dimension remains unmeasured and is excluded, never converted to zero. Report each dimension's pass/total/percentage, failure categories and traceable evidence. For local benchmark-compatible runs, also report token-level F1 and mean case latency; these are diagnostics and are not upstream official benchmark scores.

For shared-suite comparisons, align outcomes using the canonical `suite_test_id`. Report condition means, population standard deviation across repetitions, paired candidate-minus-reference percentage-point delta, deterministic bootstrap 95% interval and exact two-sided sign-test p-value. These are descriptive/pilot support statistics unless the team preregisters a confirmatory analysis and sample size.

Separately report Auditor validity against frozen manual labels: extraction and relationship Precision/Recall/F1, test validity, evaluator failure-detection Precision/Recall/F1/Accuracy/FPR, and agreement. Do not combine Auditor validity and Target Agent health into one score.

## External benchmark-compatible subsets

LongMemEval, LoCoMo and BEAM inputs must be independently obtained under their applicable licences. The application accepts caller-supplied local-compatible JSON. Deterministic reference-overlap baselines remain available; the LongMemEval live pilot additionally calls a fixed real target through selected memory policies without exposing reference answers. For live C evidence, the request requires dataset version, licence or permission basis, and citation; the result binds these declarations into its configuration fingerprint and reports the exact source fingerprint, adapter version and adapter implementation fingerprint, and explicit compatibility limitations. These are user declarations, not independently verified. Matching external automated semantic assessments can be imported and validated against those replies and the declared evaluator revision; the application does not execute the official external evaluator or verify imported file authorship. It neither downloads nor persists benchmark sources. Label resulting numbers **local compatibility results**, not official full-benchmark scores. Record category mapping. Experiments → Research tools → Does the benchmark agree? connects two saved audits from one frozen experiment to matching semantic assessment inputs. First validate each benchmark condition in Review saved benchmark assessments and download its ranking input. Select the corresponding original audits and upload those two inputs. The check requires matching target model, reader, memory preparation/version, context settings and recorded seed; every audit question and benchmark condition must have comparable decided assessments. It rejects missing dataset provenance, missing adapter fingerprints, saved-answer reassessment, partial coverage and incompatible settings. Compare the two policies within each question set; never subtract scores across the different sets. A tie is displayed separately from agreement or reversed ordering. This read-only descriptive check does not establish independent validity, external file authenticity or general superiority; independent reviews, representative source subsets and repeated trials remain required. Live word-match scores alone do not complete Experiment C.

## Reporting checklist

- protocol ID, code commit, environment and dependency versions;
- run configuration and reproducibility fingerprints from every exported run;
- dataset/annotation identifiers, consent statement and de-identification process;
- all excluded cases, failed runs and retry decisions;
- per-condition sample size and every measured dimension, including unmeasured dimensions;
- representative synthetic or authorised failure traces, never hidden private context or credentials;
- clear separation of illustrative synthetic examples, local compatibility runs, pilot results and formal results.

## Deterministic reporting artifacts

After downloading an experiment CSV, run `scripts/generate_paper_artifacts.py INPUT_EXPORT.csv OUTPUT_DIRECTORY`. It produces a condition-overall table/chart and, when the export contains those rows, a dimension-comparison table/chart and detected-failure distribution table/chart. `paper_artifacts_manifest.json` records the input SHA-256, every generated artifact SHA-256, row counts and the generator's reporting boundary.

These files are deterministic presentation transforms only. They do not estimate significance, prove causality, fill in unmeasured dimensions, or make official external-benchmark claims. Preserve the CSV, manifest and frozen protocol with every reported figure; add any statistical analysis only under a separately declared analysis plan.

Statistical display safeguards (11 October 2026): one paired answer has no bootstrap interval, while its descriptive delta and exact sign result remain available. Multi-question intervals resample the observed questions; zero width does not establish population certainty or independence. Repeated-condition variation requires at least two scored results. Unknown configuration provenance does not establish a repetition. Condition identity is independent of display labels, and pending answer counts remain explicit alongside decided-case results.

For failure recall, report both decided-only confusion metrics and the complete reference inventory. Research metric v3 supplies full-reference recall and detected/missed/uncertain/missing counts: uncertain submissions count as failures not found, while missing reference-failure predictions prevent a complete score. No actual reference failures means recall is undefined. Do not apply the frozen recall threshold to the decided-only percentage or to a displayed rounded percentage. The saved-threshold checker compares supplied evidence using exact raw counts and the server-saved criteria. Upload predictions for the selected scenario only. The v2 checker verifies exact saved answers and automated verdict/category facts for that scenario and condition; missing, differing or ambiguous evidence prevents saved-result acceptance. It does not establish independent authorship or held-out sampling; these plots and numerical checks alone do not certify research success. For newly generated answers differing from corpus examples, label the actual saved answers through the existing review/blind-review workflow, then select **Check reviewed saved answers**. This reads resolved post-execution labels and the original frozen thresholds, with no uploaded files or new model calls. Missing labels and invalidated adjudication remain unmeasured. Recorded reviewer names alone do not verify independent human evaluation.
