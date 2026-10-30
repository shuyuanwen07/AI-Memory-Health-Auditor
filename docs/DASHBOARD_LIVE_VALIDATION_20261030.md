# Dashboard live verification — 30 October 2026

This exploratory verification exercises the saved dashboard flow. It does not replace the separately reviewed A/B/C studies or establish population-level performance. The history and benchmark cases were previously used and their earlier outcomes were known.

The comparison used one existing synthetic history, four questions, four retrieval strategies, three runs per strategy, and OpenRouter GPT-6 Luna. After runs with a 192-token output limit produced empty provider responses, the original records were preserved and a new group was frozen with a 1024-token limit. The latter completed 12/12 runs; automatic decided results were:

| Strategy | Passed / decided |
| --- | --- |
| First-match retrieval | 6/12 |
| Relationship-priority retrieval | 12/12 |
| Match the task and project | 6/12 |
| Consider time and importance | 12/12 |

The B results are automatic labels, not independent human judgments. Repeated answers share the same history and questions. The completed group is `EXPA4C337652EDB4014B2F1EA19F07C5333`.

For C, two previously used LongMemEval Oracle knowledge-update cases were selected before the new runs. The server-frozen plan `CP24c3f81bba294dcc86c7977e6716977b` executed all four strategies over three repeats. Automatic lexical matches, summed across repeats, were 0/6, 6/6, 6/6 and 6/6 in the strategy order above. Lexical match is a surface proxy, not human-reviewed accuracy; repeated cases are not independent. Original returned answers are retained locally for review. The complete benchmark and its general performance were not measured.

The initial 192-token collection retained 7 completed and 5 failed audit runs; all three C trials failed and remain recorded, not scored as incorrect. The team must still review the new answers. A new A method-comparison package was created from the same synthetic source, but its source inventory and fixed questions await human review; no new A outcomes are claimed.

The live Dashboard was checked after refresh: it selected the new B group and displayed all three C repeats while retaining the prior reviewed studies. C and B show automatic measurements separately from pending independent human review.

## Human-confirmed return

The user subsequently reported that two different people independently checked each AI-assisted judgment and approved the A inventory and fixed templates. The [user confirmation](../research/dashboard-validation-20261030/review-confirmation.json) and [source-bound reconciliation](../research/dashboard-validation-20261030/reconciliation.json) preserve that report and the original archive fingerprint. Reviewer identities were not authenticated, score exposure was not established, and C strategy names were visible. The two original AI judgments agreed on all 100 responses; neither the AI labels nor the earlier files were rewritten.

For the 1024-token B group, two-reviewer consensus pass counts, in the strategy order above, were **3/12, 9/12, 6/12 and 9/12**. The 192-token group had 12 passes and 16 failures across its 28 completed answers; five failed audit runs remain missing. For C, the consensus pass counts were **0/6, 3/6, 0/6 and 1/6**, respectively. These differ from the lexical proxy above, which is not a substitute for human review. Repetitions share one synthetic history or two benchmark cases and are not independent population samples.

After two separate itemwise human reviews of the eight newly generated questions were reported by the user, the three A methods completed one run each. Direct questions, fixed templates and contextual/indirect tests had 3/4, 4/4 and 3/4 answers automatically judged passed, respectively. These are automatic answer assessments, not measures of defects discovered. The [eight-question reconciliation](../research/dashboard-validation-20261030/a-eight-question-review.json) retains the returned archive fingerprint and both AI-assisted decisions. The questions include a duplicate prompt and explicit hints, which limit conclusions about question diversity and unprompted discovery.

The user later confirmed two independent human itemwise checks of the AI-assisted 12-answer judgments and the frozen mappings. The confirmed answers are 10 pass and 2 fail, with 0/3 candidate failure patterns matched for each method. The three patterns were predeclared potential failures; their presence in the evaluated responses was not established independently, so this 0/3 is not a general recall estimate. Both human-confirmed failures involve an unsupported claim that historical database information was missing; neither uses the old database as the current one, so neither matches the frozen STALE definition. These [out-of-inventory failures](../research/dashboard-validation-20261030/a-out-of-inventory-failures.json) are retained separately rather than changing the frozen inventory. The [confirmation](../research/dashboard-validation-20261030/a-12-user-confirmation.json) and [reconciliation](../research/dashboard-validation-20261030/a-12-answer-reconciliation.json) preserve provenance; score exposure and identity authentication remain unverified. This is one selected synthetic history with one run per method.
