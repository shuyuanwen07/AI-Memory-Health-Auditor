# Development feedback from returned A/C worksheets

The returned A and C worksheets bind to the same frozen material (six histories,
32 audit responses and 21 benchmark pilot responses). The original exports carry
AI-assisted declarations. On 11 October 2026, the coordinator explicitly confirmed
that both attached returns were completed by real people. This newer confirmation
is recorded separately; original files and provenance are preserved without edits.
Each return has all 283 worksheet fields filled, with nine categorical differences.
Whether the reviewers independently re-judged the source without consulting one
another or automated scores remains awaiting confirmation. Human completion alone
does not establish blind independence or a final adjudicated reliability release.
Reviewer B is still pending. No operational gold labels were written.
On 12 October 2026, after seeing the source summaries and both reviewers' choices,
the coordinator selected C for all nine disputed fields. The separate adjudication
receipt preserves original labels, file hashes and the selected source notes.
There are no unresolved categorical disagreements in this decision record; the
NAS answer remains uncertain because that is C's selected judgement. This is
coordinator adjudication with AI-assisted summaries, not a third blind review.

`scripts/analyse_independent_reviews.py` checks the frozen source payload,
worksheet schema, field types, reviewer identifiers and missing entries. It
preserves provenance and disagreements; it never promotes matching AI drafts
into independent human validation. Returned source payload changes are rejected
regardless of the supplied fingerprint.

The review identified three bounded improvements:

- UPDATE probes now describe explicit replacement without inventing two
  separately dated records or describing resolved supersession as unresolved
  conflict. Expected behavior includes the historical value and asks for a
  source-grounded explanation. Generator revision: `rule-based-v16`.
- Rule evaluation checks old-database noun phrases such as "older PostgreSQL
  implementation" against explicit past evidence, retaining project isolation.
  An unrecorded assertion about a new/updated memory policy requires review;
  ordinary grounded recency explanations and qualified uncertainty remain
  allowed. Evaluator revision: `rule-based-v35`.
- Semantic evaluation explicitly checks explanations and reference assumptions,
  distinguishes source attributes, and applies known context to advice questions.
  Its rubric revision is `llm-judge-<provider>-v5`. This prompt change has contract
  coverage but does not establish improved semantic judgment performance.

Offline reevaluation uses the exact saved questions, reference memories and
answers for all 32 ordinary items. No target calls, semantic judge calls,
training or database label writes are performed. Before: 24 pass, 4 fail,
4 uncertain. After: 23 pass, 5 fail, 4 uncertain. A previously uncertain false
historical explanation becomes a failure; an unrecorded memory-policy assertion
previously passed becomes uncertain. These are development observations, not
held-out accuracy metrics or evidence of improved target-model performance.

There are nine disagreeing categorical fields across A/C, including two answer
correctness fields, three failure dimensions, three benchmark reference-support
fields and the dimension accompanying one correctness disagreement. Preserve
the original pre-adjudication values for agreement statistics. The coordinator's
selection of C resolves these disputes; it is not a majority-vote gold release.
Benchmark source ambiguity must not silently rewrite official references.

When B arrives, validate the same release, compare all three drafts and confirm
independent source verification. Resolve ambiguous cases using original
sources, freeze a revised evaluator, then evaluate new held-out responses.
