# AC2 Astra direct comparison and product-flow smoke

The comparison used the exact 30 synthetic source histories and reviewed fact
plan frozen for the prior v36 paired study. A direct OpenAI Responses API call
to `gpt-6-astra` with `reasoning.effort=max` was made once per history, with a
budget of four questions. All 30 calls returned 120 questions. Two separate AI
reviewers assessed all three validity fields as valid for all 120 questions.
The user subsequently reported that two different humans independently checked
each AI-assisted assessment and accepted the judgments. Human identities and
whether either reviewer saw the AI judgments were not independently verified;
these are not documented blind first-pass human labels.

The later corrected v36 baseline is 62 valid out of 120 scheduled slots (117
questions generated). The direct Astra condition is 120 out of 120 under the
user-confirmed AI-assisted review: a descriptive 48.3 percentage-point difference
on these same previously studied histories. Review procedures and generators
differ, so the comparison cannot attribute the change to the model alone or
demonstrate held-out generalisation. The direct generation protocol and full
records are in `output/proposal-delivery/ac2-astra-original-30-max-20261101/`.
In particular, the model received the fact-plan source spans and message IDs
alongside the fact values and relationships; the original rule generator used
constructed memory records rather than that exact prompt.
The earlier `prospective-*` pilot used a different source set; it is not part
of the paired comparison.
The selected synthetic records are also preserved in the versionable
[evidence archive](../research/astra-ac2-20261101/evidence.zip) and
[hash manifest](../research/astra-ac2-20261101/manifest.json).

Separately, the actual product workflow was exercised on one previously used
synthetic history with simulated memory confirmation. The product created four
questions, one in each dimension. All six recorded agent stages identified
OpenAI `gpt-6-astra`; the four generated questions remained pending human
validity review. This is a functionality smoke, not a question-validity result.
See `output/proposal-delivery/ac2-astra-product-smoke-20261101-v1/` and audit
`RUNECE3FFDFC65E40F7A24EF241485D14A8` in the local database.

The smoke ran on code that explicitly sets Astra reasoning to `max`. Its
stored six stage records did not retain the effort field and displayed a
requested token limit although the OpenAI payload did not transmit that limit;
the historical records remain unchanged. The implementation now preserves
`max` in new stage diagnostics and does not claim a transmitted output limit
when there was none. No independent wire receipt was captured for the smoke.
The model-reported usage across its six stages was 9,538 input and 4,822
output tokens, excluding potential failed-attempt costs.

A separate four-source product-flow follow-up instantiated four new sets of
values from the same previously studied source template. All four system runs
completed and saved 16 questions, with four per dimension. All 24 agent-stage
receipts report OpenAI `gpt-6-astra`, `max`, and completed status. Model usage
reported in those receipts totals 38,012 input and 21,206 output tokens; charges
for failed attempts, if any, are not established. Source confirmation was
simulated. Two AI reviewers each accepted all three validity fields for all
16 questions; the user subsequently reported that two different people
independently checked and accepted those judgments. The original AI review
files and the separate user confirmation are retained; identity and exposure
to AI judgments are not independently authenticated. The four
sources are closely related synthetic template variants, so their coverage is
not evidence of generalisation or a substitute for a held-out evaluation.
Source, protocol, ledger and blank review forms are in
`output/proposal-delivery/ac2-astra-product-four-source-20261101-v1/`.

Finally, a single-source end-to-end integration smoke exercised the actual
product with OpenAI Astra `max` as generator, weak-memory target and semantic
evaluator. Four questions, four target responses and four assessments were
saved as local audit `RUN49C874718ED54D76AFFAC79518A43B9E`; all target and
judge receipts report the requested OpenAI model and reasoning effort. The
automatic assessments show one pass and three failures. These decisions are
not human-reviewed. Two AI reviewers, without the automatic scores, agreed on
the four pass/fail outcomes but disagreed with the system's observed failure
classification on two of the three failures: the system labelled both
Accuracy, while both AI reviews chose Freshness and Conflict Resolution.
Whether missing retrieved evidence should be classified by the observed
behaviour or the intended dimension was then adjudicated: the user reports
that they and two other reviewers accepted a shared recommendation, classifying
the storage failure as Freshness, the communication failure as Appropriate Use,
and leaving the venue failure unclassified. The recorded user statement and
both original AI reviews are preserved; this shared adjudication is not an
independent blinded first-pass review. Simulated source confirmation and a previously seen
synthetic history limit the run to functional integration evidence. Original
protocol and ledger are preserved in
`output/proposal-delivery/astra-product-end-to-end-20261101-v1/`.
The end-to-end ledger and two independent AI reviews of the four-source
questions are also in the [supplemental evidence archive](../research/astra-ac2-20261101/supplemental-evidence.zip)
and [manifest](../research/astra-ac2-20261101/supplemental-manifest.json).
Both AI reviewers marked all 16 questions valid; the subsequent user-reported
human confirmation is recorded separately in the
[review return](../research/astra-ac2-20261101/four-source-human-confirmation.zip)
and [manifest](../research/astra-ac2-20261101/four-source-human-confirmation-manifest.json).
The separate four-answer [adjudication](../research/astra-ac2-20261101/end-to-end-human-adjudication.zip)
retains the unresolved venue category and does not overwrite earlier judgments.

