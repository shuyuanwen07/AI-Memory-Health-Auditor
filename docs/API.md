# API

The interactive OpenAPI contract is available at `/api/v1/docs` when the backend is running. All JSON endpoints are versioned beneath `/api/v1`.

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
| GET | `/experiments/{id}/results` | Group-level condition scores, per-run reports, uniquely paired answer rows, failures, and paired-test comparison signals |
| GET | `/experiments/{id}/export.csv` | Download group and run summaries, every uniquely paired answer row, failures, and paired comparisons as CSV |
| GET | `/experiments/{id}/reproducibility-bundle.json` | Download the frozen suite, safe run configuration, per-answer outcomes and evidence, and comparison signals as portable JSON |
| GET | `/experiments/{id}/artifact.zip` | Download a byte-stable frozen artifact with manifest hashes, suite, per-run responses/evaluations and post-run retrieval traces |
| POST | `/audits` | Create a reproducible audit run |
| POST | `/audits/{id}/method-comparison` | Prepare three Experiment A conditions and a source-bound defect inventory plus rule-generated fixed-template draft |
| POST | `/audits/{id}/retrieval-improvement` | Idempotently fork an approved, completed A condition into a same-question, same-reader paired retest using `relationship_packet` |
| GET | `/research/retrieval-improvements/latest` | Report source-bound, same-question paired outcomes with human-review basis and unresolved counts |
| POST | `/audits/{id}/method-comparison-inventory` | Freeze the independently reviewed source-defect inventory and researcher-reviewed, rule-seeded fixed-template release before any question generation |
| POST | `/audits/{id}/method-comparison-discovery-mapping` | Freeze the researcher-confirmed mapping from every saved response in one Experiment A condition to zero or more IDs in the frozen defect inventory |
| GET | `/audits/{id}/method-comparison-results?comparison_id=...` | Report Experiment A validity, category coverage, response-level recall/FPR, distinct-failure discovery, budgets and recorded attempts |
| GET | `/audits`, `/audits/{id}` | List or retrieve runs |
| POST | `/audits/{id}/generate-tests` | Generate test cases |
| GET | `/audits/{id}/tests` | List test cases |
| GET | `/audits/{id}/test-review` | Load the frozen canonical suite for researcher review before execution |
| PATCH | `/audits/{id}/tests/{testId}/review` | Accept or reject a test and synchronise that decision to every experiment peer |
| PATCH | `/audits/{id}/tests/{testId}/human-validity-review` | Save a separate, self-declared researcher validity decision for an Experiment A question |
| POST | `/audits/{id}/tests/{testId}/regenerate` | Replace one canonical test, quality-check it, and synchronise the replacement to peers |
| POST | `/audits/{id}/execute` | Execute target responses |
| POST | `/audits/{id}/cancel` | Cancel one unfinished audit condition while preserving safe completed evidence |
| POST | `/audits/{id}/evaluate` | Evaluate responses and complete the run |
| GET | `/audits/{id}/retry-plan` | Inspect the first incomplete durable stage of a failed run |
| POST | `/audits/{id}/retry` | Resume a failed run without repeating completed work |
| GET | `/audits/{id}/results` | Scorecard and traceable failures |
| POST | `/audits/{id}/reassessment` | Prepare an idempotent separate assessment of exact saved answers; execute no target calls |
| GET | `/audits/{id}/source-history` | Complete original messages in source order, without verdicts or internal identifiers |
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
| POST | `/research/exploratory/synthetic-matrix` | Materialise an explicitly exploratory synthetic engineering matrix; does not qualify as Experiment B |
| POST | `/research/evaluator-calibration/analyse` | Analyse a versioned, de-identified human-review release against automated evaluator decisions; does not store it |
| POST | `/research/validity/report` | Calculate extraction, relationship, test-quality and evaluator validity metrics against supplied human labels |
| POST | `/research/benchmarks/longmemeval/validate` | Validate and normalise a locally supplied LongMemEval-compatible JSON file; does not download or execute a benchmark |
| POST | `/research/benchmarks/longmemeval/run` | Execute a locally supplied compatible source in isolated in-memory target-memory simulations; does not download, retain, or call an LLM |
| POST | `/research/benchmarks/locomo/validate`, `/research/benchmarks/beam/validate` | Validate caller-supplied local-compatible LoCoMo/BEAM JSON; no download, persistence, or official-loader claim |
| POST | `/research/benchmarks/locomo/run`, `/research/benchmarks/beam/run` | Run caller-supplied compatible cases in isolated in-memory simulations; never official LoCoMo/BEAM scores |

To register a multi-scenario A campaign, pass `{"campaign_id":"study-id","scenario_id":"scenario-id","planned_scenarios":4}` to the method-comparison creation endpoint for each completed source audit. All scenarios must use different source conversations and scenario IDs, the same planned count, and matching target, generator, evaluator, memory and test-budget settings. Registration precedes question generation. Existing empty-body calls remain standalone comparisons. The Dashboard counts only completed scenarios in the campaign; human labels, unresolved responses and per-scenario links remain separate from automatic judgments. Registration alone does not create or approve source material, questions, or human reviews.

For a source condition within a registered A campaign, `POST /audits/{id}/retrieval-improvement` accepts `{"study_id":"study-id"}`. It clones the exact saved question suite with source test lineage, preserves the weak reader and other target settings, and selects `relationship_packet`; target answers, evaluations and human review are never copied. The operation is idempotent for the same source and study. `/research/retrieval-improvements/latest` returns `null` until a study exists. Matched improvements and regressions require both sides to have a human verdict with the same review basis; single-human references and independent-human consensus remain distinct. This is a paired diagnostic replay on already observed synthetic histories, not an independent held-out evaluation.

The API returns `409 Conflict` for an invalid audit lifecycle action and `422 Unprocessable Entity` when consent or required review data is absent.

