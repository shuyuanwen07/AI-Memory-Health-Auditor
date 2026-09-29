# Annotation guide — owner-a-guide-1.1-english-handoff

This guide is frozen with the source snapshot. It extends the repository's [annotation protocol](../../docs/ANNOTATION_PROTOCOL.md) for these synthetic tasks. A later guideline change must receive a new version and identify affected items for re-review.

## Independent workflow

Use your own CSV. `label` is one allowed value, `source_message_ids` is a `|`-separated set of exact source IDs, and `note` records a short justification or ambiguity. Do not copy the AI reference or coordinate labels with the other annotator. Candidate and response IDs are neutral shuffled identifiers, not label hints. Source messages retain chronological order.

Stage 1 covers `memory_inclusion` and `relationship_type`. Seal that portion before opening stage 2 (`test_validity`). Seal stage 2 before opening stage 3 (`evaluator_verdict` and `failure_dimension`). Stage 2 expected behaviours are candidate rubrics to inspect, not accepted answers. Stage 3 response text is authored synthetic material, not a model's measured performance.

The independent CSV includes all stages for convenience; filter by `task` while working. A source custodian should distribute later-stage packets only after the earlier stage is sealed. Do not share other annotators' files or open `completed_labels.csv`, `decision_log.csv` or `annotation_dataset.json` during independent work.

## Decisions

| Task | Allowed labels | Rule |
| --- | --- | --- |
| Memory inclusion | `include`, `exclude` | Include only an explicit atomic fact or a faithful qualified report of a requirement. Exclude unsupported inference, scope expansion and unjustified certainty. |
| Relationship type | `none`, `UPDATE`, `CONFLICT`, `CONTEXTUAL_OVERRIDE` | Judge the specified ordered pair; do not silently reverse source and target. |
| Test validity | `accept`, `reject` | Accept only source-grounded tests with observable, supported expected behaviour and no answer leakage in the question. |
| Evaluator verdict | `pass`, `fail` | Judge whether the response satisfies the source-grounded test; do not score by exact wording alone. |
| Failure dimension | `none`, `accuracy`, `freshness`, `conflict_resolution`, `appropriate_use` | `none` is mandatory for pass. A failure gets the dimension describing the actual error. |

### Facts and evidence

- Preserve the subject, project, date, unit and scope. A requirement for one report cannot become a rule for every report.
- Preserve historical facts when later values replace them. The old value remains a source-backed memory, with an incoming update relationship; it should not be treated as current.
- A conflicting requirement remains a fact **about a document's claim**. It is not a confirmed operational choice.
- Neither a project's technology nor a task constraint establishes a personal preference or a change of preference.
- Copy exact message IDs supporting the candidate. For excluded inferences, cite the nearest relevant message(s) and explain the missing support. Source-set agreement for exclusions is diagnostic; semantic rationales also matter.
- Review the full conversation for missing atomic memories, not only the supplied candidates. Record omissions with the scenario ID and source IDs in your note or a separate signed addendum. The coordinator must add/review the new units before claiming full extraction coverage.

### Relationships

- `UPDATE`: the **new fact → old fact** for the same subject, supported by explicit replacement and chronology. The reverse ordered pair is `none`; an old value does not update a new value.
- `CONTEXTUAL_OVERRIDE`: **current narrow requirement → general preference**. The general preference still applies outside the named task. Do not label this as a global `UPDATE`.
- `CONFLICT`: incompatible claims with no supported precedence. This release stores both directed edges; both candidates should be checked. Mention order in a single message is not evidence that the last claim wins.
- `none`: independent facts, or an unsupported ordered relation. A shared project name alone does not make an update or conflict.

### Tests and answers

Reject answer-leaking questions even when the underlying fact is present. Reject tests about missing future plans, personal likes, different events, prices, hardware ratings, or global rules when the source only supports a narrower claim. Explain separately whether the issue is missing evidence or answer leakage.

For accuracy, accept semantic equivalence while preserving the specified identifier, value or unit. For freshness, a correct answer may mention the old value historically, but must identify the new value as current. For conflict resolution, the answer must acknowledge unresolved incompatible requirements and defer choosing until authority is clarified; simply selecting either side fails. For appropriate use, apply the explicit current task constraint; do not infer that the general preference was permanently removed.

All response examples here are attached to tests proposed as valid. If you reject one of those tests, flag its response labels for adjudication rather than treating an invalid question as a model failure. If a single allowed category cannot faithfully represent an ambiguity, leave the label pending and explain it; revise the affected unit before final freeze. Do not force a label merely to fill the spreadsheet.

## Disagreements and final sign-off

Preserve both independent CSVs with timestamps and checksums before comparing them. Populate `annotator_1_label` and `annotator_2_label` exactly in the adjudication sheet. Also compare `source_message_ids` as sets (order does not matter). For every item record `final_label`, `final_source_message_ids`, `basis` and a meaningful `decision_note`.

Use `basis: adjudicated` for a documented human resolution. On agreeing items, record that both labels agree and which evidence was checked. On disagreements, state the contested interpretation, controlling source IDs, applied guideline and final rationale. Use `external_reference` only when a separately approved reference actually exists; this AI proposal is not an approved human reference. Escalate unresolved questions to a third human when available, and leave the release pending if no defensible decision is reached.

The pending package declares at least five paired items per task, complete paired and final-label coverage, no unresolved disagreements, and Cohen's kappa ≥ 0.6 where defined, matching the repository's default. These are predeclared workflow criteria, not a statistical power calculation. Report each task separately; do not interpret pooled kappa across different tasks as a single reliability measure. When kappa is undefined, report it as undefined and show raw counts/agreement instead of inventing a score. Source-set agreement is an additional manual check outside the current service's categorical gate.

## Release-specific clarification

Use dataset version `2.0.0-ai-reviewed` with this handoff. A012 now specifies exactly 8 versus exactly 12 pages, rather than overlapping maximum-page limits. A017 preserves the concise qualifier. The filled CSVs are AI-assisted review results. The separate forms are blank for future genuinely independent human work; do not mistake those templates for the completed AI labels.
