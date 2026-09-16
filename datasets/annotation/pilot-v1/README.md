# Double-annotation pilot template

`double_annotation_pilot_template.json` is deliberately a blank, de-identified structure. It contains no human labels, conversation text, target responses, or personal data, so it is **not** a completed pilot and will correctly return `ready_for_formal_evaluation: false` until filled.

For every declared item, two independent annotators add one label using only the allowed values below. Preserve both label sets even when they disagree. After the independent phase, add one adjudication or approved external-reference label and a concise decision note.

| Task | Allowed labels |
| --- | --- |
| `memory_inclusion` | `include`, `exclude` |
| `relationship_type` | `none`, `UPDATE`, `CONFLICT`, `CONTEXTUAL_OVERRIDE` |
| `test_validity` | `accept`, `reject` |
| `evaluator_verdict` | `pass`, `fail` |
| `failure_dimension` | `none`, `accuracy`, `freshness`, `conflict_resolution`, `appropriate_use` |

Submit a completed, approved package to `POST /api/v1/research/pilot/analyse`. The endpoint is request-scoped: it returns a fingerprint, coverage, raw pre-adjudication disagreement counts, Cohen's kappa where mathematically applicable, and readiness blockers. It does not write any package field to PostgreSQL.

Keep identifiable sources and the mapping from pilot IDs to source material in approved research storage outside this repository. Do not use placeholder IDs as evidence that real people have annotated a dataset.
