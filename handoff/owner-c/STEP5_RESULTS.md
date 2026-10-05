# Owner C step 5: final metrics and limitations

Frozen baseline: a241e3d; rule-based WEAK target; seed 7; maximum 20 tests per scenario. Eight held-out scenarios produced nine tests across seven scenarios. The final response reference was adjudicated and confirmed by the user in step 4. These results are a limited deterministic engineering validation.

## Target response scores

| Dimension | Tests | Automated pass score | Adjudicated reference pass score |
| --- | ---: | ---: | ---: |
| Accuracy | 8 | 100% (8/8) | 100% (8/8) |
| Freshness | 0 | Not measured | Not measured |
| Conflict resolution | 0 | Not measured | Not measured |
| Appropriate use | 1 | 100% (1/1) | 0% (0/1) |

The automated macro-average is 100%; the reference macro-average is 50%, averaging only the two measured dimensions equally. The reference per-test pass rate is 88.9% (8/9). Macro score and per-test pass rate use different denominators and must not be interchanged. Neither is a four-dimension score.

## Evaluator validity

Failure is the positive class. Comparison with the final reference gives TP=0, FP=0, TN=8, FN=1.

| Metric | Result | Denominator / interpretation |
| --- | ---: | --- |
| Evaluator accuracy / agreement | 88.9% | 8 correct judgements / 9 responses |
| False-positive failure rate | 0% | 0 falsely flagged failures / 8 reference passes |
| Failure recall | 0% | 0 detected failures / 1 reference failure |
| Failure precision | Undefined | No automated failure predictions |
| Failure F1 | 0% | 2TP / (2TP + FP + FN) = 0/1 |
| Evaluator-reference Cohen's kappa | 0.000 | Automation predicts PASS for every response |

The evaluator misses A019-T002: the response repeats the colourful-chart preference rather than applying the current grayscale submission requirement. This is a false-negative failure, not a false-positive failure. With all predictions PASS, high raw agreement is consistent with zero chance-corrected agreement and zero failure recall.

## Raw worksheet agreement

Before final adjudication the two saved worksheets agree on PASS/FAIL for 8/9 responses (88.9%; descriptive kappa 0.609), and on both verdict and failure dimension for 7/9 responses. The two disputed fields were preserved and resolved explicitly. These figures are descriptive worksheet comparisons, not evidence of independent blind human inter-rater reliability: reviewer 1 received assistant suggestions before revision, and reviewer 2 independence is not verified. Evaluator-reference kappa (0.000) and worksheet-to-worksheet kappa (0.609) compare different label pairs.

## Limits

- Only nine tests and one reference failure were observed; recall is 0/1, not a stable estimate of population performance.
- Freshness and conflict resolution are unmeasured. A004 produced no tests. Source scenarios containing those themes do not establish that the generated suite tested those dimensions.
- Several prompts are generic. Adjudication used the non-exhaustive interpretation of “state the relevant fact only”; alternative reasonable interpretations should be disclosed.
- Generated expectations came from the same extractor outputs used in this engineering pipeline. Extraction omissions and incorrect relationships require separate reference-based evaluation; a passing generated test does not establish extraction correctness.
- Only one deterministic WEAK condition was run; no strategy improvement, model comparison, or stochastic variance claim is supported.
- This source-only pipeline is distinct from the persisted application target-memory lifecycle. The baseline was not tuned after seeing held-out results.
- Reference provenance remains qualified; these materials do not establish completion of a formal two-independent-human annotation gate.

## Reproduction and artifacts

Run `python3 scripts/calculate_owner_c_metrics.py` after step 4. The script checks final-adjudication, raw-review, configuration and suite hashes and validates exact response-ID coverage. It uses the existing AuditorValidityService and MetricsService and cross-checks the expected contingency counts. Detailed numbers are in `step5_metrics.json` and `step5_dimension_scores.csv`; actual response evidence remains under the Git-ignored local artifact directory. Original worksheets and frozen business code are unchanged.
