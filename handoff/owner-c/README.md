# Owner C handoff to Owner D

Prepared on 5 October 2026 (Australia/Sydney). Owner C completed a limited held-out engineering run, actual-response review finalisation, evaluator comparison and final metrics against B's frozen commit `a241e3d28ee58bdd5a66bfd724f8aa02ab315bb9`. The frozen business implementation is unchanged. This delivery does not establish a completed formal independent-double-annotation study.

## Start here

1. Read `OWNER_C_HANDOFF.md` for results, scope, files and reproduction.
2. Use `STEP5_RESULTS.md` for report-ready tables and limitations.
3. Use `FAILURE_CASE.md` to explain the missed appropriate-use failure.
4. Use `D_PRESENTATION_NOTES.md` for demonstration/report talking points.
5. Use `step5_metrics.json` and `step5_dimension_scores.csv` for numbers; do not infer scores for unmeasured dimensions.

The local ZIP in `artifacts/local/owner-c-delivery/` includes the run evidence, raw actual-response review sheets, final adjudication, source-only input, scripts and manifest. It is separate from public Git-tracked documentation and is intended for authorised local team handoff. Source/answer artifacts remain Git-ignored.

## Baseline and provenance

A and B are inherited through B's final frozen commit. B confirmed that no held-out content was viewed or used for development/tuning; see `owner_b_confirmation.json`. The confirmed seed is 7, while the old investigation script's seed 42/budget 100 are historical settings. C chose budget 20 and the WEAK first-record condition before running.

The eight-scene custodian input passed original checksum/schema validation before working annotation sheets were filled. Human verification of reference sheets was confirmed by the user. The first reference sheet was AI-assisted, and the actual-response first sheet was revised after assistant suggestions; these records must not be represented as two independent blind human annotations. Original worksheets and adjudication decisions are preserved.

Steps 1–2 records document baseline and data readiness; steps 3–5 record execution and evaluation. The remaining scope limitations are explicit in the final report. The C documentation and scripts belong on `codex/owner-c-validation`; held-out source data and local delivery archives remain excluded from Git.
