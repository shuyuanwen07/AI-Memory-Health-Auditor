# Owner D report and demonstration notes

## Suggested explanation

“We evaluated B's frozen deterministic baseline on eight synthetic held-out scenarios. The extraction/generation path produced nine tests, covering accuracy and appropriate use. The automated judge passed all responses, but review found one contextual-use failure: the target repeated a colourful-chart preference when the current submission required grayscale. Agreement was 8/9, but failure recall was 0/1. This demonstrates both a concrete evaluator limitation and why coverage and reference review matter.”

## Report numbers

Use the scorecard in STEP5_RESULTS.md. Distinguish response pass rate (8/9, 88.9%) from the equal-weight dimension macro-average (50% over only two measured dimensions). Label freshness and conflict resolution “not measured”. Show the failure-positive confusion counts TP=0, FP=0, TN=8, FN=1. Precision is undefined, not zero; failure F1 is 0% by the direct count formula.

## Demonstration preparation

Use the project's normal Docker Compose workflow and README for the product demo. The saved C run is an offline engineering artifact and will not appear automatically in Dashboard history. A newly executed UI audit is a separate demonstration run; do not present its configuration or output as identical to the frozen C run without verifying equivalence.

Capture any desired product screenshots during D's demonstration, label them as demonstration screenshots, and use the saved C tables/failure evidence for the reported experiment. D remains responsible for building slides, capturing screenshots and rehearsing.

## Claims to preserve

State the small sample and missing dimensions. No real cloud model, strategy comparison, repeated stochastic conditions or official benchmark was evaluated. Review provenance does not establish two independent blind annotators. A high agreement percentage alone does not imply reliable failure detection.