Audit stage mutations use a local nonblocking lock and, on PostgreSQL, a dedicated
session advisory lock shared across API workers. Shared-suite edits, extraction,
execution, evaluation, recovery and answer reuse retain protection across intermediate
artifact commits. A competing request receives 409 before starting duplicate work.
The recovery planner probes the same database lock scopes to report ongoing work
in another worker. Locks release on stage exit; connection invalidation prevents a
failed release from returning a locked session to the pool. SQLite tests retain
local-process protection only. These guards do not certify all multi-worker
operations or unlimited concurrency. Evaluation human-review writes also use the
run scope, preventing concurrent updates and final decisions from interleaving.

An adjudication request must include `based_on_review_versions`, mapping every
`based_on_review_ids` entry to the `updated_at` timestamp displayed in the loaded
independent review. Missing or mismatched keys return 422. If a cited review was
updated since the page loaded, saving returns 409 with refresh guidance and writes
no final label. Reload the review evidence and recheck the changed judgements
before resubmitting; the frontend provides an explicit refresh action. Existing
stored labels are retained. A final decision must cite the complete current set
of independent labels: a newly added reviewer invalidates the old adjudication
for calibration, and a partial or stale set returns 409. Refresh and explicitly
re-adjudicate all labels; none are silently discarded or majority-voted.
Review identities remain supplied attestations.

The audit result also includes `evaluation_warnings` when one or more stored
judge calls were unavailable or invalid. Their verdict is uncertain, excluded
from scores, and any deterministic advisory result is not treated as an LLM
verdict. Independently selected rule-based evaluation remains a lexical baseline.

Shared-suite review is also frozen as soon as any condition in the comparison
group enters execution or a terminal state. This prevents a later edit from
causing peers to answer different test versions. Duplicate execute/evaluate
requests for the same run are rejected while that stage is already active.

## Local data lifecycle

The Audit History page offers an export and a permanent local-delete control for each conversation. Export is read-only and creates a `conversation-export-v1` JSON file containing source messages, reviewed ground truth, experiment metadata, test cases, target responses and evaluations. It deliberately excludes API keys and raw provider payloads. The conversation records a declared `source_origin`: `synthetic`, `authorised`, `deidentified`, or `unknown`; the default is `unknown`, and the service never infers origin from transcript text. The export includes an origin-specific research-use notice. These declarations do not establish consent, research eligibility, or independent human labels.

`POST /conversations` accepts either `pasted_text` or structured `messages`. Optional `source_origin` declares the source category; omitted values remain `unknown`. For structured input, every supplied `message_id`, `role`, `content`, timestamp and array order is retained. Reused source IDs from separate uploaded conversations are supported safely because the database keeps a separate internal key. Source message IDs must be unique within one uploaded conversation. Pasted text follows the documented one-non-empty-line-per-message convention; a leading `[User]`, `[Assistant]`, `[System]` or custom role is retained.

`PATCH /memories/{memory_id}` can update the canonical value, review status, source message IDs, observed timestamp and `UPDATE`, `CONFLICT` or `CONTEXTUAL_OVERRIDE` relationships. Evidence IDs and relationship targets are verified against the same authorised conversation.

Long-running stage calls use PostgreSQL advisory locks or renewable database leases on persistent non-PostgreSQL stores. A competing extraction for the same conversation receives `409 Conflict`; an abandoned non-PostgreSQL lease expires after three minutes, and active calls refresh it every 30 seconds. Process-local in-memory SQLite remains protected only within that process because separate in-memory databases do not share records.

Deletion is an irreversible local operation: `DELETE /conversations/{id}` requires `{"confirmation":"{id}"}`. It atomically removes the selected conversation, messages, reviewed memories and relationships, experiment groups, audit runs, tests, target responses, evaluations and private target-memory operational records derived from that conversation. Download an export before deletion when a copy is required for research retention.

`POST /audits` accepts target `provider` and `model`, plus optional `pipeline_provider`, `pipeline_model`, `semantic_review_provider`, `semantic_review_model`, `evaluator_provider`, and `evaluator_model`. `pipeline_*` selects the coverage-planning test-generation Agent; `semantic_review_*` independently selects its duplicate-intent reviewer. Both accept local `ollama` or a configured cloud provider, and their exact choices are stored with the audit. If semantic-review fields are omitted, the reviewer uses the test-generation model. It also accepts `target_system_adapter` (currently `controlled-memory`), `memory_maintenance_policy`: `append_only` or `update_aware_consolidation` (the default), and a frozen `target_memory_capacity` between 1 and 500 (default 50). The adapter lifecycle is `ingest → answer → trace → reset`; its name and version are persisted with the run. This controls only the target Agent's private write-side lifecycle; it is separate from `memory_strategy`, which controls retrieval. Retrieval strategies are `no_memory`, `full_context`, `weak_first_hit`, `strong_rule_based`, `strong_score_based`, `scope_aware`, and `temporal_importance`. `no_memory` and `full_context` are explicit reference ablations: the first exposes no retrieved records, while the second replays all eligible active records without ranking. The final strategy ranks relevant records using their relative position in the authorised conversation plus transparent scope/relationship importance. It never uses the wall-clock time of an audit; each retrieval trace contains chronology basis, normalised recency factor, importance components and final temporal-importance score. `scope_aware` gives current project requirements priority for context-specific prompts, while treating profile and preference records as primary only for matching questions. Providers include `rule_based`, `ollama`, `openrouter`, `openai`, `deepseek`, and `gemini`. When provider/model fields are omitted, the backend resolves defaults from its configuration. A missing cloud credential is reported during execution as `503 Service Unavailable`, without exposing configuration secrets. Extractor-local IDs are translated to globally unique durable IDs when stored, so separate authorised conversations can safely reuse labels such as `M001`.

