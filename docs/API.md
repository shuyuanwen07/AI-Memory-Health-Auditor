# API

The interactive OpenAPI contract is available at `/docs` when the backend is running. All JSON endpoints are versioned beneath `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Service health |
| GET | `/target-providers` | Selectable target providers and backend configuration status; never returns secrets |
| POST | `/conversations` | Store authorised pasted or structured conversation data |
| GET | `/conversations/{id}` | Retrieve conversation and messages |
| POST | `/conversations/{id}/extract` | Extract candidate memories |
| GET | `/conversations/{id}/memories` | List reviewed candidates |
| POST | `/memories` | Add a missing memory |
| PATCH | `/memories/{id}` | Accept, edit, reject, or amend relationships |
| DELETE | `/memories/{id}` | Mark a memory rejected |
| POST | `/conversations/{id}/confirm-ground-truth` | Confirm reviewed ground truth |
| POST | `/experiments` | Create an Experiment Group with one frozen shared-test-suite configuration |
| GET | `/experiments` | List frozen Experiment Groups for fair-comparison history |
| GET | `/experiments/{id}/results` | Group-level condition scores, per-run reports, failures, and paired-test comparison signals |
| GET | `/experiments/{id}/export.csv` | Download the group summary, run scorecards, failures, and paired comparisons as CSV |
| POST | `/audits` | Create a reproducible audit run |
| GET | `/audits`, `/audits/{id}` | List or retrieve runs |
| POST | `/audits/{id}/generate-tests` | Generate test cases |
| GET | `/audits/{id}/tests` | List test cases |
| GET | `/audits/{id}/test-review` | Load the frozen canonical suite for researcher review before execution |
| PATCH | `/audits/{id}/tests/{testId}/review` | Accept or reject a test and synchronise that decision to every experiment peer |
| POST | `/audits/{id}/tests/{testId}/regenerate` | Replace one canonical test, quality-check it, and synchronise the replacement to peers |
| POST | `/audits/{id}/execute` | Execute target responses |
| POST | `/audits/{id}/evaluate` | Evaluate responses and complete the run |
| GET | `/audits/{id}/retry-plan` | Inspect the first incomplete durable stage of a failed run |
| POST | `/audits/{id}/retry` | Resume a failed run without repeating completed work |
| GET | `/audits/{id}/results` | Scorecard and traceable failures |
| GET | `/audits/{id}/target-memory-trace` | Post-completion evidence of the independently controlled target memory store |
| GET | `/audits/{id}/failures/{failureId}` | One failure with full evidence |
| GET | `/experiments/summary` | Average comparison across completed weak and strong controlled runs |
| POST | `/research/annotations/validate` | Validate a versioned human annotation JSON release and return its content fingerprint; does not store it |
| POST | `/research/validity/report` | Calculate extraction, relationship, test-quality and evaluator validity metrics against supplied human labels |
| POST | `/research/benchmarks/longmemeval/validate` | Validate and normalise a locally supplied LongMemEval-compatible JSON file; does not download or execute a benchmark |
| POST | `/research/benchmarks/longmemeval/run` | Execute a locally supplied compatible source in isolated in-memory target-memory simulations; does not download, retain, or call an LLM |

The API returns `409 Conflict` for an invalid audit lifecycle action and `422 Unprocessable Entity` when consent or required review data is absent.

`POST /audits` accepts target `provider` and `model`, plus optional `pipeline_provider`, `pipeline_model`, `evaluator_provider`, and `evaluator_model`. It also accepts `memory_maintenance_policy`: `append_only` or `update_aware_consolidation` (the default). This controls only the target Agent's private write-side lifecycle; it is separate from `memory_strategy`, which controls retrieval. Each provider is one of `rule_based`, `openai`, `deepseek`, or `gemini`. When pipeline or evaluator fields are omitted, the backend defaults from its environment. A missing provider key is reported during execution as `503 Service Unavailable`, without exposing configuration secrets.

`GET /audits/{id}/tests` and test-generation responses intentionally omit the private target-memory context. They do include the test type (`direct`, `contextual`, `paraphrased`, or `indirect`) and a quality/grounding decision. The server gives private context only to the controlled target during execution; this prevents a client or target model from using evaluator-only material.

To run a fair matrix comparison, first create an Experiment Group, then create all its audit runs with the returned `experiment_id`. The first run to generate tests becomes the canonical suite source; peer runs receive cloned test cases with their own response/evaluation records and a private `suite_test_id` link back to that source. The experiment freezes test budget, seed, prompt-template version, pipeline provider/model and suite mode. Suite modes are `behavioural`, `direct_ground_truth`, and `fixed_template`.

## Research validation endpoints

Research payloads are intentionally request-scoped: the service validates them but never writes annotation or external benchmark source data to the operational audit database. Archive approved, de-identified releases in version-controlled research storage and record the returned SHA-256 fingerprint in the experiment report.

`POST /research/validity/report` accepts a complete `AnnotationDataset` and a `ResearchPredictionSet`. For extraction, each generated candidate has an explicit `matched_gold_memory_id` supplied by an independent reviewer; leave it null for an unmatched candidate. This makes the otherwise subjective semantic matching decision visible. Relationships are evaluated as an ordered `(source, type, target)` tuple. Tests are positive only when both `grounded=true` and `quality_label=accept`. Evaluator validity uses **failure detection** as the positive class and is measured per response ID, so multiple responses to the same test remain separate observations.

`POST /research/benchmarks/longmemeval/validate` is a compatibility adapter, not a LongMemEval implementation. It accepts an array or a top-level `records`, `data`, `questions`, or `examples` array. Every record needs a question, reference answer and message/session context. See [the synthetic local sample](../datasets/benchmarks/longmemeval-compatible-v1/local_sample.json) and its [adapter notes](../datasets/benchmarks/longmemeval-compatible-v1/README.md). Obtain official data separately and follow its licence/citation conditions.

`POST /research/benchmarks/longmemeval/run` accepts the same `payload`, plus `source_authorised: true`, optional `source_label`, `memory_strategy` (`weak_first_hit`, `strong_rule_based`, or `strong_score_based`) and `random_seed`. It keeps every case isolated: user-authored messages are ingested in chronological order into a fresh in-memory target-memory simulation, then a deterministic policy retrieves records and a deterministic reference-answer matcher scores the response. The response contains per-case retrieval evidence, category and dimension summaries, a reproducible source SHA-256 fingerprint, deterministic run ID, strategy and runner versions. It never writes benchmark data to PostgreSQL, calls a provider, downloads data, or claims an official LongMemEval score. The caller remains responsible for the source dataset's licence, citation, consent and privacy conditions.

Before execution, the UI loads `/test-review` from the canonical suite. A reviewer may accept, reject, or regenerate a question. A reject blocks execution until it is replaced or accepted, and any decision/replacement is copied to every peer run, preserving a fair shared suite. Regenerated tests return to `pending` and require an explicit acceptance.

`GET /audits/{id}/target-memory-trace` is deliberately available only once the audit is `COMPLETED`. It exposes the target's independently written records, scopes, lifecycle links, writer version, maintenance-policy decisions and retrieval ranking decisions, but excludes evaluator-only expected behaviour and never exposes runtime target-memory context before completion.

`GET /experiments/{id}/results` groups repeated runs by provider, model and memory strategy. It reports means and population standard deviations while leaving zero-test dimensions as unmeasured. Its pairwise rows align outcomes by the canonical `suite_test_id`, not by question text. Each row includes a deterministic 2,000-resample percentile bootstrap interval for the candidate-minus-reference pass-rate delta and an exact two-sided sign-test p-value over discordant tests. These are pilot-study support signals, not a substitute for a preregistered statistical analysis.
