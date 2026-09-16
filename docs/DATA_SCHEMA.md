# Data schema

The PostgreSQL schema is created from the Alembic migration chain in `backend/alembic/versions`.

| Table | Purpose |
| --- | --- |
| conversations, messages | Authorised source history and ordered message evidence |
| memories, memory_relationships | Reviewed facts and UPDATE, CONFLICT, or CONTEXTUAL_OVERRIDE links |
| audit_runs | Reproducible controlled run configuration, provider/model selection, and lifecycle state |
| experiments | Frozen comparison configuration, canonical test-suite source, and experiment lifecycle |
| test_cases | Generated tests with memory support, test type, grounding and quality decision |
| target_responses | Controlled target outputs |
| target_agent_memories, target_agent_memory_relationships | Private memory records independently written by each controlled target Agent |
| target_agent_memory_events, target_agent_retrievals | Append-only private write/update and retrieval evidence for a target run |
| evaluation_results | Pass/fail decisions, reasons, and evidence memory IDs |

All identifiers are stable string IDs and foreign keys preserve audit traceability. Public objects are represented by matching Pydantic models in `backend/app/schemas/domain.py` and TypeScript interfaces in `frontend/src/types/domain.ts`.

`audit_runs` records the controlled target configuration, provider/model, `memory_strategy`, `memory_maintenance_policy`, temperature, seed, budget and prompt-template version. It also records the resolved pipeline and evaluator provider/model so a stored experiment does not change if default environment settings are later changed.

Each private `target_agent_memories` record has one deterministic scope: `profile`, `preference`, `project_requirement`, or `episodic`. These labels are inferred from the authorised conversation during target-Agent ingestion and are independent of the reviewer-confirmed ground truth. They make future scope-aware retrieval experiments possible without changing the record format.

`memory_maintenance_policy` is a run-level controlled variable. `append_only` retains both sides of an UPDATE as active observations. `update_aware_consolidation` marks the previous record `SUPERSEDED` while preserving the relationship and write evidence. The private event ledger records the selected policy and its maintenance action for every UPDATE, so the two conditions remain experimentally traceable.

`test_cases.target_memory_context` is stored server-side only. It contains only the context retrieved from the controlled target's own per-run memory store; it is not reviewer-confirmed ground truth. Public test and result API responses omit it; the expected behaviour remains evaluator-only and is never sent to a target provider. `target_agent_*` tables remain private while an audit is running. Only after `COMPLETED`, the purpose-built target-memory-trace endpoint returns a redacted, read-only evidence view; it never returns evaluator expected behaviour or runtime context.

When an audit belongs to an experiment, its `experiment_id` links it to the comparison group. Canonical source tests have no `suite_test_id`; each cloned peer test stores `suite_test_id` pointing to its source test. This keeps all target responses and evaluations isolated by run while proving that every compared condition saw the same behavioural question.

Test review also acts on the canonical source: accepted/rejected decisions and regenerated content are copied to every peer test row. This preserves test-suite fairness even when a researcher rejects or replaces a generated question before execution.

Experiment history is calculated read-only from `experiments`, `audit_runs`, `test_cases`, `target_responses` and `evaluation_results`; no extra analytics table is needed. This prevents a stale report from becoming a second source of truth. Group exports likewise contain public score and failure evidence only.

## Offline research annotation data

Human annotations are intentionally not stored in the operational audit database. They are versioned, de-identified research artefacts under `datasets/annotation/`, with validation contracts in `backend/app/schemas/annotation.py`. This keeps participant source data separate from gold labels used to evaluate extraction, relationship classification, test quality and evaluator decisions. See [the annotation protocol](ANNOTATION_PROTOCOL.md) for permitted fields and the double-annotation procedure.

`backend/app/schemas/research.py` adds a request-scoped `ResearchPredictionSet` that joins a frozen annotation release to automated outputs. An extraction candidate is counted as a match only through its explicitly reviewed `matched_gold_memory_id`; relationship predictions are ordered source/type/target tuples; evaluator predictions are keyed by response ID. The research API validates and hashes these releases but does not add a database table, avoiding accidental mixing of research consent scopes and normal audit data.

`datasets/benchmarks/longmemeval-compatible-v1/` holds a synthetic format sample only. The adapter normalises local data to `LongMemEvalCase` and does not persist, download, or execute external benchmark records.