`POST /audits` also accepts optional `target_memory_writer`: `rule_based` or `llm_structured`. If omitted, the backend resolves `TARGET_MEMORY_WRITER` **once at creation**. The resulting run always returns its persisted writer kind and writer version, and includes both in reproducibility metadata. Later execution uses those persisted values rather than the current process environment. `llm_structured` requires a non-rule-based frozen pipeline provider.

`GET /audits/{id}/tests` and test-generation responses intentionally omit the private target-memory context. They do include the test type (`direct`, `contextual`, `paraphrased`, or `indirect`) and a quality/grounding decision. The server gives private context only to the controlled target during execution; this prevents a client or target model from using evaluator-only material.

To run a fair matrix comparison, first create an Experiment Group, then create all its audit runs with the returned `experiment_id`. The first run to generate tests becomes the canonical suite source; peer runs receive cloned test cases with their own response/evaluation records and a private `suite_test_id` link back to that source. The experiment freezes test budget, seed, prompt-template version, generation provider/model, semantic-review provider/model, evaluator provider/model and suite mode. New conditions may be added only while the Experiment Group is `CREATED`; generating its shared suite or reaching a terminal state freezes membership. Suite modes are `behavioural`, `direct_ground_truth`, `fixed_template`, `paired_contextual`, and `contextual_indirect`; the last restricts generated items to contextual/indirect types and excludes direct-recall items.

`POST /audits/{id}/cancel` safely stops one executing or evaluating condition between provider calls and stops the browser's current execution queue. The backend uses a conditional state transition at the end of each stage, so a concurrent cancellation cannot be overwritten by a stale executor. `POST /experiments/{id}/cancel` marks every unfinished condition in the group as `CANCELLED`; completed outcomes remain available for inspection. Cancellation is terminal and intentionally cannot be retried, preserving the meaning of a frozen comparison. The Experiments history page exposes this group-level action after a browser refresh.

## Research validation endpoints

Research payloads are intentionally request-scoped: the service validates them but never writes annotation or external benchmark source data to the operational audit database. Two deliberate exceptions materialise explicitly authorised synthetic data. `POST /research/formal/synthetic-matrix` is the formal Experiment B path; it requires an explicit frozen `study_design`, a development dataset with no exact normalized-history overlap, at least three repetitions for every target including the deterministic baseline, one fixed provider/model/temperature, paired Weak/Strong policies, and a matching human double-annotation package that has passed the formal-readiness gate. `POST /research/exploratory/synthetic-matrix` is a separate engineering path for unplanned or smaller checks; its results are tagged `study_mode: exploratory` and do not qualify as Experiment B. Both create one ordinary Experiment Group per synthetic scenario, with an accepted, grounded fixed suite cloned to each selected strategy. Neither pre-populates target responses, accepts participant data, or converts an external benchmark into stored operational data. Archive approved, de-identified releases in version-controlled research storage and record the returned SHA-256 fingerprint in the experiment report.

The annotation validation, validity-report and pilot-analysis request wrappers require `source_authorised: true` before analysis. Omitted/false permission returns 422; strings and numbers are rejected rather than coerced. This is an operator declaration, not proof of ownership or independent labels, and does not grant permission to save histories or call a model. Keep the declaration outside the dataset/package so its source fingerprint stays unchanged. Examples: `{"dataset": ..., "source_authorised": true}`, `{"dataset": ..., "predictions": ..., "source_authorised": true}`, and `{"package": ..., "source_authorised": true}`. Older API clients must explicitly add the field; these endpoints no longer analyse their unconfirmed requests.

`POST /research/validity/report` accepts a complete `AnnotationDataset` and a `ResearchPredictionSet`. For extraction, each generated candidate has an explicit `matched_gold_memory_id` supplied by an independent reviewer; leave it null for an unmatched candidate. This makes the otherwise subjective semantic matching decision visible. Relationships are evaluated as an ordered `(source, type, target)` tuple. Tests are positive only when both `grounded=true` and `quality_label=accept`. Evaluator validity uses **failure detection** as the positive class and is measured per response ID, so multiple responses to the same test remain separate observations.

`POST /research/pilot/analyse` accepts one `PilotAnnotationPackage`: a declared, de-identified item list; exactly two independent pseudonymous annotator label sets; and separate `adjudicated` or `external_reference` labels. The `annotation_mode` declaration is required: `human_double_annotation` or `ai_assisted_synthetic_dry_run`. Omission returns 422 rather than implicitly declaring independent human provenance. Explicit declarations remain the submitter's responsibility and do not authenticate independence. It never accepts source conversation text. It reports per-task and overall label coverage, raw pre-adjudication agreements/disagreements, adjudicated disagreement count, percent agreement and unweighted Cohen's kappa when the statistic is mathematically defined. Readiness is deliberately conservative and uses the package's declared `minimum_paired_items_per_task` and optional `minimum_kappa`; it also requires both labels and an adjudication/reference label for every declared item. A null kappa (for example, where expected agreement is one) is marked not applicable rather than treated as zero. See the blank [double-annotation pilot template](../datasets/annotation/pilot-v1/double_annotation_pilot_template.json).

`POST /research/formal/synthetic-matrix` accepts `dataset`, `pilot`, a required `study_design`, a required disjoint `development_dataset`, at least two target `conditions`, at least three `repetitions`, success criteria, a random seed and `synthetic_data_confirmation: true`. The conditions must include `weak_first_hit` and `strong_rule_based`, and all must share one target provider/model/temperature. The server rejects a non-synthetic declared origin, a pilot that does not bind to the exact dataset fingerprint, an unready pilot, reused/duplicate histories, duplicate strategy/provider/model/temperature combinations, mixed target settings, or an already materialised scenario. It saves the plan before target calls and returns experiment and run IDs in `TESTS_GENERATED`; clients execute and evaluate those runs explicitly.

