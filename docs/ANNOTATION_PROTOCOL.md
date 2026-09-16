# Human annotation and research-validity protocol

This protocol turns the Auditor from a useful engineering demonstration into a defensible university experiment. It is intentionally lightweight: the seed file is a reference format and a calibration set, not a claim of population-level evidence.

## Research questions and unit of analysis

Record the following before formal runs are started:

1. Does a memory strategy improve each Memory Health dimension over the weak first-hit baseline when both conditions receive the same test suite?
2. Does the Auditor correctly extract memories and their relationships against independently created human labels?
3. Does the Auditor's evaluator agree with a human judgement of each target response?

Use one **conversation** as the extraction unit, one **gold memory** as the memory/relationship unit, one **test** as the test-generation unit, and one **target response** as the evaluator unit. Do not merge these denominators.

## Dataset and annotation format

The versioned seed set is [seed_annotations.json](../datasets/annotation/v1/seed_annotations.json). It is validated by `AnnotationDataset` in `backend/app/schemas/annotation.py`. Start new annotation work from [annotation_template.json](../datasets/annotation/v1/annotation_template.json), retaining the format and assigning a new dataset version.

Before a pilot or formal analysis, submit the frozen JSON to `POST /api/v1/research/annotations/validate` and record the returned SHA-256 fingerprint, dataset ID and dataset version. The endpoint validates only; it does not retain participant data. For automatic reporting, use `POST /api/v1/research/validity/report` with the same dataset and a separately reviewed prediction mapping. In particular, an annotator must explicitly map each extracted candidate to at most one gold memory (or leave it unmatched); automatic string similarity is not an acceptable hidden matching rule.

Each gold memory must be atomic, canonicalised in English, linked to its exact source messages, and optionally linked to another gold memory only as `UPDATE`, `CONFLICT`, or `CONTEXTUAL_OVERRIDE`.

- `UPDATE`: the source memory is later and replaces the target for the same fact.
- `CONFLICT`: both records cannot safely be used together and no priority is established.
- `CONTEXTUAL_OVERRIDE`: a narrower current requirement overrides a general preference in that context.

Annotators should not infer unstated preferences or facts. If a claim is ambiguous, flag it for adjudication instead of inventing a memory.

For each proposed behavioural test, label `test_type` as `direct`, `contextual`, `paraphrased`, or `indirect`; then label it `accept` only if it is grounded in supplied memories, has observable expected behaviour, and does not reveal its answer in the prompt. Rejected tests remain in the dataset so test validity can be reported.

For every sampled target response, label pass/fail, failure dimension when failing, a short reason, and the exact supporting memory IDs. A response that makes an unsupported choice in an unresolved conflict fails conflict resolution.

## Practical double-annotation procedure

1. Build scenarios that cover all four dimensions, including positive and negative cases. Keep an immutable copy of the source, IDs and annotator instructions.
2. Two annotators independently label the same pilot set without seeing model output, each other's labels, or system labels.
3. Compare annotations, discuss only disagreements, and record the final adjudicated label plus a short decision note. Do not overwrite individual raw annotations.
4. Update the written guidelines once after pilot calibration. Freeze the guideline version, dataset version, prompts, test budget, provider/model versions, temperature and seed before the formal evaluation.
5. A third team member, if available, adjudicates unresolved disagreements. Report both pre-adjudication agreement and adjudicated results.

For a practical project, aim for at least 20 independently labelled conversations/scenarios and enough valid tests to cover every dimension. Treat the included one-conversation seed set as a format example only.

## Metrics to report

For memory extraction, match a predicted memory to a gold memory only when the canonical claim and cited source evidence refer to the same fact. Report:

```
precision = matched predicted memories / predicted memories
recall    = matched predicted memories / gold memories
F1        = 2 × precision × recall / (precision + recall)
```

For relationships, evaluate the type and the ordered source-target pair together. Report relationship precision, recall and F1. Report test validity as accepted, grounded generated tests divided by all generated tests sampled for review.

For evaluator reliability, use human response labels as the reference. Report evaluator precision, recall, F1, accuracy, and false-positive rate for the chosen positive class (state whether “pass” or “failure” is positive). Include a confusion matrix and report results by dimension.

For inter-annotator agreement, report percent agreement and Cohen's kappa for categorical labels (memory inclusion, relationship type, test accept/reject, pass/fail and failure dimension). For span/source-message selection, report exact-set agreement in addition to a short qualitative disagreement log. Kappa is an agreement diagnostic, not a substitute for adjudication.

For strategy/model comparisons, use one frozen shared suite per experiment group. Run every condition on the same test IDs, retain per-test paired outcomes, repeat stochastic conditions, and report mean, standard deviation, number of runs and valid-test coverage. Do not describe score differences as conclusive when the sample is too small; show the failures and paired evidence.

## External benchmark compatibility

The optional LongMemEval-compatible adapter is a format boundary, not an execution claim. Use it only after independently obtaining the official data under its applicable licence. Validate a local source file through `POST /api/v1/research/benchmarks/longmemeval/validate`, record the adapter version and source fingerprint externally, then decide in the formal protocol which benchmark cases/dimensions are in scope. The repository includes only a synthetic two-case compatibility sample; do not call it LongMemEval or report its numbers as benchmark results.

## Consent, privacy and retention

Only import conversations for which the owner has explicitly authorised this audit and this research use. Prefer synthetic or de-identified scenarios in repositories, demonstrations and reports. Before sharing annotation files, remove names, account details, emails, phone numbers, addresses, access tokens, proprietary code, and unnecessary sensitive personal information.

Keep any identifiable source data outside version control and restrict it to approved team storage. Store a consent/provenance note and a de-identification note with every dataset version. Do not send source conversations to an external model provider unless the participant authorisation covers that processing and the project supervisor's data-handling guidance permits it. Delete or securely remove source data when the agreed retention period ends.

## What to include in the final report

State the dataset version, number of conversations, annotators, agreement process, final denominators, provider/model and strategy settings, frozen shared-suite configuration, and all exclusions. Include representative pass and failure evidence, but never identifiable source text.
