# Owner C final handoff

## Outcome

The frozen deterministic engineering pipeline produced nine tests from eight synthetic held-out scenarios. Seven scenarios had tests; A004 had none. Human-adjudicated reference labels contain eight passes and one appropriate-use failure. The automatic evaluator passed all nine and missed that failure.

Evaluator agreement is 88.9% (8/9), false-positive failure rate 0% (0/8), failure recall 0% (0/1), failure precision undefined (no predicted failures), failure F1 0%, and evaluator/reference Cohen's kappa 0.000. These results measure this small run; they are not official benchmark or general model-performance results.

## Frozen settings

| Setting | Value |
| --- | --- |
| B commit | a241e3d28ee58bdd5a66bfd724f8aa02ab315bb9 |
| Provider / target | rule_based / rule-based-target-ai |
| Condition | WEAK; weak_first_hit first-record context |
| Temperature / seed | 0 / 7 |
| Maximum test budget | 20 per scenario (C pre-run choice) |
| Extractor | RuleBasedMemoryExtractor |
| Generator / version | RuleBasedTestGenerator / rule-based-v4 |
| Evaluator / version | RuleBasedBehaviourEvaluator / rule-based-v4 |
| Prompt template | rule-based-v1 |

The runner is a source-only engineering pipeline, not a persisted web-app audit. All target records come from the source extractor, and evaluator-only expected behaviour is stripped before target invocation. Source hashes, component hashes and a pre-execution suite hash are retained.

## Target scorecard

Accuracy: 8 tests, reference score 100%. Appropriate use: 1 test, reference score 0%. Freshness and conflict resolution: not measured. Reference macro-average over the two measured dimensions is 50%; reference per-test pass rate is 88.9%. The automatic macro-average is 100%, illustrating why automation must be checked against reference judgement.

## Evidence files

`step5_metrics.json` and `step5_dimension_scores.csv` contain the final numbers. `STEP5_RESULTS.md` gives definitions and denominators. `FAILURE_CASE.md` contains the critical example. The local delivery ZIP additionally contains original actual-output review sheets, the final adjudication, frozen suite, execution results, configuration, source conversations and reproducibility scripts. Package `manifest.json` lists SHA-256 values for each included file.

## Reproduce / verify

Use the project checkout at B's frozen implementation with C scripts added. Python must support the backend's declared dependencies; NumPy/cloud services are not required for these scripts. From the repository root:

```sh
python3 scripts/calculate_owner_c_metrics.py
```

This checks frozen suite/configuration/final-adjudication/raw-review hashes and recomputes metrics using existing services. To run a separate fresh engineering replication, without overwriting the saved run:

```sh
python3 scripts/run_owner_c_heldout.py --output artifacts/local/owner-c-heldout-replication
```

Replication IDs/questions are deterministic; timestamps differ. Keep the adjudicated original run for the final report. Do not replace raw reviews or infer new human labels for a replication. The comparison script prepares a draft for new review work; rerunning it is not needed to validate the already-finalised reference.

## Validation actually performed

Original A development/custodian manifests and backend schema checks passed before worksheet edits. Run scripts validated frozen component bytes against B, unique scenario-qualified test IDs, suite hashes and complete response coverage. Review comparison validated identity, allowed labels and source IDs. Metric computation passed hash checks and independently checked TP=0, FP=0, TN=8, FN=1 and the macro-score denominator. Business code remains byte-identical to B. A local attempt to rerun the seven B regression tests could not start because pytest is not installed in the current Python environment; B's reported 136-pass backend run is a supplied attestation, not a C rerun.

## Limits and next owner

D should present the detected evaluator miss and coverage gaps, not claim four-dimension validation, strategy improvement or a formal independent-double-annotation study. Generic prompts, nine tests, only one reference failure, shared extractor-derived expectations, no freshness/conflict tests, and qualified review provenance limit interpretation. No post-holdout tuning was performed. D can use the frozen implementation for the product demonstration, but saved engineering run artifacts are not operational UI audit-history entries.
