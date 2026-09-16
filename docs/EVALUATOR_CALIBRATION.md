# Evaluator Calibration

The Memory Health score measures a **controlled target agent**.  Evaluator
calibration measures a different question: whether the Auditor's automated
PASS/FAIL verdicts agree with independent human review.

## Input contract

`app.evaluator.calibration.EvaluatorCalibrationRequest` accepts a de-identified
and versioned review set. Each case has a stable `case_id`, the test dimension,
an automated evaluator verdict, and a human verdict. Failure types may be
recorded only for FAIL cases. The service validates duplicate identifiers and
internally inconsistent verdict/type combinations before calculating metrics.

The module deliberately does not write these labels to operational audit
tables. Research labels should be retained only in the team's approved,
access-controlled research storage. The returned SHA-256 fingerprint identifies
the exact request used in a reported result.

## Reported measures

Failure is the positive class. The report provides, overall and for each test
dimension:

- true/false positives and negatives;
- agreement, accuracy, failure precision, recall and F1;
- specificity, false-positive rate and Cohen's kappa.

When both the human and automated evaluator identify a failure and both assign
a type, the report additionally provides a human-row/evaluator-column confusion
table, exact failure-type agreement, and label coverage. Failure-type agreement
is intentionally conditional on both systems detecting a failure; missed and
spurious failures remain visible in the binary confusion metrics.

## Integration point

An API endpoint or a notebook may call:

```python
report = EvaluatorCalibrationService().analyse(request)
```

The service is pure and request-scoped. A future route should require only
authorised, de-identified research labels and return `EvaluatorCalibrationReport`;
it should not persist raw reviewer submissions by default.
