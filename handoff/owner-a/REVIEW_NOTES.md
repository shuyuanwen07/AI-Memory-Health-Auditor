# Annotation Review and Resolution Notes

**Method:** source-visible AI review by the same assistant that prepared the original reference.

**Completed development decisions:** 195.

**Independent human disagreements:** not measured.

## Recorded findings

| Finding | Resolution | Evidence |
| --- | --- | --- |
| A012's maximum lengths of 8 and 12 pages overlap | Replace with exactly 8 versus exactly 12 pages; update dependent memories, questions and responses | Before/after records in `source_revision_log.json`; per-item notes identify the repaired v2 source |
| A017's canonical preference omitted “concise” | Restore the qualifier without changing inclusion or scope | Original and revised canonical values in the revision log |
| Some labels cited unrelated messages | Narrow citations to messages supporting the specific judgement | Initial/final IDs in `development/decision_log.csv`; original text in `completed_labels.csv` |

The full local review refined 100 evidence sets across both splits. This package's development-only count appears in `review_summary.json`. All 325 categorical labels across the full release retained their classifications after source corrections. This is not an agreement statistic: the review was neither independent nor blinded, and one source scenario changed.

## Decision rules applied

- Include explicit, scoped claims; exclude unstated preferences, universal rules and unwarranted certainty.
- Keep historical memories, with UPDATE directed from the new fact to the old fact.
- Apply CONTEXTUAL_OVERRIDE from the current task constraint to the general preference; retain that preference outside the task.
- Keep both unresolved document claims and require clarification before selecting an authoritative requirement.
- Reject answer-leaking or unsupported tests under the pilot's declared quality criteria.
- Judge responses semantically against source evidence; passing examples have failure dimension `none`.

Every completed row records its decision and evidence. These records describe work that actually occurred; they do not invent a human discussion or a second annotator.

## Future human disagreement records

Use the blank forms only for actual independent human work. Preserve raw sheets, then record disputed interpretations, source IDs, controlling guidelines and final decisions. Report human agreement and disagreement only after those observations exist. A human-reviewed release must receive a new version and its own frozen evidence.