`POST /research/exploratory/synthetic-matrix` accepts the shared synthetic source/pilot and success-criteria checks, but does not accept a `study_design`; it allows one to five repetitions and other multi-model or multi-policy engineering matrices. The response is tagged `study_mode: exploratory`, and those runs must not be represented as formal Experiment B results.

`POST /research/benchmarks/longmemeval/validate` is a compatibility adapter, not a LongMemEval implementation. It accepts an array or a top-level `records`, `data`, `questions`, or `examples` array. Every record needs a question, reference answer and message/session context. See [the synthetic local sample](../datasets/benchmarks/longmemeval-compatible-v1/local_sample.json) and its [adapter notes](../datasets/benchmarks/longmemeval-compatible-v1/README.md). Obtain official data separately and follow its licence/citation conditions.

`POST /research/benchmarks/longmemeval/live` also requires caller-declared `dataset_provenance: {dataset_version, license, citation}`. These declarations are part of the configuration fingerprint and returned evidence. The result includes the exact local-source fingerprint, adapter version and implementation fingerprint, and compatibility limitations. The service does not verify the declared rights or citation.

`POST /research/benchmarks/{family}/run` accepts the validated `payload`, plus `source_authorised: true`, optional `source_label`, `memory_strategy` (`no_memory`, `full_context`, `weak_first_hit`, `strong_rule_based`, `strong_score_based`, `scope_aware`, or `temporal_importance`) and `random_seed`. It keeps every case isolated: user-authored messages are ingested in chronological order into a fresh in-memory target-memory simulation, then a deterministic policy retrieves records and a deterministic reference-answer matcher scores the response. The response contains per-case retrieval evidence, token-level F1 diagnostics, measured case latency, category and dimension summaries, a reproducible source SHA-256 fingerprint, deterministic run ID, strategy and runner versions. Token F1 and latency are transparent local diagnostics, not official upstream benchmark scores. For `temporal_importance`, the runner normalises sequential message order into a recency factor and combines it with transparent scope/relationship importance; it does not use runtime wall-clock values for retrieval. It never writes benchmark data to PostgreSQL, calls a provider, downloads data, or claims an official external-benchmark score. The caller remains responsible for the source dataset's licence, citation, consent and privacy conditions.

`POST /research/benchmarks/locomo/*` and `/beam/*` use the same request-scoped safety boundary for small caller-supplied compatibility subsets. The adapters accept a common local case shape (a question/query/prompt, reference answer, and message/conversation/dialogue/session list), return normalised cases, and the runners return every case's selected retrieval records plus category and Memory Health dimension summaries. They do not download, retain, redistribute, fully parse, or score upstream datasets; label outputs **local compatibility results**, never official LoCoMo or BEAM scores. `source_authorised: true` is required for execution.

Before execution, the UI loads `/test-review` from the canonical suite. A reviewer may accept, reject, or regenerate a question. A reject blocks execution until it is replaced or accepted, and any decision/replacement is copied to every peer run, preserving a fair shared suite. Regenerated tests return to `pending` and require an explicit acceptance.

Experiment A additionally requires an explicit human-validity decision for every
question, stored separately from automated question-quality status. Submit
`{"decision":"accepted","reviewer_pseudonym":"<self-declared pseudonym>","note":"<optional>"}`
or `decision: "rejected"` to
`PATCH /audits/{id}/tests/{testId}/human-validity-review`. Execution returns 409
until all questions in that A condition are accepted. Regenerating a question
clears its prior validity decision. A pseudonym is a declaration and does not
authenticate identity or establish research independence.

The Experiment A result defines a valid question as one with automated quality
accepted, automated grounding grounded, and human validity accepted. The report
counts valid questions and leaves Category Coverage unmeasured until every
question has an explicit human-validity decision. It separately returns accepted,
reviewed, pending, and acceptance-rate fields so an incomplete review is visible.

`GET /audits/{id}/target-memory-trace` is deliberately available only after a terminal `COMPLETED` or `CANCELLED` audit. It exposes the target's independently written records, scopes, lifecycle links, writer version, maintenance-policy decisions and retrieval ranking decisions, but excludes evaluator-only expected behaviour and never exposes runtime target-memory context during execution. `GET /audits/{id}/cancelled-evidence` additionally lists only the target responses that completed before cancellation.

`GET /audits/{id}/source-history` returns `{role, content, timestamp}` for every original message belonging to this audit, including assistant messages. It preserves stored message sequence even when supplied timestamps differ, is read-only, and returns 404 for an unknown audit. The ordinary review screen loads this conversation once per batch rather than duplicating it in every answer. This source history is independent of the target memory-input receipt and does not show what was sent to the model. Blind review uses only its existing blind response and source evidence, without fetching automated verdicts or calibration.

`GET /audits/{id}/evaluation-review` is also completion-only. A researcher may save a pseudonymous PASS/FAIL review at `PATCH /audits/{id}/evaluations/{evaluationId}/review`; it creates calibration evidence alongside, rather than replacing, the immutable automated verdict. The legacy payload remains valid and creates a `reference` label. Send `review_role: "independent"` for each blind reviewer; those labels coexist and are never silently majority-voted. An explicit `adjudication` must cite its `based_on_review_ids`, and takes precedence over a reference label for calibration. `GET /audits/{id}/evaluation-calibration` compares automation only with explicit reference/adjudication labels, while separately reporting independent-review coverage, consensus/conflict counts, pairwise agreement and κ. Use `POST /research/evaluator-calibration/analyse` for a separate versioned, de-identified review release with failure-type confusion cells and Cohen’s κ.

`GET /experiments/{id}/reproducibility-bundle.json` exports the frozen public suite, safe configuration snapshots, results, paired comparisons and uniquely bound per-answer rows. Answer rows retain the saved question, expected behaviour, target response, assessment state (including unassessed responses), canonical memory evidence and only the source statements linked to that evidence. They do not include the full source conversation, credentials, raw provider payloads or private target-memory runtime context. This endpoint is an explicit report export, so its answer-level evidence can contain user-authorised source text.

