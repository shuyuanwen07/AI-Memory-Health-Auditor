# B/C Astra repeated retest

**Status: two independent AI reviews complete; human confirmation pending.**

Both studies use OpenAI GPT-6 Astra with max reasoning,16questions perpolicy and3repetitions:48planned answers perpolicy. All384answers were collected. The original studies remain archived.

| Policy | B pass / planned | B unresolved | C pass / planned | C unresolved |
| --- | --- | --- | --- | --- |
| First-match | 9/48 | 0 | 8/48 | 12 |
| Relationship-priority | 33/48 | 3 | 28/48 | 13 |
| Task/project | 19/48 | 3 | 26/48 | 12 |
| Time/importance | 33/48 | 3 | 27/48 | 13 |

Pass/planned is conservative verified-success coverage. Unresolved references and disagreements are not model failures. Decided-only accuracy and per-repeat counts are in analysis.json.

## What changed

B fixes the shared reader configuration. Old advanced policies retrieved2–5records but delivered only1. Allnewconditions use one common full reader, which changes both delivery and reader instructions. The original rule writer remains fixed and omits the venue facts, limiting conflict-question completion.

C uses Astra rather than the earlier Luna run and a fixed stratified16-case Oracle sample. Sixteen cases and3repeats replace the old2-case display. The two oldanchors are retained separately in the analysis; model,budget andcohort differences prevent an isolated model-causation claim.

## Repetitions

| Study / policy | Repeat1 | Repeat2 | Repeat3 |
| --- | --- | --- | --- |
| B / First-match | 3/16 (0 unresolved) | 3/16 (0 unresolved) | 3/16 (0 unresolved) |
| B / Relationship-priority | 11/16 (1 unresolved) | 11/16 (1 unresolved) | 11/16 (1 unresolved) |
| B / Task/project | 7/16 (1 unresolved) | 7/16 (1 unresolved) | 5/16 (1 unresolved) |
| B / Time/importance | 11/16 (1 unresolved) | 11/16 (1 unresolved) | 11/16 (1 unresolved) |
| C / First-match | 3/16 (4 unresolved) | 3/16 (4 unresolved) | 2/16 (4 unresolved) |
| C / Relationship-priority | 10/16 (4 unresolved) | 9/16 (5 unresolved) | 9/16 (4 unresolved) |
| C / Task/project | 9/16 (4 unresolved) | 9/16 (4 unresolved) | 8/16 (4 unresolved) |
| C / Time/importance | 9/16 (4 unresolved) | 9/16 (4 unresolved) | 9/16 (5 unresolved) |

## Objectivity and limits

- Source versions, question text, model settings and sampling rules were frozen before calls; no outcome-dependent substitutions or paid request retries.
- C uses a pinned external LongMemEval Oracle release, a deterministic stratified selection and16distinct questions across7categories. Actual normalized source content was checked for duplication.
- Receipts bind the actual model,maxeffort,outputbudget and sentmemory. Repeated-condition input hashes match; provider sampling is not claimed deterministic.
- Two separate Astra max reviewers saw opaque source/answer handles without policy,model,repetition,automated scores or the other review. Source-validity judgments remain canonical; changes would remain disputed.
- 4 C question/reference pairs need human adjudication. They remain in the planned sample and their answers are unresolved,not automatically failed.
- B has four structurally related synthetic sourceclusters. C has16selected benchmarkcases. Repetitions are correlated measurements,not48independent histories. Source-cluster intervals and paired differences are descriptive.
- These are development and compatibility studies,not official full-benchmark scores or population-wide validation. Equaldenominators do not equalize datasetdifficulty.
- Human-verification declarations remain unset. AI judgments are not represented as human labels.

## Evidence

`output/proposal-delivery/bc-reader-retest-20261101-v2/` contains frozen protocols,raw journals,source snapshots,receiptcontrols,original reviewfiles,consensus andanalysis. The humanhandoff is `BC复测-待人工确认.zip`.
