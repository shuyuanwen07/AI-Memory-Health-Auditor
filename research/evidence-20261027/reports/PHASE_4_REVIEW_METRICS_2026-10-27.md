# Phase 4 — retrospective review metrics (27 October 2026)

These are descriptive, conditional metrics based on the two returned reviews and user-provided recheck decisions. The review recheck exposed both first-round judgments; it is not an independent blind adjudication. Source provenance explicitly says AI draft; the user subsequently states that description was incorrect and Chongtai personally judged the items. Both the original declaration and user-reported correction are retained. They have not been independently verified. The old automated scores and source evidence remain unchanged.

## Answer-level failure detection

Comparison uses saved-answer evaluator v65 against review agreement. Unresolved human responses are excluded from confusion counts. The labels below include responses to questions whose validity remains uncertain; they are not a validated-question-only reliability estimate.

| Study | Reference agreed / total | TP | FP | FN | TN | Automated uncertain | Precision (TP/(TP+FP)) | Recall on decided outputs (TP/(TP+FN)) | FPR (FP/(FP+TN)) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 30/36 | 27 | 0 | 0 | 3 | 0 | 27/27 = 100% | 27/27 = 100% | 0/3 = 0% |
| B | 71/72 | 27 | 1 | 8 | 34 | 1 | 27/28 = 96.43% | 27/35 = 77.14% | 1/35 = 2.86% |

B also has one agreed human failure with an automated uncertain verdict. Counting that failure in the reference denominator gives 27/36 = 75.00% reference-inclusive recall. A has six unresolved answers; B has one. These are not silently scored as passing, nor assumed to be failures. Small samples and related scenarios prevent generalisation.

## Other review outcomes and denominators

- Failure classification: 51 of 51 automatically classified items with an agreed typed human failure label match (100%). There are 61 agreed typed human failures overall, so 51/61 = 83.61% joint detection-and-classification recall under the implementation's definition; 10 typed failures were not correctly classified. Two additional failure-type disagreements are excluded from this typed-reference denominator.
- Question validity: 35/48 are agreed valid; 13/48 are both marked uncertain. The 35/35 = 100% conditional rate among decided items must not be presented as 100% overall validity.
- Extraction candidate precision: 21/27 candidates are agreed valid, six remain disputed or uncertain. 21/21 = 100% is conditional on decided candidates; it is not full-set precision.
- Reference-unit recall: not calculated. Six coverage decisions remain unresolved, including three full-coverage marks that depend on candidates marked uncertain; those three are withheld for analysis only and the reviewer records are unchanged. The 24 proposed reference units are not an established complete atomic-fact universe.
- Relationship classification: 6/9 = 66.67% on the nine selected source pairs; all nine reference relation labels agree. This is not an exhaustive relation benchmark.
- Critical errors: 0 agreed critical among 101 response judgments with an agreed pass/fail and agreed critical label; seven response judgments are unresolved. One of these is explicitly flagged critical by Shuyuan but uncertain by Chongtai; zero agreed critical does not mean no critical errors.

## Experiment A discovery

The frozen inventory has three defects per history. Under the two recheck records, history H1 direct questions mapped 1/3 frozen defects, fixed template 0/3, and contextual 0/3; each condition contains four answer judgments and completed mappings. These are retrospective descriptive counts for one history, not formal discovery rates or evidence of method superiority; some relevant question-validity judgments are uncertain. The other six conditions include unresolved answer judgments and therefore lack complete condition-level discovery denominators. An H3 direct response was mapped to STALE, but that condition also includes an unresolved answer. No uncertainty is imputed to complete the rates and the later broader defect inventory is not applied retroactively.

## Evidence and next steps

Machine-readable inputs, source hashes, derived denominators, corrections and unresolved list are under `artifacts/local/phase4-formal-review-20261027/user-reported-correction-20261027/recheck-analysis-20261027/`. `analysis.json` also records three analysis-only coverage adjustments. Actual reviewer values are in the transcription files. `remaining-issues.html` lists unresolved/disputed cases. Formal independent reliability and complete A discovery remain unestablished; further blinded independent evidence or clearly documented actual adjudication is needed for claims requiring it. No review API writes or target-model calls were made in this analysis.
