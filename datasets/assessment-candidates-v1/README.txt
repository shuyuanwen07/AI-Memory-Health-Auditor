Source-only candidate release, AI authored; no human gold labels or formal results.
20 varied source scenes cover five domains and four exercise dimensions. Ten are
pilot candidates; ten are candidate test scenes. Neither pool is certified novel.
The held-out subset contains only ten histories, below the documented practical
20-history formal guideline; extend it with independently authored scenes.

Individual JSON files can be imported through New audit -> Choose JSON file.
Reviewer A and B each complete their own blank copy independently, checking facts
and relationships. For Experiment A, first confirm the source memories, then use
the application to create the deterministic rule-generated fixed-template draft.
A researcher reviews every drafted question, edits or replaces weak items, adds
questions to meet the frozen budget and dimension minimums, and explicitly
confirms the final release before it is frozen. This is a rule-seeded,
researcher-reviewed baseline, not a from-scratch human-authored baseline. C
reconciles disagreements and certifies source/template independence before
experiment freeze.
Do not execute candidate test scenes to tune the system. If used for tuning, move
them to development and create a new untouched test release.

These files are source-review materials, NOT AnnotationDataset import contracts.
After human agreement, create the versioned annotation/pilot releases using
../annotation/v1/annotation_template.json and ../annotation/pilot-v1/
double_annotation_pilot_template.json. Blank lists are not validated gold.
No answer is inserted into target context. The manifest fingerprints source files,
not a complete frozen protocol or the runtime. docs/HUMAN_EVIDENCE_HANDOFF.txt
explains proposal A/B/C, which are distinct from reviewer roles A/B/C.
