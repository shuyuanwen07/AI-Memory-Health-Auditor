# Exploratory retrieval retest — 30 October 2026

The Auditor identified missing retrieved context in a first-match baseline. A
new `relationship_packet` policy retrieves target-owned records and their
available relations and presents them as one source-labelled packet to the same
weak reader. No researcher ground truth is injected into target context.

The four synthetic histories, three test-construction methods, 48 source
questions, provider/model, reader configuration, target profile, capacity and
other recorded settings were held fixed. Candidate answers are fresh model
calls. The model's provider controls sampling; an identical seed is not proof
of deterministic output. The source outcomes were observed before the candidate
was designed, so this is an exploratory same-data retest, not a held-out study.

| Method | Before | After | Improved | Worsened |
| --- | ---: | ---: | ---: | ---: |
| Direct questions | 5/16 | 14/16 | 9 | 0 |
| Fixed templates | 5/16 | 15/16 | 10 | 0 |
| Contextual/indirect | 5/16 | 14/16 | 9 | 0 |

In total 28 of 48 matched answers changed from fail to pass; none changed from
pass to fail. Each side has one user-confirmed human reference after two
independent AI blind reviews, not two independent human reviews. The fixed
sample contains four related synthetic histories: answers from one history and
the three methods are not independent population samples.

Five candidate answers remained failures: two selected one side of a garden
allocation conflict; three did not provide the community venue information
needed by the question. The target's own writer had already omitted some source
facts; retrieval cannot restore records that were not retained. Some candidate
questions received no records at all. This intervention demonstrates an
improvement for this selected test, not universal model or Auditor accuracy.

Provider-reported target costs were approximately $0.004863 for the baseline
and $0.009425 for the candidate across 48 calls each; they exclude other stages
and are not a verified invoice. The candidate presents more source material,
which is part of the retrieval/context intervention. Its outer packet is one
reader record but may contain several actual memory IDs; inspect receipts.

The original questions, responses, reference judgments, blinded AI reviews,
confirmation, experiment receipts and SHA-256 manifest are retained in
`research/retrieval-retest-20261030/`. The Dashboard uses a separate paired
summary, preserving earlier A, B and C results.
