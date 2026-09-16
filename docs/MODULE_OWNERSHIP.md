# Module ownership

| Module | Suggested owner | Boundary |
| --- | --- | --- |
| Conversation and ground truth | Developer 1 | API workflow, persistence, review UX |
| Extraction and test generation | Developer 2 | Implement interface-compatible pipeline providers |
| Target execution and evaluation | Developer 3 | Controlled connector/evaluator providers and evidence |
| Metrics, dashboard, experiments | Developer 4 | Scores, reports, benchmark comparison UI |

Shared changes to schemas, lifecycle transitions, and migrations should be reviewed by the team before merging.