`GET /experiments/{id}/artifact.zip` is the research hand-off format. Its fixed-timestamp ZIP contains `manifest.json`, the frozen test suite, condition and paired summaries, and for each completed run its configuration, result, sanitised responses/evaluations and post-completion retrieval trace. The manifest records a SHA-256 hash for every payload file, the frozen-suite/dataset hash, configuration fingerprints and the optional build-time `AUDITOR_CODE_REVISION`. It deliberately excludes raw conversation text, API keys and raw provider payloads. The Dashboard also reports source-evidence proxy retrieval metrics: Evidence Recall@k, Evidence Precision@k, update evidence recall, conflict evidence coverage and unnecessary retrieval rate. These compare source message IDs because target-private records and reviewer-approved ground-truth records use distinct IDs; they must not be interpreted as semantic retrieval metrics.

`GET /experiments/{id}/results` groups repeated runs by provider, model and memory strategy. It reports means and population standard deviations while leaving zero-test dimensions as unmeasured. Its pairwise rows align outcomes by the canonical `suite_test_id`, not by question text. Each row includes a deterministic 2,000-resample percentile bootstrap interval for the candidate-minus-reference pass-rate delta and an exact two-sided sign-test p-value over discordant tests. These are pilot-study support signals, not a substitute for a preregistered statistical analysis.

Each condition summary also reports the mean recorded response latency and total
input/output/combined token counts when the selected provider exposes them. A
dash means the provider did not report that measurement; monetary cost is not
calculated because provider pricing is not fixed by the audit protocol.

### Reliability and evidence qualification

`GET /auditor-quality` counts every resolved human label in review coverage, including answers for which the automatic judge abstained. `decided_reference_count` and `labelled_abstention_rate` expose that excluded subset. Binary `accuracy` does not imply correct diagnosis categories: `failure_classification_accuracy` measures category agreement among jointly detected failures with known human categories, while `failure_detection_and_classification_recall` includes human-labelled failures the automatic judge missed. `category_confusion` distinguishes missed failures from unclassified automatic failures. Missing eligible references produce null percentages rather than invented scores.

Audit results retain the historical `overall_score` tested-dimension macro-average. Derived `formal_overall_score` is null unless all four core dimensions have decided scores. Failure details add ordered `source_statements` containing role, original content and timestamp, restricted to the audit conversation and linked evidence; identifiers belonging to other histories cannot expose their source text.


### Lost creation response recovery
`POST /experiments` and `POST /audits` accept an optional `creation_request_key` (16–100 ASCII letters, digits, underscore or hyphen). Retry exactly the same validated request with the same key to recover its saved identity, including after the suite freezes. A different payload with the same key returns 409; intentional repetitions use separate keys. Unique constraints arbitrate simultaneous requests in PostgreSQL. The key and request fingerprint are internal and excluded from public reports. Clients without keys retain the historical creation behaviour. This does not provide idempotency for source import or diagnostic experiment package endpoints.

Local Ollama semantic evaluator v2 cross-checks definite provider verdicts against evidence-rule judgment. Disagreement becomes unscored pending review, retaining both advisory explanations and both verdicts in the saved judge receipt. It is not a rule override or a guarantee of accuracy when both methods agree. Historical results are preserved.

### Saved assessment comparability

Audit comparison pairs only decided, unchanged canonical questions with matching saved assessment implementation, configured judge identity, receipt judge identity and local cross-check version. Local judge v2 without a saved cross-check version is incomplete evidence and is excluded. `excluded_assessments` preserves original answers and pass labels for review; these rows do not enter fixed/regressed counts or paired pass-rate deltas. Historical full-suite scores remain descriptive. This version check does not establish independent evaluator accuracy.

Experiment analytics apply the same saved assessment signature before computing
paired deltas, intervals and sign tests. `shared_tests` counts eligible decided
questions. `shared_question_count` includes all shared evaluated questions,
and `excluded_uncertain_count` counts pairs lacking a decided verdict on either
side. `excluded_assessment_count` reports decided shared questions excluded
because assessment signatures differ or are incomplete. Original scores and
answers remain available. Comparing review methods is an assessment ablation,
not evidence of improved target memory. Exports record `experiment-analytics-v2`
and its saved-assessment alignment policy.

Research validity coverage (2026-10-09)
The offline validity report compares submitted question assessments and decided answer judgments against matching gold references. Missing predictions are not negative decisions. An evaluator prediction may explicitly use `passed: null`; it is counted as abstained, excluded from binary confusion counts, and retained in coverage. Reports include `test_assessment_coverage` and `evaluator_coverage` with expected/submitted/decided/missing/abstained counts. Exact response-to-test correspondence is validated within the annotation release. Partial coverage can yield high decided-case accuracy; it does not establish complete recall or formal acceptance. Extraction and relationship set recall assumes the submitted candidate inventory is complete; a missing inventory must not be presented as a verified extraction result.


Target answer execution metadata may include `completion_status` (`complete`, `truncated`, or null) and a whitelisted `finish_reason`. The status describes provider termination, not semantic correctness. An explicit output-limit termination is unscored (`passed: null`, no failure dimension) by both supported evaluator types. The saved answer remains inspectable. Legacy responses without termination evidence remain unknown and are never silently reclassified using token count alone. No database migration is required: these optional values are retained in the existing JSON execution metadata.
Diagnosis `fact-aware-diagnosis-v8` adds `answer_and_history_review` when
the supplied exact supporting update covers the missing old reference facts,
and every missing unit is exclusively observed as excluded by the superseded
policy. `memory_availability.superseded_only_missing_fact_units` is `null`
when supply is unknown. Unknown matching copies and other exclusion reasons
do not qualify. The diagnosis asks for answer/assessment and historical-context
review together; it does not establish a causal failure or change the target
configuration.


