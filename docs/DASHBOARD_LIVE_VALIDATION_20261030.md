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
