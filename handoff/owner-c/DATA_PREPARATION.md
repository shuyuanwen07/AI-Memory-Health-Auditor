# Step 2: held-out data and human reference preparation

Status (5 October 2026): original custodian package received locally and moved to `handoff/owner-a-custodian/`. Integrity and schema checks passed; 8 scenarios match documented counts. Conversation IDs and exact normalised message texts do not overlap development. Human worksheets remain empty (0/130 for each annotator and adjudication); B subsequently supplied a no-exposure attestation via the user (see `owner_b_confirmation.json`); near-duplicate review remains pending. No human labels have been created or substituted. See `data_readiness.json` for executed checks.

## Inputs to obtain from Owner A

Obtain the original English custodian distribution described in `docs/OWNER_A_HANDOFF.md`. Place it in the already Git-ignored `handoff/owner-a-custodian/`, or provide its existing local path. Request the frozen manifest, held-out annotation dataset and source conversations, blind stages 1–3, annotation guide, blank independent worksheets, pending pilot package, AI decision records and custody/exposure history. Keep AI answer sheets separate from independent annotators.

A documents 8 held-out scenarios, 16 messages, 18 memories, 8 relationships, 16 accepted and 8 rejected candidate tests, 32 illustrative responses and 130 AI decisions. These counts are expectations, not measurements performed by C.

## Receipt checks

1. Record the received date, custodian, authorised recipients and package SHA-256 inventory. Do not revise the original distribution in place.
2. Run `python3 scripts/verify_owner_a_handoff.py --package handoff/owner-a-custodian --schema` against the original AI-reviewed distribution before any human-reviewed revision. This verifier intentionally expects pending human labels; do not use it to approve a later human-reviewed release.
3. Check conversation IDs, source-message IDs and normalised source texts for overlap with development, inspect near-duplicate scenarios, and record task-family overlap. Check references and declared dimension coverage. IDs alone do not establish independence.
4. Obtain an exposure declaration: whether any held-out content or answers informed B's implementation or settings. If exposed, disclose it and arrange a fresh holdout before claiming strict held-out validation.

## Independent human reference

Two actual annotators independently complete their own blank forms using staged packets and guidelines, without AI labels, automated verdicts or each other's labels. For response judgement, provide the response being judged while hiding the automated decision. Record pseudonyms, guideline version and completion dates; preserve raw worksheets unchanged.

Compare categorical labels and exact source-message sets. Record final decisions and reasons separately in the adjudication worksheet. Do not fill disagreements artificially, copy AI answers into human fields, or designate the assistant as a human annotator.

Create a separate human-reviewed dataset revision and matching pilot package after real review. Use the repository annotation validation and pilot analysis endpoints to record fingerprints, per-task coverage, raw agreement, Cohen's kappa where defined and readiness reasons. The existing default pilot criteria are at least 5 paired items per task, full paired/final coverage, no unresolved disagreements and kappa at least 0.6 where defined. Report actual results rather than editing labels to pass the gate.

## Boundary for later steps

The 32 authored answers are illustrative evaluator-validation examples, not measured target-model outputs. After step 3 produces actual responses, obtain blind human pass/fail and failure-dimension labels for those same response IDs before reporting automated-versus-human metrics on actual runs.

Step 2 is complete only after receiving and validating the held-out release, documenting split independence and custody, and freezing genuine reference labels with their provenance. Current development verification is recorded in `data_readiness.json`; it does not establish held-out readiness.
