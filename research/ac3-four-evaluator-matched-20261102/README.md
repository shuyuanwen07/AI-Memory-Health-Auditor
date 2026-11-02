# AC3 matched evaluator comparison (2 Nov 2026)

This package preserves an additional same-answer comparison for the existing AC3 cohort. It includes the 120 synthetic source/question/answer inputs, the previously confirmed AI-assisted reference labels, saved rule and Astra MAX judgments, every raw Luna and Qwen response, the protocol, analysis, and scripts.

## Results

| Evaluator | Reference failures detected | False alarms on 51 reference passes | Decided |
| --- | ---: | ---: | ---: |
| Archived rule baseline | 55/69 | 18/51 | 120/120 |
| Qwen 3 1.7B | 0/69* | Not measurable | 0/120 |
| GPT-6 Luna | 60/69 | 0/51 | 120/120 |
| GPT-6 Astra MAX | 63/69 | 0/51 | 120/120 |

*Qwen returned no usable pass/fail verdicts: 17 outputs were uncertain and 103 failed the output contract. Counting abstentions as misses gives the conservative 0/69; this is not a claim of zero semantic accuracy or zero false positives.

## Limits

All evaluators saw the same 120 previously observed answers from 30 related synthetic histories. This is not held-out evidence. The model graders use the same taxonomy rubric and answer context, but providers, models, and effort settings differ. The deterministic rule baseline uses its archived structured inputs (including expected behaviour), so this is not a fully controlled model-only comparison. The reference judgments were AI-assisted and were previously confirmed by the user as independently checked by two people. Results should not be generalized to natural conversations or used as a universal model ranking.

The scoring scripts require the repository backend environment. `four_evaluator_matched_20261102.py` performs the Luna and Qwen calls; the saved responses are already included, so no API call is needed to inspect or re-analyse this package. Never include provider API keys in the package.
