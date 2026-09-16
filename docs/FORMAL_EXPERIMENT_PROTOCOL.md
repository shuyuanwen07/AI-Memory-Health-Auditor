# Frozen formal experiment protocol

**Protocol ID:** `mha-formal-v1`  
**Status:** template to freeze before collecting formal results  
**Scope:** controlled memory-policy evaluation; this document does not report results.

## Research questions

1. Under a fixed underlying target model and frozen question suite, how do controlled memory strategies affect Accuracy, Freshness, Conflict Resolution and Appropriate Use?
2. Does a scoped/context-aware strategy improve contextual use without reducing performance on stable facts?
3. Are observed differences consistent across repetitions and locally permitted benchmark-compatible subsets?

## Conditions and controls

Compare only predeclared conditions. The minimum comparison is `weak_first_hit`, `strong_rule_based`, and `strong_score_based`; add `scope_aware` only when its policy version is frozen. Keep the following fixed within each experiment group:

- authorised/de-identified conversation set and reviewed ground truth;
- canonical shared test suite, suite mode, seed, prompt-template fingerprint and acceptance decisions;
- target provider/model, temperature, retry policy and target-memory writer version;
- evaluator provider/model and evaluator version;
- memory-maintenance policy, retrieval budget and software revision.

Run each condition at least three times when a cloud model is involved. The deterministic local baseline may be run once as a reproducibility check, but should not be used to infer provider variance.

## Data, consent and labelling

Use only synthetic or explicitly authorised, de-identified conversations. Store source conversations separately from research annotation files. Before formal collection, freeze a versioned annotation release containing memory, relationship, test-quality and evaluator labels; record the validation SHA-256 fingerprint. Two annotators independently label a predefined overlap subset, disagreements are adjudicated without seeing automated outputs, and Cohen's kappa is reported where labels permit it.

## Pilot and freeze gate

Run a pilot before formal evaluation. Resolve unclear memory boundaries, leaked-answer tests, ambiguous expected behaviour, and evaluator disagreements. Do not silently change prompts, labels, policies, benchmark mapping or sample membership after the freeze. Any change creates a new protocol ID and a new experiment group.

## Primary outcomes and analysis

The primary outcome is macro-average Memory Health across measured dimensions. A zero-test dimension remains unmeasured and is excluded, never converted to zero. Report each dimension's pass/total/percentage, failure categories and traceable evidence.

For shared-suite comparisons, align outcomes using the canonical `suite_test_id`. Report condition means, population standard deviation across repetitions, paired candidate-minus-reference percentage-point delta, deterministic bootstrap 95% interval and exact two-sided sign-test p-value. These are descriptive/pilot support statistics unless the team preregisters a confirmatory analysis and sample size.

Separately report Auditor validity against frozen manual labels: extraction and relationship Precision/Recall/F1, test validity, evaluator failure-detection Precision/Recall/F1/Accuracy/FPR, and agreement. Do not combine Auditor validity and Target Agent health into one score.

## External benchmark-compatible subsets

LongMemEval, LoCoMo and BEAM inputs must be independently obtained under their applicable licences. This application only accepts caller-supplied local-compatible JSON and uses an in-memory, deterministic reference-overlap baseline. It neither downloads nor retains those sources and does not implement official loaders or scorers. Label all resulting numbers **local compatibility results**, not official benchmark scores. Record the upstream dataset version, licence/citation, source fingerprint, adapter/runner version and the explicit mapping from external categories to the four Memory Health dimensions.

## Reporting checklist

- protocol ID, code commit, environment and dependency versions;
- run configuration and reproducibility fingerprints from every exported run;
- dataset/annotation identifiers, consent statement and de-identification process;
- all excluded cases, failed runs and retry decisions;
- per-condition sample size and every measured dimension, including unmeasured dimensions;
- representative synthetic or authorised failure traces, never hidden private context or credentials;
- clear separation of illustrative synthetic examples, local compatibility runs, pilot results and formal results.