Saved-answer reassessment preserves the completed source audit and selects the current implementation of its recorded assessment service/model. It copies each original evaluation's exact bound response and input receipt into a separate run, with zero target attempts, preserving question acceptance and reference text. It does not copy human labels or formal experiment attestations. A source/software/assessor key reopens an existing reassessment rather than duplicating it. The returned run is ready for the ordinary evaluation endpoint; interrupted evaluation can use ordinary recovery. The UI keeps original and new reports accessible. Changed assessment scores do not demonstrate improved target-model memory performance.

The same endpoint optionally accepts an explicit assessor selection:
`{"evaluator_provider":"openrouter","evaluator_model":"<specific model ID>"}`.
Omitting the body preserves same-assessor reassessment. Cloud/local model selections
require a nonblank model name; automatic routing and `latest` aliases are rejected.
Unknown fields/providers and unavailable explicitly selected services return 422.
Each source/runtime/provider/model combination has its own idempotent result, even
when requested through another reassessment of that source. Target questions,
reference text and exact saved answers are copied unchanged. Preparation does not
call either model; the ordinary evaluation endpoint invokes the selected assessor.
An accepted model name is not proof that the upstream account can call it; actual
execution and its receipts establish that. This is the backend foundation for
controlled multi-assessor comparison, not an empirical auditor-accuracy result.

Research validity identity and provenance (2026-10-11)
The report records `metric_version`, `annotation_fingerprint_sha256`, `prediction_fingerprint_sha256` and a limitations notice. Hashes use canonical validated model JSON, not raw file bytes or authenticated authorship. Current metric version is `research-count-metrics-v1`; F1 uses raw counts, 2TP/(2TP+FP+FN). No positive denominator remains null; positive errors with zero TP yield 0%. Structured keys preserve distinct conversation/local IDs even when delimiters occur, and unmatched candidates cannot collide with gold memory names. The UI can export these bound metrics; changing either input clears the previous result and export. Independent references and complete candidate inventories remain research obligations.

Experiment results exports preserve condition identity and separate passed, decided, pending, and unassessed responses. The results API and JSON bundle expose per-run `answers` rows; CSV writes the same uniquely bound answer rows alongside summaries, including IDs, question, expected behaviour, answer, outcome, assessment reason, canonical evidence and linked source statements. Ambiguous duplicate or cross-run test/response bindings are omitted rather than selected by row order. CSV includes a `condition_id` column for linking records even when display labels coincide. JSON reproducibility bundles include `analysis_metadata`; fixed-material ZIPs include the same content as `analysis-metadata.json`. These record the descriptive bootstrap/sign-test method, its version, and limits. A single paired question has no estimable confidence interval; missing and uncertain judgments are excluded from decided scores and reported separately. Technical identities remain in reproducibility exports rather than primary chart labels.

### Reviewed release binding for formal matrices

`PilotAnnotationPackage.dataset_fingerprint_sha256` records the canonical SHA-256
of the reviewed `AnnotationDataset`. It is optional for analysing legacy pilot
agreement, but mandatory and content-matched for creating a formal synthetic matrix.
Matching dataset names and versions alone cannot satisfy this gate. Source or gold
reference changes invalidate the binding before any operational rows are written.
The UI exports `dataset-review-receipt.json` after dataset validation. Reviewers must
record that receipt fingerprint after reviewing the exact release; the UI never
automatically binds old labels to newly uploaded data. Pilot agreement passing does
not by itself prove dataset matching, reviewer independence or formal study validity.

### Saved-answer provenance in audit comparisons

`answer_provenance` distinguishes `target_executions`, `same_saved_answers`,
`different_saved_executions` and `unknown_saved_answers`. Reused-answer identity
is checked from each unchanged shared question's evaluated response receipt
(original run and response identity), with exact response text equality required
for the same-answer claim. Matching words alone do not establish reuse. Missing
receipts, conflicting text or mixed origins remain unknown. The comparison page
and SVG explain the saved provenance without altering historical results.
Different original executions can be assessed under matching standards, but
configuration changes and experimental independence still govern interpretation.

### Standalone comparison charts

Saved comparison SVGs embed `audit-comparison-chart-v1` metadata: saved run and
answer-source identities, selected model/assessor/memory settings, configuration
fingerprint and saved source hash when recorded, question scope, dimension
numerators/denominators, uncertainty coverage, saved assessor versions, paired
outcomes and comparison warnings. Missing historical fields remain null or absent;
current software values are not substituted. The chart visibly retains essential
limits for full-suite scope, changed assessment standards and combined configuration
changes. Custom instruction text and arbitrary reproducibility metadata are not
copied into the chart; inspect the original saved audit for full evidence.

### Observed input-delivery evidence

Diagnosis `input_delivery.version = input-stage-correspondence-v3` preserves
`complete_retrieved_match = null` when the reference facts or saved selection
are unavailable. A recorded empty selection with known reference facts is
`false`; exact complete selection is `true`. Exclusion counts describe only
unambiguous recorded supporting-fact exclusions, so zero is not proof that all
exclusions were observed. Answer-time eligibility counts likewise describe
recorded observations rather than the model's internal use of memory.


### Saved AI-assessor comparisons

`POST /assessor-comparisons` saves a plan with `creation_request_key`,
`source_run_id` and two to five distinct `assessors` using the explicit
reassessment selection shape. A repeated identical key reopens its plan;
a changed payload with that key returns 409. A reassessment source resolves
to its original completed audit. Preparation and creation incur no model calls.

`POST /assessor-comparisons/{id}/prepare` creates missing assessor runs over
exact saved questions, references and answers. Each prepared association is
committed separately; a service failure retains earlier progress. Repeating
preparation reuses prepared rows. Software changes block new preparation,
while saved plans/results remain readable. The ordinary run evaluation and
retry endpoints finish each assessor; target execution remains prohibited.

