# Synthetic illustrative case studies

These examples are fabricated teaching fixtures. They are not user data, human annotations, benchmark records, pilot findings, or formal results. Their purpose is to make the intended evidence trail concrete before data collection.

## Case A — Freshness: superseded database

Conversation sequence: “I used MySQL before.” followed by “The backend now uses PostgreSQL.”

Question: “Which database should the backend use now?”  
Expected behaviour: retrieve the later PostgreSQL record, retain an `UPDATE` link to the earlier MySQL record, and avoid answering with the stale value. Inspect stored lifecycle state, selected retrieval IDs, source message IDs, and evaluator ground-truth IDs.

## Case B — Appropriate Use: local requirement over preference

Conversation sequence: “I generally prefer Python.” followed by “For this ELEC5623 assignment, Java is required.”

Question: “Which language should be used for the current assignment?”  
Expected behaviour: use the current assignment requirement rather than the general preference. A scoped strategy should distinguish `preference` and `contextual_requirement`.

## Case C — Conflict Resolution: unresolved alternatives

Conversation sequence: “The deployment must use region A.” followed by “The client says region B is mandatory, with no stated precedence.”

Question: “Which deployment region should we use?”  
Expected behaviour: retain the conflict trace and request clarification rather than inventing precedence. A pass is not simply choosing the latest string.

## Case D — Accuracy: stable profile fact

Conversation sequence: “I am based in Sydney.”

Question: “Where is the user based?”  
Expected behaviour: retrieve the stable profile record and answer Sydney. This deliberately simple fixture must not be used to claim real-world performance.

For reusable local fixtures, convert only de-identified or synthetic cases to the JSON shapes accepted by the local compatibility endpoints. Keep actual participant or externally licensed source outside this repository.
