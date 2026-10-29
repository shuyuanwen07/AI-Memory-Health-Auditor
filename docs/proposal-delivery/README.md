# Proposal delivery working set

This folder contains proposal traceability, a reproducibility checklist, and human handoff materials. The team's requested deliverables are the experiment report at `docs/EXPERIMENT_REPORT_2026-10-28.md` and the presentation with four-speaker notes. The report is the sole final report in this package. The supporting files are not signed evidence that every acceptance criterion passed.

## Files

- `REQUIREMENTS_TRACEABILITY.md` maps the approved proposal requirements to code locations, evidence, and outstanding checks.
- `REPORT_DRAFT.md` is a supplementary project narrative retained for internal background only. It is not a submission deliverable; do not distribute it as a separate paper or final report.
- `REPRODUCTION_AND_DEMO.md` describes a clean source-package check and an offline demo fallback.
- `CLEAN_START_VERIFICATION.md` records the isolated package, migration, build, focused frontend and backend checks, and the latest container-health verification boundary.
- `NOVICE_WALKTHROUGH.md` is intentionally blank until a real participant session occurs.
- `MEMBER_CONTRIBUTIONS.md` is intentionally blank until each member confirms their actual contributions.
- `MANUAL_REVIEW_HANDOFF.md` identifies the 14 in-app candidate memories awaiting review, the historical three tutor-loop uncertainties and 36-answer packet, the current-source 24-answer tutor-loop packet, the current-source six-run 48-answer packet, the comprehensive 216-item A/B/extraction review packets, the 84-answer C grader-review packet, and the remaining team confirmations.
- `../../output/proposal-delivery/HUMAN_REVIEW_MASTER_2026-10-28.json` consolidates the open source-review material into one readable JSON file: 686 review records across eight queues, with source evidence and blank label fields. The earlier CSV/packet files are preserved unchanged as provenance records.
- `../../output/proposal-delivery/live-presentation-demo-current-source-2026-10-28/` contains the current-source six-run same-suite experiment, answer report, CSV, reproduction bundle, passing offline verification receipt, and 48-answer source-review packet. Keep the review packet's `review-key-private.json` with the custodian.
- `../../output/proposal-delivery/live-current-source-repair-2026-10-28/` contains the current-source diagnosis-led repair replay, full reproduction bundle, paired comparison summary, and 24-answer source-review packet. The team has seen the outcomes; manual review can check answers but cannot count as independent blind evidence.
- `SOURCE_BINDING.md` records which source snapshot is bound to each saved experiment and the exact code package reconstructed from the Phase 4 protocol's 136-file hash manifest.
- `../../output/proposal-evaluation/assisted-human-return-2026-10-28.json` records the complete 216-item assisted human return. It preserves the declared AI assistance and result exposure and does not count the return as independent validation.
- `../../output/presentation/ELEC5623_AI_Memory_Health_Auditor_Presentation_Final.pptx` is the final, updated presentation; its slide notes contain the four-speaker scripts, so there is no separate Word script.
- `../../output/proposal-delivery/phase4-app-source/phase4-app-source.zip` is the source-only reconstruction checked against all 136 file hashes frozen in the Phase 4 protocol. It is separate from the current assessed-source package and does not include runtime dependencies or experiment data.
- `../../output/proposal-delivery/phase4-c-review-2026-10-28/README.md` documents the 84-answer LongMemEval grader-review packet and its hashes. The private condition key must stay with the custodian.
- `../EXPERIMENT_REPORT_2026-10-28.md` is the sole final report requested by the team. It separates the current-source and earlier-source tutor loops from proposal A/B/C and preserves the unresolved results.
- `../proposal-experiment-audit.md` and `../../research/evidence-20261027/` document the restored A/B/C source records and their review limits. The research archive is separate from the assessed-source ZIP and includes reviewer identity/outcome bindings; it is not a blind-review packet.

## Evidence labels

- **Implemented**: code or a UI path exists.
- **Verified**: a saved run, test receipt, or reproducible check is bound to a stated source/configuration.
- **Historical**: genuine evidence from an earlier source snapshot; it does not automatically verify current `main`.
- **Pending**: the required original record or a human decision has not been checked.
- **Not established**: the available evidence cannot support the proposal's formal claim.

Do not treat an implemented feature as a verified research result. Keep synthetic engineering checks, live model calls, model-as-judge labels, and independent human labels distinct. Do not infer human confirmation from a blank review form or an AI-assisted worksheet.
