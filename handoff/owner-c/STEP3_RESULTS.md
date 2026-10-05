# Owner C step 3 engineering run

B baseline commit a241e3d is unchanged. A reproducible source-only engineering runner is available at `scripts/run_owner_c_heldout.py`. It uses B's frozen extractor, generator, WEAK rule-based target and evaluator. C recorded seed 7 and a maximum budget of 20 per scenario before execution. The budget is a C choice, not a setting attributed to B.

The suite was saved and hashed before execution. Local ignored artifacts are in `artifacts/local/owner-c-heldout-v1/`: configuration, frozen suite and extracted memories, freeze metadata, responses, evaluations, summary and two blank actual-response review worksheets. IDs are prefixed by scenario to avoid collisions. Target invocation strips expected behaviour and uses only source-derived first-record context. No cloud provider or operational database was used.

## Findings

Eight scenarios produced nine tests: eight accuracy and one appropriate-use test. All nine passed the lexical automated evaluator. Freshness and conflict resolution have zero tests and their scores are unmeasured. A004 produced an empty suite. This is an extraction/generation coverage limitation of the frozen source-only pipeline, not evidence of perfect performance across the four dimensions. No implementation or settings were tuned after observing the holdout.

This runner follows the engineering investigation style; it does not claim to reproduce the persisted web application target-memory lifecycle or a formal human-gated experiment. Generated expected behaviours come from extractor outputs, so these scores do not establish extraction correctness. A separate evaluation against the reviewed held-out references is needed to expose omissions and relationship failures. If a reference-based suite is later added, record it as a separate protocol condition rather than replace this frozen run.

## Next step

Use `actual_response_review_1.csv` and `actual_response_review_2.csv` for actual-output judgement while hiding automated decisions. Reviewers need the original source conversations. The existing 32 authored examples and their labels are separate units and must not be treated as labels for these nine outputs. Reference provenance must remain accurately described; the first existing reference sheet was AI-assisted then manually confirmed.
