# API

The interactive OpenAPI contract is available at `/docs` when the backend is running. All JSON endpoints are versioned beneath `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Service and database readiness |
| GET | `/target-providers` | Selectable target providers and backend configuration status; never returns secrets |
| POST | `/conversations` | Store authorised pasted or structured conversation data |
| GET | `/conversations/{id}` | Retrieve conversation and messages |
| GET | `/conversations/{id}/export` | Download authorised conversation, reviewed ground truth, and locally derived audit records as portable JSON; API keys and raw provider payloads are excluded |
| DELETE | `/conversations/{id}` | Permanently delete the authorised conversation and all locally derived audit records; request body must echo the exact conversation ID in `confirmation` |
| POST | `/conversations/{id}/extract` | Extract candidate memories |
| GET | `/conversations/{id}/memories` | List reviewed candidates |
| POST | `/memories` | Add a missing memory |
| PATCH | `/memories/{id}` | Accept, edit, reject, or amend relationships |
| DELETE | `/memories/{id}` | Mark a memory rejected |
| POST | `/conversations/{id}/confirm-ground-truth` | Confirm reviewed ground truth |
| POST | `/experiments` | Create an Experiment Group with one frozen shared-test-suite configuration |
| POST | `/experiments/{id}/cancel` | Cancel every unfinished condition in an Experiment Group; completed conditions remain immutable |
| GET | `/experiments` | List frozen Experiment Groups for fair-comparison history |
| GET | `/experiments/{id}/results` | Group-level condition scores, per-run reports, failures, and paired-test comparison signals |
| GET | `/experiments/{id}/export.csv` | Download the group summary, run scorecards, failures, and paired comparisons as CSV |
| GET | `/experiments/{id}/reproducibility-bundle.json` | Download the frozen suite, safe run configuration, outcomes and comparison signals as portable JSON |
| GET | `/experiments/{id}/artifact.zip` | Download a byte-stable frozen artifact with manifest hashes, suite, per-run responses/evaluations and post-run retrieval traces |
| POST | `/audits` | Create a reproducible audit run |
| GET | `/audits`, `/audits/{id}` | List or retrieve runs |
| POST | `/audits/{id}/generate-tests` | Generate test cases |
| GET | `/audits/{id}/tests` | List test cases |
| GET | `/audits/{id}/test-review` | Load the frozen canonical suite for researcher review before execution |
| PATCH | `/audits/{id}/tests/{testId}/review` | Accept or reject a test and synchronise that decision to every experiment peer |
| POST | `/audits/{id}/tests/{testId}/regenerate` | Replace one canonical test, quality-check it, and synchronise the replacement to peers |
| POST | `/audits/{id}/execute` | Execute target responses |
| POST | `/audits/{id}/cancel` | Cancel one unfinished audit condition while preserving safe completed evidence |
| POST | `/audits/{id}/evaluate` | Evaluate responses and complete the run |
| GET | `/audits/{id}/retry-plan` | Inspect the first incomplete durable stage of a failed run |
| POST | `/audits/{id}/retry` | Resume a failed run without repeating completed work |
| GET | `/audits/{id}/results` | Scorecard and traceable failures |
| GET | `/audits/{id}/evaluation-review` | Completed automated verdicts and optional saved human calibration labels |
| PATCH | `/audits/{id}/evaluations/{evaluationId}/review` | Save a pseudonymous independent, reference, or adjudication label without changing the automated result |
| GET | `/audits/{id}/evaluation-calibration` | Calibration against explicit resolved labels, plus independent-review agreement and κ |
| GET | `/audits/{id}/target-memory-trace` | Terminal-run evidence of the independently controlled target memory store |
| GET | `/audits/{id}/cancelled-evidence` | Retained completed responses and safe target-memory trace for a cancelled condition |
| GET | `/audits/{id}/failures/{failureId}` | One failure with full evidence |
| GET | `/experiments/summary` | Legacy weak/strong summaries kept separate per comparison group |
| POST | `/research/annotations/validate` | Validate a versioned human annotation JSON release and return its content fingerprint; does not store it |
| POST | `/research/pilot/analyse` | Validate two independent de-identified annotation label sets, adjudications and formal-study readiness; does not store them |
| POST | `/research/formal/synthetic-matrix` | Materialise an explicitly authorised, frozen **synthetic** annotation release into paired operational audit groups after the matching double-annotation pilot passes |
| POST | `/research/evaluator-calibration/analyse` | Analyse a versioned, de-identified human-review release against automated evaluator decisions; does not store it |
| POST | `/research/validity/report` | Calculate extraction, relationship, test-quality and evaluator validity metrics against supplied human labels |
| POST | `/research/benchmarks/longmemeval/validate` | Validate and normalise a locally supplied LongMemEval-compatible JSON file; does not download or execute a benchmark |
| POST | `/research/benchmarks/longmemeval/run` | Execute a locally supplied compatible source in isolated in-memory target-memory simulations; does not download, retain, or call an LLM |
| POST | `/research/benchmarks/locomo/validate`, `/research/benchmarks/beam/validate` | Validate caller-supplied local-compatible LoCoMo/BEAM JSON; no download, persistence, or official-loader claim |
| POST | `/research/benchmarks/locomo/run`, `/research/benchmarks/beam/run` | Run caller-supplied compatible cases in isolated in-memory simulations; never official LoCoMo/BEAM scores |

The API returns `409 Conflict` for an invalid audit lifecycle action and `422 Unprocessable Entity` when consent or required review data is absent.

The audit result also includes `evaluation_warnings` when one or more stored
verdicts used the deterministic fallback. This keeps a provider outage visible
even when every individual test passed; fallback verdicts are not presented as
ordinary LLM-judge outcomes.

Shared-suite review is also frozen as soon as any condition in the comparison
group enters execution or a terminal state. This prevents a later edit from
causing peers to answer different test versions. Duplicate execute/evaluate
requests for the same run are rejected while that stage is already active.

## Local data lifecycle

The Audit History page offers an export and a permanent local-delete control for each conversation. Export is read-only and creates a `conversation-export-v1` JSON file containing source messages, reviewed ground truth, experiment metadata, test cases, target responses and evaluations. It deliberately excludes API keys and raw provider payloads.

`POST /conversations` accepts either `pasted_text` or structured `messages`. For structured input, every supplied `message_id`, `role`, `content`, timestamp and array order is retained. Reused source IDs from separate uploaded conversations are supported safely because the database keeps a separate internal key. Source message IDs must be unique within one uploaded conversation. Pasted text follows the documented one-non-empty-line-per-message convention; a leading `[User]`, `[Assistant]`, `[System]` or custom role is retained.

`PATCH /memories/{memory_id}` can update the canonical value, review status, source message IDs, observed timestamp and `UPDATE`, `CONFLICT` or `CONTEXTUAL_OVERRIDE` relationships. Evidence IDs and relationship targets are verified against the same authorised conversation.

Deletion is an irreversible local operation: `DELETE /conversations/{id}` requires `{"confirmation":"{id}"}`. It atomically removes the selected conversation, messages, reviewed memories and relationships, experiment groups, audit runs, tests, target responses, evaluations and private target-memory operational records derived from that conversation. Download an export before deletion when a copy is required for research retention.

`POST /audits` accepts target `provider` and `model`, plus optional `pipeline_provider`, `pipeline_model`, `evaluator_provider`, and `evaluator_model`. It also accepts `target_system_adapter` (currently `controlled-memory`), `memory_maintenance_policy`: `append_only` or `update_aware_consolidation` (the default), and a frozen `target_memory_capacity` between 1 and 500 (default 50). The adapter lifecycle is `ingest → answer → trace → reset`; its name and version are persisted with the run. This controls only the target Agent's private write-side lifecycle; it is separate from `memory_strategy`, which controls retrieval. Retrieval strategies are `no_memory`, `full_context`, `weak_first_hit`, `strong_rule_based`, `strong_score_based`, `scope_aware`, and `temporal_importance`. `no_memory` and `full_context` are explicit reference ablations: the first exposes no retrieved records, while the second replays all eligible active records without ranking. The final strategy ranks relevant records using their relative position in the authorised conversation plus transparent scope/relationship importance. It never uses the wall-clock time of an audit; each retrieval trace contains chronology basis, normalised recency factor, importance components and final temporal-importance score. `scope_aware` gives current project requirements priority for context-specific prompts, while treating profile and preference records as primary only for matching questions. Each provider is one of `rule_based`, `openai`, `deepseek`, or `gemini`. When pipeline or evaluator fields are omitted, the backend defaults from its environment. A missing provider key is reported during execution as `503 Service Unavailable`, without exposing configuration secrets. Extractor-local IDs are translated to globally unique durable IDs when stored, so separate authorised conversations can safely reuse labels such as `M001`.

`POST /audits` also accepts optional `target_memory_writer`: `rule_based` or `llm_structured`. If omitted, the backend resolves `TARGET_MEMORY_WRITER` **once at creation**. The resulting run always returns its persisted writer kind and writer version, and includes both in reproducibility metadata. Later execution uses those persisted values rather than the current process environment. `llm_structured` requires a non-rule-based frozen pipeline provider.

`GET /audits/{id}/tests` and test-generation responses intentionally omit the private target-memory context. They do include the test type (`direct`, `contextual`, `paraphrased`, or `indirect`) and a quality/grounding decision. The server gives private context only to the controlled target during execution; this prevents a client or target model from using evaluator-only material.

To run a fair matrix comparison, first create an Experiment Group, then create all its audit runs with the returned `experiment_id`. The first run to generate tests becomes the canonical suite source; peer runs receive cloned test cases with their own response/evaluation records and a private `suite_test_id` link back to that source. The experiment freezes test budget, seed, prompt-template version, pipeline provider/model, evaluator provider/model and suite mode. New conditions may be added only while the Experiment Group is `CREATED`; generating its shared suite or reaching a terminal state freezes membership. Suite modes are `behavioural`, `direct_ground_truth`, and `fixed_template`.

`POST /audits/{id}/cancel` safely stops one executing or evaluating condition between provider calls and stops the browser's current execution queue. The backend uses a conditional state transition at the end of each stage, so a concurrent cancellation cannot be overwritten by a stale executor. `POST /experiments/{id}/cancel` marks every unfinished condition in the group as `CANCELLED`; completed outcomes remain available for inspection. Cancellation is terminal and intentionally cannot be retried, preserving the meaning of a frozen comparison. The Experiments history page exposes this group-level action after a browser refresh.

## Research validation endpoints

Research payloads are intentionally request-scoped: the service validates them but never writes annotation or external benchmark source data to the operational audit database. The one deliberate exception is `POST /research/formal/synthetic-matrix`: it only accepts a dataset whose declared origin contains `synthetic`, an explicit persistence confirmation, and a matching human double-annotation package that has passed the formal-readiness gate. It creates one ordinary Experiment Group per synthetic scenario, with an accepted, grounded fixed suite cloned to each selected strategy. It never pre-populates target responses, accepts participant data, or converts an external benchmark into stored operational data. Archive approved, de-identified releases in version-controlled research storage and record the returned SHA-256 fingerprint in the experiment report.

`POST /research/validity/report` accepts a complete `AnnotationDataset` and a `ResearchPredictionSet`. For extraction, each generated candidate has an explicit `matched_gold_memory_id` supplied by an independent reviewer; leave it null for an unmatched candidate. This makes the otherwise subjective semantic matching decision visible. Relationships are evaluated as an ordered `(source, type, target)` tuple. Tests are positive only when both `grounded=true` and `quality_label=accept`. Evaluator validity uses **failure detection** as the positive class and is measured per response ID, so multiple responses to the same test remain separate observations.

`POST /research/pilot/analyse` accepts one `PilotAnnotationPackage`: a declared, de-identified item list; exactly two independent pseudonymous annotator label sets; and separate `adjudicated` or `external_reference` labels. It never accepts source conversation text. It reports per-task and overall label coverage, raw pre-adjudication agreements/disagreements, adjudicated disagreement count, percent agreement and unweighted Cohen's kappa when the statistic is mathematically defined. Readiness is deliberately conservative and uses the package's declared `minimum_paired_items_per_task` and optional `minimum_kappa`; it also requires both labels and an adjudication/reference label for every declared item. A null kappa (for example, where expected agreement is one) is marked not applicable rather than treated as zero. See the blank [double-annotation pilot template](../datasets/annotation/pilot-v1/double_annotation_pilot_template.json).

`POST /research/formal/synthetic-matrix` accepts `dataset`, `pilot`, at least two target `conditions`, a random seed and `synthetic_data_confirmation: true`. A condition fixes its strategy, provider, model and temperature. The server rejects a non-synthetic declared origin, a pilot that names another dataset/version, an unready pilot, duplicate strategies, or an already materialised scenario. It returns experiment and run IDs in `TESTS_GENERATED`; clients execute and evaluate those runs explicitly. This preserves a reviewable boundary between freezing the study design and consuming target-model calls.

`POST /research/benchmarks/longmemeval/validate` is a compatibility adapter, not a LongMemEval implementation. It accepts an array or a top-level `records`, `data`, `questions`, or `examples` array. Every record needs a question, reference answer and message/session context. See [the synthetic local sample](../datasets/benchmarks/longmemeval-compatible-v1/local_sample.json) and its [adapter notes](../datasets/benchmarks/longmemeval-compatible-v1/README.md). Obtain official data separately and follow its licence/citation conditions.

`POST /research/benchmarks/{family}/run` accepts the validated `payload`, plus `source_authorised: true`, optional `source_label`, `memory_strategy` (`no_memory`, `full_context`, `weak_first_hit`, `strong_rule_based`, `strong_score_based`, `scope_aware`, or `temporal_importance`) and `random_seed`. It keeps every case isolated: user-authored messages are ingested in chronological order into a fresh in-memory target-memory simulation, then a deterministic policy retrieves records and a deterministic reference-answer matcher scores the response. The response contains per-case retrieval evidence, token-level F1 diagnostics, measured case latency, category and dimension summaries, a reproducible source SHA-256 fingerprint, deterministic run ID, strategy and runner versions. Token F1 and latency are transparent local diagnostics, not official upstream benchmark scores. For `temporal_importance`, the runner normalises sequential message order into a recency factor and combines it with transparent scope/relationship importance; it does not use runtime wall-clock values for retrieval. It never writes benchmark data to PostgreSQL, calls a provider, downloads data, or claims an official external-benchmark score. The caller remains responsible for the source dataset's licence, citation, consent and privacy conditions.

`POST /research/benchmarks/locomo/*` and `/beam/*` use the same request-scoped safety boundary for small caller-supplied compatibility subsets. The adapters accept a common local case shape (a question/query/prompt, reference answer, and message/conversation/dialogue/session list), return normalised cases, and the runners return every case's selected retrieval records plus category and Memory Health dimension summaries. They do not download, retain, redistribute, fully parse, or score upstream datasets; label outputs **local compatibility results**, never official LoCoMo or BEAM scores. `source_authorised: true` is required for execution.

Before execution, the UI loads `/test-review` from the canonical suite. A reviewer may accept, reject, or regenerate a question. A reject blocks execution until it is replaced or accepted, and any decision/replacement is copied to every peer run, preserving a fair shared suite. Regenerated tests return to `pending` and require an explicit acceptance.

`GET /audits/{id}/target-memory-trace` is deliberately available only after a terminal `COMPLETED` or `CANCELLED` audit. It exposes the target's independently written records, scopes, lifecycle links, writer version, maintenance-policy decisions and retrieval ranking decisions, but excludes evaluator-only expected behaviour and never exposes runtime target-memory context during execution. `GET /audits/{id}/cancelled-evidence` additionally lists only the target responses that completed before cancellation.

`GET /audits/{id}/evaluation-review` is also completion-only. A researcher may save a pseudonymous PASS/FAIL review at `PATCH /audits/{id}/evaluations/{evaluationId}/review`; it creates calibration evidence alongside, rather than replacing, the immutable automated verdict. The legacy payload remains valid and creates a `reference` label. Send `review_role: "independent"` for each blind reviewer; those labels coexist and are never silently majority-voted. An explicit `adjudication` must cite its `based_on_review_ids`, and takes precedence over a reference label for calibration. `GET /audits/{id}/evaluation-calibration` compares automation only with explicit reference/adjudication labels, while separately reporting independent-review coverage, consensus/conflict counts, pairwise agreement and κ. Use `POST /research/evaluator-calibration/analyse` for a separate versioned, de-identified review release with failure-type confusion cells and Cohen’s κ.

`GET /experiments/{id}/reproducibility-bundle.json` exports the frozen public suite, safe configuration snapshots, results and paired comparisons. It deliberately omits source conversations, credentials, raw provider payloads and private target-memory runtime context.

`GET /experiments/{id}/artifact.zip` is the research hand-off format. Its fixed-timestamp ZIP contains `manifest.json`, the frozen test suite, condition and paired summaries, and for each completed run its configuration, result, sanitised responses/evaluations and post-completion retrieval trace. The manifest records a SHA-256 hash for every payload file, the frozen-suite/dataset hash, configuration fingerprints and the optional build-time `AUDITOR_CODE_REVISION`. It deliberately excludes raw conversation text, API keys and raw provider payloads. The Dashboard also reports source-evidence proxy retrieval metrics: Evidence Recall@k, Evidence Precision@k, update evidence recall, conflict evidence coverage and unnecessary retrieval rate. These compare source message IDs because target-private records and reviewer-approved ground-truth records use distinct IDs; they must not be interpreted as semantic retrieval metrics.

`GET /experiments/{id}/results` groups repeated runs by provider, model and memory strategy. It reports means and population standard deviations while leaving zero-test dimensions as unmeasured. Its pairwise rows align outcomes by the canonical `suite_test_id`, not by question text. Each row includes a deterministic 2,000-resample percentile bootstrap interval for the candidate-minus-reference pass-rate delta and an exact two-sided sign-test p-value over discordant tests. These are pilot-study support signals, not a substitute for a preregistered statistical analysis.

Each condition summary also reports the mean recorded response latency and total
input/output/combined token counts when the selected provider exposes them. A
dash means the provider did not report that measurement; monetary cost is not
calculated because provider pricing is not fixed by the audit protocol.
