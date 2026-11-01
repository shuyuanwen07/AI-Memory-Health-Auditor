# AC2: complete retest of the original ten scenarios

Status: the effective 40-question cohort has completed two independent Astra
high AI reviews, followed by user-confirmed independent checks by two people.
They accepted all 40 questions, the 60 facts and source checks, and conservative
handling of six uncertain links. Human review was AI-assisted, with the AI
opinions visible; it is not a blind human study. The subsequent target
execution/evaluation smoke completed all ten histories: 40 returned answers
and 40 automatic assessments, with direct OpenAI Astra max receipts verified.

## Scope and comparison

The exact original ten histories are `prospective-01`, `04`, `07`, `10`, `13`,
`16`, `19`, `22`, `25`, and `28`. Their source messages are not rewritten.
Each history has four planned questions, one for each ability: 40 planned slots.
The separate four-history guard study (`02`, `05`, `08`, `11`) and the revised
workout pilot (`05`, four questions) are not substitutes for this cohort.

The original, human-checked study remains 14 valid, 14 invalid and 12 not
generated out of 40 planned slots. The first complete rerun on the subsequently
released code attempted all ten sources and saved 8 questions across two
histories; the other 32 slots were not generated. Those eight questions have no
new independent validity result and must not be described as eight valid
questions. Its raw calls, failed stages and frozen implementation are retained
in `research/astra-ac2-ten-completion-20261101/initial-original-ten-rerun.zip`.

## Diagnosis and implementation

The strict planner previously counted only questions that the deterministic
seed writer could already word successfully. This blocked model generation on
some source-supported topics. The repair adds metadata-only evidence slots,
without question text or expected answers, alongside existing valid seeds.
The model must still write actual questions. Initial full-suite generation
retains the original grounding, quality, semantic and duplicate checks. The two
later single-question revisions use the product regeneration path, with local
checks and the separate source-based AI and human reviews; this path does not
rerun the full-suite pairwise semantic critic. Missing
relationships are not invented and all four abilities remain required.

A separate relationship-stage guard applied observation-time ordering to a
scoped override. The scoped statement can legitimately be observed before a
general preference; its direction describes scope rather than recency.
Only CONTEXTUAL_OVERRIDE is exempted from this ordering guard. UPDATE and
CONFLICT ordering, endpoint citations, topic checks and atomic validation stay
in place. Failures now identify the affected edge and type.

Versions: generator `agent-coverage-semantic-v25`; strict planner
`coverage-planner-agent-v4`; partial planner remains `coverage-planner-agent-v3`;
relationship analysis `relationship-analysis-agent-v8`. The quality validator
and semantic critic are unchanged. Compilation, ruff and 243 related isolated
checks passed before collecting the repaired cohort. These offline checks
made no external provider calls.

## Collection and review protocol

Extraction, relationship analysis, source review, planning, generation and
semantic question review use OpenAI directly with `gpt-6-astra`, reasoning
`max`. The same original source selection and four-slot allocation are used.
A fresh copy of each source runs through extraction and generation. The run
freezes all application files and archives their exact bytes before dispatch.
Every attempted scenario and failed or ambiguous request remains recorded.

Operator confirmation before generation is simulated for this synthetic
research collection. It is not represented as a pre-run human annotation.
Two separate Astra high agents independently inspected sources, extracted
facts, links and actual generated questions without automatic quality verdicts
or each other's judgments. The first question review and a later review of the
effective suite are preserved separately. The user has explicitly confirmed
that two people independently checked and accepted this effective cohort and
the conservative treatment of its uncertain links. This confirmation concerns
the current batch and is retained separately from the original AI files.
The human checks followed the AI reviews and do not establish blind human
annotation. Uncertain relations remain uncertain rather than being silently
relabelled valid.

## Results so far

| Collection | Saved questions | Valid | Invalid | Unresolved | Not generated | Review basis |
|---|---:|---:|---:|---:|---:|---|
| Original ten-history study | 28 | 14 | 14 | 0 | 12 | Earlier human-checked AI-assisted review |
| First rerun on the subsequently released code | 8 | — | — | — | 32 | No independent question-validity conclusion for these eight |
| Repaired full-cohort generation, before question feedback | 40 | 38 | 0 | 2 | 0 | Initial independent Astra high AI opinions, preserved unchanged |
| Effective cohort after two question revisions | 40 | 40 | 0 | 0 | 0 | Two new independent Astra high AI reviews, subsequently independently checked and accepted by two people according to the user |

Every row has the same 40 planned slots, with four slots per original history.
The repaired generation produced all 40 questions, but its first independent
review did **not** accept every question: two were uncertain. The original
questions and their judgments remain preserved. Exactly those two questions
were subsequently revised through the real product review and regeneration
APIs using the same OpenAI Astra max pipeline, then included in the effective
cohort for another independent review. This is post-feedback development;
the final 40 valid AI judgments are not a first-pass automatic 40/40 result.