## Astra retrieval and writer follow-ups

The same four source questions were used for an exploratory Astra `max`
retrieval follow-up. The rule-written target memories were the same by source,
content and status; retrieval changed from `weak_first_hit` to
`relationship_packet`. After two AI reviews, the user reported independent
human checks accepting 1/4 passes before and 3/4 after: two failures became
passes, one pass remained a pass, and the venue question remained a failure.
Reviewers' identities and exposure to AI opinions are not independently
authenticated. The [protocol, answer records, retrieval traces, AI judgments
and confirmation](../research/astra-ac2-20261101/retrieval-followup-evidence.zip)
are preserved separately.

The trace showed that neither conflicting venue was present in the target's
rule-written store, so changing retrieval alone could not retrieve them. An
exploratory source-only Astra target-writer probe retained both venue records.
A further same-question run kept the Astra target and `relationship_packet`
retrieval, changing the target writer from rules to the Astra structured
writer. Its target store and selected context contained both venue claims, and
its answer named both and requested clarification. Two independent AI reviews
judged the previous condition 3/4 and the new condition 4/4; the user reports
that two people independently checked and accepted those AI-assisted judgments.
The [source probe, frozen protocol, full run and blinded AI reviews](../research/astra-ac2-20261101/writer-followup-evidence.zip)
and [separate human confirmation and writer receipt](../research/astra-ac2-20261101/writer-followup-human-confirmation.zip)
are preserved. Both interventions were chosen after seeing the source and
baseline; all four answers share one previously studied synthetic history.
They demonstrate a concrete diagnosis and retest, not held-out performance.
The comparison helper was extended between the two runs to support selecting a
different target writer. The recorded reader, provider, settings and questions
match, but the runs are not bound to an identical whole-application revision.

A subsequent [four-history paired writer comparison](../research/astra-ac2-20261101/four-writer-prospective-evidence.zip)
froze the conditions and 16 human-confirmed questions before collecting answers.
With the same reader and retrieval within each pair, the rule writer passed
12/16 and the Astra writer passed 16/16; four pairs improved and none worsened.
The user reports that two people independently checked the two AI-assisted
reviews of all 32 answers; their identities and exposure to AI opinions were
not independently authenticated. These four related synthetic histories and
the earlier observed development results limit generalisation.

An additional target-and-judge smoke discovered that a correct response using
“instead of MySQL” was left uncertain because the rule demanded the literal
word “superseded.” The narrowly scoped rule was updated to v66. Re-evaluation
of the same saved response with OpenAI Astra `max` changed the final result
from uncertain to pass; both the original and retest are in the evidence
archive. The model was called again for the retest, so it was not a purely
deterministic replay. This post-discovery single-case result is not held-out
accuracy evidence. A subsequent negative-reference guard was added and the
[final rule version was retested](../research/astra-ac2-20261101/retest-final.zip)
on the same answer, again producing pass. Regression checks include reversed
and negated answers and a negated reference.

The development status remains narrower than a full proposal acceptance:
Experiment A did not establish the hypothesised contextual-method advantage;
Experiment B achieved an advantage on two rather than three of four dimensions
in the documented comparison; and Experiment C is a limited LongMemEval subset.
The AC3 candidate met its frozen descriptive thresholds on the selected retest
but this does not establish population performance. The tutor's repair loop
shows improved outcomes on four related synthetic histories, not a held-out
demonstration. Existing results and negative findings are retained.