`GET /assessor-comparisons` and `GET /assessor-comparisons/{id}` expose saved
plans, current per-assessor run states and completed results. The AI assessors
page restores these server records and charts only completed results. Its
pass-rate bars are automated verdict differences, not assessor accuracy or
model-memory improvement. Cost and assessor latency remain unmeasured in
this first presentation; no missing billing evidence is represented as zero.

Migration `0026_assessor_comparisons` adds plan storage and preserves source
audits. Preparation requires a completed, usable source; a saved plan alone
does not establish accepted questions, successful upstream access or reliable
semantic verdicts. OpenRouter routing suffixes do not make latest/automatic
model aliases eligible for fixed-model experiments.


Assessor input binding (migration 0027): newly saved plans fingerprint the
source questions/settings, conversation/reference memories and relationships,
and original stored response rows. New reassessments include this binding in
their idempotency key and verify it before evaluation. A reference or answer
change returns 409 rather than invoking the judge against changed inputs.
Human review labels are not part of these frozen automated inputs.

Comparison payloads expose `inputs_match` independently of `runtime_matches`.
Plans predating input binding remain readable but are not backfilled with an
unobserved historical fingerprint. Their comparison chart and continuation
action are disabled until a newly verified plan is created. A binding is an
integrity check, not evidence that the reference itself is semantically correct.


Saved-answer input checks also run immediately before and after each judge
operation. Source rows are refreshed rather than trusted from an ORM identity
cache. Drift during a request rejects that result before persistence and stops
later questions; existing earlier assessments remain traceable. This does not
undo a request already sent to an upstream provider.

Judge receipts v2 add optional `reported_cost_credits`. Only finite, nonnegative
numeric `usage.cost` values from OpenRouter responses are retained. Missing,
invalid, negative, Boolean and nonfinite values remain unknown; an explicit zero
is retained. Scope is the last successful HTTP reply, including a reply whose
semantic output was invalid, not total retry billing or a dollar estimate. See
https://openrouter.ai/docs/cookbook/administration/usage-accounting for provider
field semantics. Historical receipt versions remain readable with unknown cost.


Assessor comparison entries include optional `observations`, computed only
from unique accepted tests with exact response/run bindings and strictly valid
receipts matching the requested assessor identity. Duplicate assessments, wrong
response bindings and malformed/mismatched receipts do not inflate totals.
`expected_answers` is the accepted-suite denominator; `timed_answers` excludes
operations with no HTTP attempt. `mean_elapsed_ms` includes retries and local
validation. `observed_cost_credits` and `observed_total_tokens` sum available
reported replies, not unreported attempts. Empty evidence stays null; an explicit
reported zero cost remains zero. Complete cost coverage requires every accepted
answer to have one attempt, no failed HTTP attempts and a reported finite cost.

The AI assessor page uses two aligned charts with separate time/credit units and
coverage captions. Fixed plan colours remain consistent with the pass-rate chart
even when another assessor has no result. This operational comparison does not
establish independent auditor accuracy or a complete provider invoice.


### Controlled test-generator comparisons

`POST /generator-comparisons` saves an idempotent plan with a completed
`source_run_id`, a `creation_request_key`, and two to five distinct `generators`
using `{provider, model}` selections. Concrete model names are required for AI
generators. Source target/assessor aliases, uncontrolled targets and structured
LLM memory writers are rejected: changing the generation pipeline must not also
change how the target constructs memory. The source audit supplies controls and
reference data; its historical result is not a baseline score for this study.

`POST /generator-comparisons/{id}/prepare` creates independent ordinary audit
runs while retaining common target settings, strategy, maintenance, capacity,
profile, seed, budget and assessor settings. Only the test-generation provider
and model vary. Each run is prepared durably, allowing partial preparation to
resume. Preparation makes no model call. Each variant uses the ordinary
generation/execution/evaluation endpoints; different generated questions must
not reuse original target answers or another generator's frozen suite.

`GET /generator-comparisons` and `GET /generator-comparisons/{id}` return saved
progress, input/software matching flags and per-variant saved-question checks.
No saved questions means unknown acceptance percentage, never zero validity.
The checks describe current saved questions, not independent validity or raw
initial candidate quality. Initial observations remain unknown for older runs; newly instrumented runs
expose local candidate/repair/leak flags separately from saved-suite checks. Source drift blocks preparation and new generation,
target calls and evaluation. Existing results remain readable. Migration 0028
adds plan storage without altering original audit results or human labels.

Batch UI supports prepared runs and saved-question inspection. Real-model controlled experiments and independent generation-quality validation
remain outstanding.


The Test generators page (`/generator-models`) now uses these saved plans.
Question generation and target execution are separate actions. Current saved
question acceptance and four-ability coverage are charted together by generator;
missing suites are labelled Not generated. The ordinary question review widget
provides saved question inspection, explicit review decisions and regeneration.
Completed/cancelled conditions cannot be restarted from the stage controls;
rejected-only suites cannot enable target calls. Navigation invalidates old
queues and late responses. Different question difficulty makes target pass-rate
changes insufficient evidence of generator superiority or memory improvement.

Conversation exports now include assessor/generator plan rows. The existing
explicitly confirmed conversation-erasure endpoint removes these derived plans
before source audit rows, satisfying their foreign keys without leaving private
plan metadata. No live deletion is part of system verification; automated erasure
checks use isolated synthetic SQLite/PostgreSQL fixtures only.


Generation observations v1: operations are durably recorded before generator
invocation. LLM candidate/schema/local-check observations are saved as they
arrive and before another automatic repair request. Returning or failing updates
that same operation rather than creating a duplicate history row. A process
interruption can leave an unfinished record with unknown dispatch/candidates;
it is not proof of a still-running request. Retrying preserves earlier operations.

