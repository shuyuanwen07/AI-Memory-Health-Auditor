# Owner A Handoff: Synthetic Pilot Data and Annotation Materials

**Prepared:** 29 September 2026

**Dataset version:** `2.0.0-ai-reviewed`

**Delivery:** English documentation, sources, completed AI-assisted labels, review decisions, annotation instructions and reproducibility checks.

The source data and AI-assisted review are complete. Independent human double annotation and actual human disagreement adjudication remain pending. This handoff supports development and review; it does not claim formal-evaluation readiness or measured target-model performance.

## Start here

- [Development handoff for Owner B](../handoff/owner-a/README.md)
- [Annotation guide](../handoff/owner-a/ANNOTATION_GUIDE.md)
- [Review findings and decision process](../handoff/owner-a/REVIEW_NOTES.md)
- [Completed development labels](../handoff/owner-a/development/completed_labels.csv)
- [Development decision log](../handoff/owner-a/development/decision_log.csv)
- [Development annotation dataset](../handoff/owner-a/development/annotation_dataset.json)

The English custodian package is stored locally at `handoff/owner-a-custodian/`. It contains the held-out sources, labels, decisions, staged packets and instructions for C. It is excluded from GitHub so development access does not expose held-out answers. Its absence from a fresh clone is expected.

## Scope and inventory

| Material | Development: shared with B | Held out: retained for C | Full local release |
| --- | ---: | ---: | ---: |
| Synthetic scenarios | 12 | 8 | 20 |
| Scenarios per primary dimension | 3 | 2 | 5 |
| Source messages | 24 | 16 | 40 |
| Proposed memory facts | 27 | 18 | 45 |
| Directed memory relationships | 12 | 8 | 20 |
| Proposed accepted tests | 24 | 16 | 40 |
| Proposed rejected tests | 12 | 8 | 20 |
| Authored response examples | 48 | 32 | 80 |
| Completed AI label decisions | 195 | 130 | 325 |

The four dimensions are accuracy, freshness, conflict resolution and appropriate use. The full release includes five UPDATE links, five CONTEXTUAL_OVERRIDE links and ten directed CONFLICT links. Each proposed accepted test has one passing and one failing illustrative answer. These are synthetic AI-authored examples, not participant conversations or measured target-model outputs.

## Owner A responsibilities

| Responsibility | Delivered evidence | Status |
| --- | --- | --- |
| Prepare and freeze the pilot dataset | Versioned scenarios, stable IDs, sources, fixed split membership and checksums | Source and AI review complete |
| Check memory facts and relationships | Atomic claims, exact references, ordered links and review decisions | AI review complete; human confirmation pending |
| Supply labels | All 325 AI decisions filled with source text and reasons | Completed AI-assisted labels; not human labels |
| Record how annotation issues were resolved | Initial/final AI labels, evidence changes, source revisions and per-item notes | Actual AI findings recorded; human disagreements not measured |
| Hand off testing materials | Shared development package and separate local custodian package | Ready for engineering review with stated provenance |

The scheduled A phase was 23–25 September. This delivery records the actual preparation date, 29 September, rather than backdating the work.

## Review findings incorporated

1. **A012 conflict repaired.** Maximum lengths of 8 and 12 pages overlap. The revised synthetic source requires exactly 8 versus exactly 12 pages. Its memories, questions, illustrative answers and decision notes were updated together.
2. **A017 qualifier restored.** The canonical preference now preserves “concise” from the source preference for bullet-point summaries.
3. **Evidence narrowed.** Across the full local release, 100 evidence sets were refined to remove unrelated messages. Each distribution reports its own count in `review_summary.json`.

The original local snapshots remain unchanged. No categorical labels were changed to manufacture disagreement. The same assistant prepared and reviewed the reference with source access; these findings are not independent annotator disagreements.

## Owner B: next steps

1. Verify the development package and preserve its manifest and dataset version.
2. Use the 12 development scenarios to review the candidate suite and run engineering checks. Exclude tests labelled `reject` from execution while retaining them for test-validity analysis.
3. Follow the schedule's limit of one target model and a limited, predeclared set of strategies. B owns configuration selection, suite review, pilot execution, targeted improvements and regression checks.
4. Keep target prompts separate from evaluator-only expected behaviour and reference labels. Do not provide answer keys as target-model context.
5. Freeze code, configuration and the operational test suite before C receives held-out data. Preserve runs, failures and a summary of changes.

AI-reference engineering runs must be described as such. The existing human-annotation gate must not be bypassed to call them formal human-labelled evaluations.

## Human annotation required for the formal gate

Two actual annotators should independently use their own blank forms and staged packets without first viewing AI labels or each other's answers. Seal raw labels before comparing them. Compare exact source-message sets as well as categories, then document real resolutions in the adjudication form. Jointly reviewing an AI answer sheet does not establish prior independent double annotation.

Create a new human-reviewed dataset version after approved corrections. Update the matching pilot package's identity/version and actual pseudonyms, retaining raw and resolved labels. Validate through `POST /api/v1/research/annotations/validate` with `{"dataset": ...}` and analyse the real human package through `POST /api/v1/research/pilot/analyse` with `{"package": ...}`. Preserve fingerprints and per-task agreement reports.

## Owner C and custody

The custodian retains eight held-out scenarios until B's freeze, records recipients, and records whether any held-out content informed development. If it did, disclose exposure and arrange fresh data before claiming strict held-out validation. The partition is by scenario; both splits share task families and question patterns.

C evaluates the frozen system against appropriately qualified reference labels. This handoff supplies no final model metrics, human agreement results or formal-study outcomes.

## Verification

From the repository root:

```sh
python3 scripts/verify_owner_a_handoff.py
# With the backend Pydantic dependency available:
python3 scripts/verify_owner_a_handoff.py --schema
# Custodian's local checkout only:
python3 scripts/verify_owner_a_handoff.py --package handoff/owner-a-custodian --schema
```

Standard-library checks cover English text, file checksums, source evidence, label/decision consistency and the pending human-label state. `--schema` also calls the application's contracts and canonical fingerprint function. Each package includes a validation report with actual dependency versions. Checksums detect changes; they are not identity signatures.

Validation does not run a target model, call a hosted API or establish human agreement. The bundled verification environment uses Pydantic 2.13.5, while the backend pins 2.10.3; this is not a run of the complete locked backend test suite.

## Suggested progress statement

> Owner A prepared a versioned synthetic pilot release with 20 scenarios and completed AI-assisted labels and decision records for all 325 annotation units. The development package contains 12 scenarios, while eight held-out scenarios remain with the custodian until the system freeze. Source evidence, review corrections, annotation instructions and reproducibility checks are included. Independent human double annotation remains pending; no human agreement or target-model performance result is claimed.
