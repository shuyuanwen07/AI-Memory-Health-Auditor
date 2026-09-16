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
| evaluation_human_reviews | Pseudonymous human calibration labels kept separate from immutable automated verdicts |

All identifiers are stable string IDs and foreign keys preserve audit traceability. Public objects are represented by matching Pydantic models in `backend/app/schemas/domain.py` and TypeScript interfaces in `frontend/src/types/domain.ts`.

`audit_runs` records the controlled target configuration, provider/model, `memory_strategy`, `memory_maintenance_policy`, temperature, seed, budget and prompt-template version. It also records the resolved pipeline and evaluator provider/model so a stored experiment does not change if default environment settings are later changed. The target Agent's `target_memory_writer` (`rule_based` or `llm_structured`), `target_system_adapter` and their resolved versions are likewise frozen on the run. `TARGET_MEMORY_WRITER` is consulted only to choose the default while creating a new run; execution always uses the persisted run fields. Pre-0011 rows are safely interpreted as the deterministic `rule_based` writer and `controlled-memory` adapter.

Each private `target_agent_memories` record has one deterministic scope: `profile`, `preference`, `project_requirement`, or `episodic`. These labels are inferred from the authorised conversation during target-Agent ingestion and are independent of the reviewer-confirmed ground truth. The `scope_aware` retrieval strategy is a separate controlled condition: it prefers `project_requirement` for current task prompts and only prioritises `profile` or `preference` when the prompt asks for that kind of fact. Its retrieval evidence records the inferred intent and applied scope weight.

`temporal_importance` is a separate deterministic retrieval condition. For each private record, its cited source-message position is normalised against the authorised conversation length to produce `relative_chronology` and a bounded `recency_factor`; it does **not** inspect the current time or absolute transcript timestamps. A custom writer without valid cited source IDs falls back to its deterministic write order and records that basis. Its `importance_factor` is the explicit sum of scope and UPDATE/CONTEXTUAL_OVERRIDE/CONFLICT components. Retrieval evidence persists all factors and the final `temporal_importance_score`, so a paper result can distinguish a recency effect from an importance effect.

`memory_maintenance_policy` is a run-level controlled variable. `append_only` retains both sides of an UPDATE as active observations. `update_aware_consolidation` marks the previous record `SUPERSEDED` while preserving the relationship and write evidence; it merges exact normalised duplicates and only conservative near duplicates with the same content-token signature, no change/negation cue, and no lifecycle relationship. All merged source-message IDs and the merge rationale are retained in the private event ledger.

`target_memory_capacity` is a frozen positive per-run retention limit (default `50`). When pressure occurs, the private store retains project requirements, contextual overrides and unresolved conflicts before older episodic records. An evicted record remains in the trace with lifecycle state `EVICTED` and a `capacity_evicted_record` event, but is excluded from every retrieval strategy. The limit is deliberately soft if the unresolved conflict pair alone exceeds it: both sides remain and `capacity_soft_limit_preserved_conflict` records why the configured limit was exceeded. This prevents a capacity policy from silently turning a conflict-resolution case into a false certainty.

`evaluation_human_reviews` is optional calibration evidence for a completed audit. It permits multiple pseudonymous `independent` labels for one automated evaluation, plus at most one `reference` and one `adjudication` resolution in the operational API. An adjudication stores the independent review IDs it considered. Only the explicit adjudication (or reference when no adjudication exists) calibrates the automated evaluator; independent votes instead measure inter-rater reliability. No human label alters `evaluation_results`, so reported Target AI results remain reproducible while evaluator quality can be measured separately.

`test_cases.target_memory_context` is stored server-side only. It contains only the context retrieved from the controlled target's own per-run memory store; it is not reviewer-confirmed ground truth. Public test and result API responses omit it; the expected behaviour remains evaluator-only and is never sent to a target provider. `target_agent_*` tables remain private while an audit is running. Only after `COMPLETED`, the purpose-built target-memory-trace endpoint returns a redacted, read-only evidence view; it never returns evaluator expected behaviour or runtime context.

When an audit belongs to an experiment, its `experiment_id` links it to the comparison group. Canonical source tests have no `suite_test_id`; each cloned peer test stores `suite_test_id` pointing to its source test. This keeps all target responses and evaluations isolated by run while proving that every compared condition saw the same behavioural question.

Test review also acts on the canonical source: accepted/rejected decisions and regenerated content are copied to every peer test row. This preserves test-suite fairness even when a researcher rejects or replaces a generated question before execution.

Experiment history is calculated read-only from `experiments`, `audit_runs`, `test_cases`, `target_responses` and `evaluation_results`; no extra analytics table is needed. This prevents a stale report from becoming a second source of truth. The JSON reproducibility bundle contains public score and failure evidence only; the separately requested post-completion artifact ZIP additionally contains the already-redacted target-memory retrieval trace.

## Offline research annotation data

Human annotations are intentionally not stored in the operational audit database. They are versioned, de-identified research artefacts under `datasets/annotation/`, with validation contracts in `backend/app/schemas/annotation.py`. This keeps participant source data separate from gold labels used to evaluate extraction, relationship classification, test quality and evaluator decisions. See [the annotation protocol](ANNOTATION_PROTOCOL.md) for permitted fields and the double-annotation procedure.

## Local data lifecycle

Operational conversation data can be exported as a portable JSON bundle before it is erased. A conversation-level deletion removes its source messages and every operational artefact derived from it in one transaction, including private target-agent memory rows. Research annotation and locally supplied benchmark payloads are request-scoped/version-controlled separately and are not part of this operational deletion path.

`backend/app/schemas/research.py` adds a request-scoped `ResearchPredictionSet` that joins a frozen annotation release to automated outputs. An extraction candidate is counted as a match only through its explicitly reviewed `matched_gold_memory_id`; relationship predictions are ordered source/type/target tuples; evaluator predictions are keyed by response ID. The research API validates and hashes these releases but does not add a database table, avoiding accidental mixing of research consent scopes and normal audit data.

`datasets/benchmarks/longmemeval-compatible-v1/` holds a synthetic format sample only. The adapter normalises local data to `LongMemEvalCase` and does not persist, download, or execute external benchmark records.