Each operation records schema validity, returned candidate count, local-check
acceptance, answer-leak flags, whole-suite contract status, missing supported
coverage and automatic repair requests where observed. Malformed/unreturned
responses do not become zero-quality or zero-leak batches. The first recorded
operation supplies initial percentages only when its candidates are measurable.
Operation count is not underlying HTTP-attempt count. Timing includes generation
checks and observation persistence, not pure model latency. Raw failed provider
bodies and credentials are not stored in these observations.

Generator comparison pages now chart initial local checks and leak flags before
automatic repairs, alongside operation/repair counts and current saved-question
checks. These lexical/structural proxies are not independent validity labels.
New generator implementation is llm-structured-v8; historical runs are not
backfilled with observations. Actual provider access, generation billing and
independent reference comparisons remain separate verification requirements.


Pipeline HTTP receipts v1: PipelineLLMClient records request attempts at the
HTTP boundary, retryable/failed HTTP attempts, elapsed operation time, requested
provider/model and a reported response model/version identifier where supplied.
Only nonnegative integer provider token counts and finite nonnegative numeric
OpenRouter credit charges are retained. Missing/invalid values remain unknown.
Receipts survive invalid model-text parsing and are reset per invocation using
context-local counters. They do not store headers, prompts, raw provider bodies
or credentials. Failed HTTP-attempt usage is not inferred.

Generation attempt observations embed each returned client receipt, including
failed logical invocations; these differ from operation and automatic-repair
counts. Successful memory extraction records include the client receipt in
extraction provenance. Failed extraction has no durable comparison receipt yet;
its client observation is available to the planned isolated extraction runner.
These metering contracts do not replace independent quality labels or establish
complete provider billing.

Saved-answer reassessments also bind the copied question and answer rows with
`assessment_copy_signature`. Fresh reads check this destination receipt before
and after each judge call, as well as the original source binding. A mismatch
stops further scoring before persisting that call's verdict. Assessor comparison
`inputs_match` includes prepared copies, so changed or historically unverified
copies hide controlled comparison charts while preserving readable reports.
Historical reassessments without a copy receipt cannot resume scoring; create a
new comparison instead. Missing historical receipts are never backfilled as
verified. This is data integrity evidence, not proof of assessor accuracy.

Generator comparison entries expose `usage` derived from saved per-invocation
generation and semantic-review receipts. Aggregates include failed generations, automatic repairs and
operator retries, while target calls and assessor usage stay separate. Receipts
must match the saved provider/model for their agent role, meter version, terminal status and strict
finite nonnegative numeric fields. Duplicate operation identities are excluded.
Missing receipts or fields remain unknown, and explicit reported zero remains
zero. HTTP attempt/failure counts are observations, not generation operation
counts. Reported credits/tokens only cover the last successful reply of each
invocation, including an unparseable model reply when usage was supplied.
`complete_cost_coverage` requires all recorded invocations to have a single,
nonfailed HTTP attempt with reported cost and no unfinished operations. Even
this flag is coverage of saved operations, not an independent billing audit.
The generator page uses separate time, credits, call-count and token charts with
coverage labels; different units never share a numeric scale.

The local quality gate v19 rejects auditor-only memory row identifiers in a
question or expected answer. A real source identifier remains a legitimate
answer; the check does not reject it when it appears in the cited canonical
source fact. Structured generation v9 instructs models to put audit identifiers
only in supporting-memory metadata, and the existing automatic repair mechanism
receives this quality rejection. This does not establish independent semantic
validity: the check is a bounded structural safeguard.

Actual UI smoke execution (12 October 2026) used new synthetic Cedar history,
local Qwen 3:1.7B, a rule writer and a frozen four-question budget. A generator
plan included Rules, GPT 5.4, Claude Sonnet 4.6 and Gemini 3.1 Flash Lite. GPT 5.4
was listed but the configured service rejected its call; catalog presence is not
proof of routing availability. Claude and Gemini returned four-question suites.
A Claude question asking for hidden audit identifiers was rejected through the
UI before target execution. Rules and Gemini completed target evaluation;
missing/rejected suites were blocked. These are engineering smoke observations,
not independent human judgments or proof of a superior model. The historical
plan remains bound to its original software and cannot resume under updated
software. Single-question replacement usage still requires instrumentation;
the current usage aggregate covers saved suite-generation receipts only.

`/extraction-comparisons` creates a durable fixed-model plan from a completed
reference audit without making model calls. GET list/detail restores progress;
POST `/{comparison_id}/entries/{index}/extract` processes one unfinished model
condition under a plan lock. Candidate outputs live in the comparison record,
never replace confirmed conversation memories and never call the target model.
A frozen reference snapshot is exported with the plan. Per-operation intent is
committed before extraction; successful and failed calls retain supplied usage
receipts, and retries append rather than overwrite attempts. Source/software
drift blocks continued processing and mid-call changed inputs cannot produce a
valid saved output. Exact text/relationship match charts are local proxies,
not semantic accuracy, test quality or assessor correctness. Conversation export
and explicitly confirmed erasure include these new plans. Migration 0029 only
adds the isolated comparison table; it does not clear or backfill existing data.

The current concrete model shortcut is GPT-6.1 Sol, GPT-6 Luna, GPT-6 Astra and
Claude Opus 5.5, verified against official OpenRouter model listings on 12 October
2026. It fills selections only; a catalog listing does not confirm that the
configured key/provider can execute the model. Old model experiments remain
historical records; changing their saved model choices would invalidate controls.
The unfinished-submission page now explicitly identifies a previous saved
submission, explains that opening the page makes no extraction call, and scopes
failure text to that submission. Starting a new conversation clears the local
resume pointer and error while preserving server data; continuing may retry the
previous frozen extraction choice. Invalid relationship references are result
validation failures, distinct from authentication errors.