The reading scenario (`prospective-10`) needed its Freshness prompt to ask
explicitly for the earlier format and recorded update, alongside handling the
unresolved same-period conflict. The project-planning scenario
(`prospective-13`) needed its Appropriate Use reference to apply daily planning
only during the launch week without claiming that a daily activity changes or
overrides the length of a standard planning cycle. Both revisions changed
questions or references; none changed the original source messages.

For the effective cohort, both high reviewers agree that all 40 questions are
valid on four separately recorded criteria: source grounding, executability,
reference-answer validity and dimension alignment. They also agree on 60 valid
extracted facts and ten valid source-coverage checks. The user subsequently
confirmed independent human checks and acceptance of these AI-assisted
judgments. Source-coverage checks are record-level reviewer judgments, not an
independent atomic-recall estimate or a population performance measure.

Relationship validity remains separate: of 32 extracted links, 26 are agreed
valid and six remain uncertain. The unresolved links are CONTEXTUAL_OVERRIDE
claims in `prospective-01`, `04`, `16` and three links in `13`. Compatible
scoped instructions, different participants, and planning activities versus
cycle duration do not necessarily establish an override. The final questions
are assessed against the source text; their validity does not certify every
graph link. The user accepted conservative handling of these six links; no
unresolved relation is relabelled valid by the question result.

The source-bound records at this checkpoint are:

- [First independent review reconciliation](../output/proposal-delivery/ac2-original-ten-repaired-review-analysis-20261101-v1/summary.json), retaining 38 valid and two uncertain questions.
- [Actual two-question revision ledger](../output/proposal-delivery/ac2-original-ten-question-revisions-20261101-v1/), preserving original questions, feedback and API receipts.
- [Effective cohort](../output/proposal-delivery/ac2-original-ten-effective-cohort-20261101-v1/summary.json), retaining 40 current slots with two revised questions.
- [Final independent AI review reconciliation](../output/proposal-delivery/ac2-original-ten-effective-review-analysis-20261101-v1/summary.json), bound to both completed reviewer files and the effective cohort.

These `output/` links refer to the local research workspace. The original
full-run archive, first-review archive, effective cohort and separate human
confirmation are retained under
`research/astra-ac2-ten-completion-20261101/` without merging the checkpoints.

All planned slots remain in the denominator. Generated question validity,
source support, missing outputs and target-answer correctness are separate
measures. The [technical execution ledger](../output/proposal-delivery/ac2-original-ten-execution-smoke-20261101-v2/collection-summary.json)
retains 40/40 returned answers and 40/40 automatic assessments. All ten writers,
40 target responses and 40 judges have verified direct OpenAI Astra max
receipts. All ten CSV exports and ten artifact ZIP exports returned HTTP 200.
The target condition retains the source's fixed auxiliary-off control profile,
but deliberately uses an OpenAI structured writer, Astra reader and judge, and
relationship-packet retrieval for this separate availability check. It is not
a repeat of the original target condition or a new strategy comparison.

| Ability | Automatic pass | Automatic fail | Automatic uncertain | Planned |
|---|---:|---:|---:|---:|
| Accuracy | 5 | 5 | 0 | 10 |
| Freshness | 0 | 3 | 7 | 10 |
| Conflict Resolution | 0 | 4 | 6 | 10 |
| Appropriate Use | 4 | 0 | 6 | 10 |
| Total | 9 | 12 | 19 | 40 |

These target-answer labels have not undergone the independent human reference
labelling used for AC3. Uncertain assessments remain in the table; completing
40 assessments does not mean 40 successful target answers or establish judge
accuracy. This technical check does not replace source-based question review
or establish a new AC3 result.

An earlier execution preflight stopped before any execute/evaluate POST:
the comparison constructor had converted the source profile's null output
limit to 2048. Its ten registrations and zero-dispatch journals remain intact
in `execution-preflight-v1-preserved.zip`. V2 restored the exact approved
profile on new copies before execution, with strict round-trip checks and
separate protocol, role and run IDs. No prior model operation was replayed.
The optional database snapshot initially failed to JSON-encode its trace
model; this inspection failure is retained separately from the successful
answers, assessments and API exports. A separate guarded, read-only export
corrected that serialization and confirmed all 40 saved questions, 40 responses
and 40 assessments in the database. The original collection summary is not
rewritten: its unavailable optional-snapshot fields describe that failed
inspection, not missing answers. See the [saved-results reconciliation](../output/proposal-delivery/ac2-original-ten-execution-smoke-20261101-v2/saved-results-reconciliation-summary.json).

This is a post-discovery development regression on previously observed,
related synthetic histories, not a held-out population evaluation. Several
implementation changes and provider-controlled sampling prevent attributing
all observed differences to one factor or to a model change. The current
human-checked AI reviews support the repaired questions on these exercised cases,
not universal question-generation reliability.
