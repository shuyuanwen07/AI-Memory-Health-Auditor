# Evaluator calibration

Target Memory Health measures answers under a controlled memory policy.
Calibration measures whether the auditor detects and classifies independently
human-confirmed errors. Higher target pass rate does not imply a better auditor.

## Available workflows

- **Auditor reliability** lists saved human-reference evidence and blind-review batches.
- `/blind-review/:runId` withholds model identity, automated decisions, judge reasons
  and other reviewers' labels on the server. It includes the complete source history.
- The visible audit report collects reference/adjudication labels only because it
  has already exposed automated results. Its link to the separate blind-review page
  is for a different reviewer who has not seen those results. The application cannot
  verify what a person previously saw or that a pseudonym represents a distinct human.
- Blind-review progress is explicitly session-local; refresh clears the counter,
  not persisted labels. Category guidance does not expose the proposed test dimension.
- Download blank review materials: all saved answers, proposed references, full source,
  empty labels and a stable content hash. No pass/fail sampling and no automatic labels.
  This material is for reading; final operational labels are submitted through the
  blind-review page. It is not an import-ready gold annotation release.
- Research Workspace validates annotation releases and double-annotation readiness.
- `POST /api/v1/research/evaluator-calibration/analyse` calculates a request-scoped
  calibration report without persisting raw submitted research labels.

Two reviewers work independently before adjudication. Labels require real human
source verification; AI-assisted labels must retain that provenance. Independently
review complete predeclared batches or freeze a stratified sample before reviewing.
Include system passes, failures and abstentions. A disagreement-only sample cannot
estimate population accuracy or failure recall.

## Metrics and denominators

Failure is the positive class. Decided human-labelled responses provide binary
confusion counts, accuracy/agreement, failure precision/recall/F1, specificity,
false-positive rate and Cohen's kappa, overall and by exercised dimension.
Decided coverage, abstention counts and labelled abstention rate remain visible.
A null metric is unmeasured, never zero.

Conditional failure-category agreement uses jointly detected typed failures.
Joint detection-and-classification recall uses human typed failures, including
misses and abstentions. Test dimension is not an observed failure classification.
Separate label provenance from metric arithmetic: numbers computed using unverified
labels do not establish independent reliability.

The versioned request carries dataset/review-set identifiers and its SHA-256
fingerprint. Duplicate IDs and inconsistent verdict/category pairs are rejected.
Related questions/repeats are correlated: use histories as uncertainty/resampling
units for formal claims, not individual replies as independent samples.

## Controlled reviewer comparison

New default comparisons execute the model-generated suite once per target/policy/
repetition and reuse its saved replies for rule and hybrid review. Persisted source
run/response receipts identify the pairing. A copied answer is no second target
request and no independent sample. Reuse checks suite content, accepted quality and
frozen target settings; ordinary execute/retry follows the saved reuse intent.
Historical runs without receipts remain separate-execution exploratory comparisons.

## Pending empirical evidence

Freeze untouched source scenarios, independent defect inventory, reference release,
thresholds, model and policy versions before collection. Then report representative
coverage, disagreements, adjudication, precision/recall, classification and uncertainty.
A passing software test suite establishes behaviour of tested paths, not accuracy
of all future auditor decisions.
