# Owner A: English Development Handoff

**Recipient:** Owner B

**Dataset:** `owner-a-synthetic-pilot-development` / `2.0.0-ai-reviewed`

**Status:** source and AI-assisted annotation complete; independent human annotation pending.

This package contains 12 synthetic development scenarios covering all four Memory Health dimensions, with 195 completed AI labels and 195 review decisions. Each decision includes source evidence and a reason. Eight held-out scenarios and their answers remain in a separate local custodian package and are not published here.

## File guide

| File | Purpose |
| --- | --- |
| [Annotation dataset](development/annotation_dataset.json) | Schema-compatible memories, relationships, tests and illustrative response labels |
| [Source conversations](development/source_conversations.json) | Source messages and stable IDs |
| [Completed labels](development/completed_labels.csv) | Filled labels, source IDs, original evidence text and reasons |
| [Decision log](development/decision_log.csv) | Initial/final AI labels, evidence refinements and final decisions |
| [Stage 1](development/blind/stage_1.md) | Memory and ordered-relationship material |
| [Stage 2](development/blind/stage_2.md) | Candidate test-quality material |
| [Stage 3](development/blind/stage_3.md) | Illustrative response material |
| [Annotation guide](ANNOTATION_GUIDE.md) | Categories, evidence rules and independent-review procedure |
| [Review notes](REVIEW_NOTES.md) | Actual findings and provenance limits |
| [Source revision log](source_revision_log.json) | Corrections with before/after records |
| [Review summary](review_summary.json) | Distribution-specific counts and method |
| [Verification record](validation_report.json) | Executed checks |
| [Manifest](freeze_manifest.json) | File checksums and canonical dataset fingerprint |

`development/forms/` contains two blank human worksheets, an adjudication worksheet and a pending pilot package with matching v2 identity. These support future independent human work; the completed AI work is already in `completed_labels.csv` and `decision_log.csv`.

## First actions

1. From the repository root, run `python3 scripts/verify_owner_a_handoff.py`; add `--schema` when backend Pydantic is available.
2. Read the [complete handoff report](../../docs/OWNER_A_HANDOFF.md), including human-annotation requirements and B/C responsibilities.
3. Review and freeze the operational suite under B's phase. The 24 accepted and 12 rejected tests are candidates. Rejected tests are annotation examples, not execution questions.
4. Preserve this release and place future changes in a new version. Do not combine v1 sources with v2 decisions.

All sources and response examples are synthetic and AI-authored. The same assistant prepared and reviewed the labels with source access. `human_confirmed` is false and formal-evaluation readiness remains false. This is not independent human annotation, Cohen's kappa evidence, a participant study or measured model performance.

The dataset remains version `2.0.0-ai-reviewed`: English packaging does not change data or labels. This distribution has its own manifest because documentation and human-work templates differ from the earlier local snapshot.
