# AC2: complete original-ten development retest

Start with [the retest report](../../docs/AC2_TEN_SCENE_RETEST_20261101.md),
[proposal evidence status](../../docs/PROPOSAL_STATUS_20261101.md), and the
[latest presentation](Memory-Auditor-Presentation-20261101-AC2-Ten-Scenes.pptx).
The four-speaker scripts are embedded in slide notes.

The exact ten original source histories are retained: `prospective-01`, `04`,
`07`, `10`, `13`, `16`, `19`, `22`, `25`, `28`. Each has four planned questions.
Sources, failed attempts, replaced questions and earlier reviews remain intact.
Experiments call OpenAI directly, using Astra `max`; two independent Astra
`high` source-based reviews precede the user's explicit report that two people
independently checked the current material. Humans could see AI suggestions;
this is AI-assisted verification, not a blind human study.

| Checkpoint | Saved | Valid | Invalid | Unresolved | Missing |
|---|---:|---:|---:|---:|---:|
| Original study | 28 | 14 | 14 | 0 | 12 |
| First rerun before the new repairs | 8 | not independently labelled | — | — | 32 |
| Repaired complete collection, first AI review | 40 | 38 | 0 | 2 | 0 |
| Current suite after two real product regenerations and human checks | 40 | 40 | 0 | 0 | 0 |

Question validity is separate from target-answer correctness. All 60 extracted
facts and source-coverage checks were accepted. Of 32 extracted relationships,
26 are confirmed correct; six uncertain or disputed overrides are excluded
from that confirmed count, while their original records remain preserved.
These previously observed, structurally related synthetic histories are
development evidence, not an independent population or model-only comparison.

## Retained evidence

- `initial-original-ten-rerun.zip`: all ten first attempts, eight saved questions,
  failed stages, and the frozen pre-repair application.
- `repaired-original-ten-full-rerun.zip`: the complete 40-question generation,
  raw responses, protocol and frozen repaired application.
- `first-independent-review.zip`: the first two reviews and 38-valid/two-uncertain
  reconciliation, preserved without relabelling them.
- `effective-cohort-reviews-and-human-confirmation.zip`: actual two-question
  regeneration records, current 40-question snapshots, independent completed AI
  reviews, separate source-bound human confirmation, and the human review pack.
- `presentation-provenance-20261101.json`: exact presentation input hashes and
  the unchanged original deck hash; its authoring source is alongside the deck.
- `execution-preflight-v1-preserved.zip`: the first ten registrations and
  pre-dispatch configuration-check stops, including their frozen helper sources.
- `complete-execution-and-validation.zip`: ten completed Astra max technical
  runs, 40 responses, 40 automatic assessments, per-run CSV/ZIP exports and the
  repaired read-only export confirming all saved rows. It also retains offline
  verification logs and the original optional-inspection error.

Technical execution completed 40/40 answers and assessments; automatic outcomes
are 9 pass, 12 fail and 19 uncertain. These are not independent human reference
labels, question-validity judgments or a new AC3 result. The source auxiliary-off
profile stays fixed, while the separate technical condition deliberately uses
an OpenAI structured writer, Astra reader/judge and relationship-packet retrieval.
The earlier optional database export failed to JSON-encode a trace model; the
original collection summary preserves that error. The separate read-only
reconciliation confirms 40 saved questions, 40 answers and 40 assessments without
changing the original summary or making additional model calls.

Archives preserve `output/proposal-delivery/...` paths. Extract them at the
repository root to resolve the detailed local evidence links in the reports.
Each evidence archive has an adjacent SHA-256 checksum. Retain the first-pass
and current-suite records separately; two revisions do not add two independent
samples to the 40 planned slots. Frozen protocols prevent automatic replays of
ambiguous paid requests. Never replace original records to improve a headline.
