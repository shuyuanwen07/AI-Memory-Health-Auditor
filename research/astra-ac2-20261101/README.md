# Astra experimental evidence — 1 November 2026

Use [the experimental report](../../docs/EXPERIMENT_REPORT_2026-10-28.md)
and [requirement map](../../docs/PROPOSAL_STATUS_20261101.md) for interpretation.
These archives preserve separate studies. Do not pool their repeated or related
cases as independent observations.

The [updated presentation](Memory-Auditor-Presentation-20261101.pptx) contains
13 slides and Speaker 1–4 scripts in the slide notes. Its authoring source is
`update-presentation-20261101.mjs`; `presentation-provenance-20261101.json`
records data sources and validation. Original slides remain preserved.

| Question | Primary records | Status and scope |
|---|---|---|
| Does source-only extraction preserve facts? | `ac1-astra-four-source-evidence.zip` | Four related histories; human-checked AI reviews. 30/30 candidates supported, 32/32 reference records covered, 12/12 relationships correct. Compound record coverage is not atomic recall. |
| Can the complete product flow generate valid tests? | `ac2-astra-ten-source-product-evidence.zip` | Human-checked: 14 valid, 14 invalid and 12 ungenerated of 40 planned slots. Includes failures. |
| Does a conflict guard help? | `ac2-conflict-guard-development-replay.zip`, `ac2-conflict-guard-four-source-retest.zip`, `ac2-generation-repair-retest.zip` | Same-question development replay and subsequent failed product retests are distinct. Rejection is not proof of successful replacement generation. |
| Did the latest revised-source product generation complete? | `ac2-intent-timeout-product-retest.zip`, `ac2-intent-timeout-human-confirmation.zip` | 4/4 questions saved after planning-intent and timeout repairs. Two Astra high reviews, subsequently independently human-checked according to the user, accept all four. One previously studied development history; not a successful repeat of all ten histories. Some prompts disclose conflict. |
| How were the unsaved candidates treated? | `ac2-unsaved-candidate-human-adjudication.zip` | User-reported two-person acceptance: Accuracy/Conflict usable, Freshness needs revision, Appropriate Use uncertain. The product suite was never saved. |
| Did the writer repair improve target answers? | `four-writer-prospective-evidence.zip` | Four related histories, 16 paired questions; 12/16 → 16/16 pass, four improved and none worsened. Human-checked AI reviews, not population performance. |
| How did four policies compare with Astra? | `b-astra-four-strategy-run-evidence.zip`, `b-astra-four-strategy-ai-review.zip`, `astra-high-two-reviewers-evidence.zip`, `astra-high-human-confirmation-and-capacity-review.zip` | 52/64 answers saved; 48 complete paired answers. The user reports two independent people checked the later Astra high judgments. Paired passes: 3/12, 3/12, 0/12, 0/12. |
| Was the fourth B scenario counted correctly? | `b-fs04-count-correction.zip` | Correct AI-review count is First-match 0/4. An earlier verbal 3/4 was a reporting error, not an alternative result. |
| Can Astra run the external-data connector? | `longmemeval-astra-isolated-development-preflight.zip`, `c-astra-development-ai-review.zip`, `c-astra-development-human-confirmation.zip` | Two development cases, four calls; 0/4 human-checked passes. Full sources imported, but only 50 memories retained and one retrieved. Not an official score or validated ranking. |
| Which C result does the live Dashboard currently show? | `dashboard-latest-c-plan.json` | Latest saved Luna plan: two reused knowledge-update cases × three repeats; human-consensus passes 0/6, 3/6, 0/6, 1/6. The historical 30-case study remains separate. |
| Does increasing capacity help on those cases? | `longmemeval-astra-capacity500-development.zip`, `astra-high-human-confirmation-and-capacity-review.zip` | Only capacity changed from 50 to 500. Three of four new requests completed, all three failed the human-checked AI review; one has no answer. The seven old/new completed answers were checked together. No improvement shown by this small development comparison. |
| Are reports and exports traceable? | `ac4-ac5-readonly-check.zip` | A currently served saved failure was matched across report/detail/export. Two paired frozen suites matched; their writer differs intentionally. This is not an identical-configuration stability repeat. |
| Where is the direct 120-question comparison? | `evidence.zip`, `manifest.json` | Previously studied sources and different generator inputs/review procedures. The 120/120 result must not replace the negative product-flow evidence above. |

Other archives retain the one-history diagnosis, retrieval/writer follow-ups,
source-review confirmation, and evaluator wording repair. Their names and JSON
manifests identify which records they supplement; keep them separate from the
later four-history paired study.

Archives with `.sha256` sidecars can be checked with a SHA-256 utility. Earlier
archives use the corresponding `*-manifest.json`. Extract into a new directory,
preserve original contents, and use separate files for later adjudications.
Original AI declarations and user reports of human confirmation are both kept.
Reviewer identities and exposure to AI opinions are not independently verified.

The main scripts live in `scripts/`; archived protocols bind their source and
application hashes. Model calls require server-side credentials and can incur
cost. Existing journals intentionally stop rather than silently repeating an
ambiguous request. This folder does not contain credentials.
