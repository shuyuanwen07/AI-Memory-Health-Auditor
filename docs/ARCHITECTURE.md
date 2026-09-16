# Architecture

AI Memory Health Auditor uses a browser → REST/JSON → FastAPI → PostgreSQL architecture. The browser never receives database credentials or provider credentials.

## Pipeline

1. A consented conversation is stored with its messages.
2. A configured `MemoryExtractor` derives reviewable memory candidates. `RuleBasedMemoryExtractor` is the deterministic baseline; `LLMMemoryExtractor` uses a provider-backed, schema-validated JSON contract.
3. The user confirms, edits, rejects, or adds the ground truth.
4. A configured `TestGenerator` creates tests from confirmed facts and their update/context relationships. Each generated test is quality-checked for confirmed evidence, grounding and answer leakage. Experiments can freeze a behavioural suite or either formal baseline (direct-ground-truth or fixed-template).
5. Before any target is executed, a researcher can inspect the frozen canonical suite, accept/reject a test or request regeneration. Canonical changes are copied to all peer runs so a model comparison remains paired and fair.
6. A controlled Target Memory Agent independently ingests the authorised conversation into a per-run persistent memory store. It records writes, UPDATE/CONFLICT/CONTEXTUAL_OVERRIDE lifecycle evidence and every retrieval. `TARGET_MEMORY_WRITER=rule_based` is the reproducible default; `llm_structured` uses the experiment's frozen pipeline provider/model to model an Agent deciding what to write, with the same strict source and relationship validation. `weak_first_hit` exposes only the first relevant record; `strong_rule_based` applies explicit contextual-override, update and supersession priorities; `strong_score_based` ranks relevance, freshness and context with transparent weights; `scope_aware` narrows current-task questions to project-requirement records and uses profile/preference records only for matching question intent. The evaluator-only expected behaviour and reviewer-confirmed ground truth are never sent to any target profile.
7. A configured `BehaviourEvaluator` compares responses with expected ground-truth behaviour. `LLMBehaviourEvaluator` uses strict JSON and evidence whitelisting, with a labelled deterministic fallback if the judge is unavailable.
8. `MetricsService` computes dimension scores and a macro-average overall score.

The four stages implement `MemoryExtractor`, `TestGenerator`, `TargetAIConnector`, and `BehaviourEvaluator` interfaces. External keys are read by the backend only; provider availability is exposed without revealing keys.

## Lifecycle

`CREATED → TESTS_GENERATED → TESTS_EXECUTED → COMPLETED`, with `FAILED` for a target or evaluator execution error.

The API validates each transition. Ground truth must be confirmed before an audit can be created. Audit records retain target provider/model, memory strategy, and resolved pipeline and evaluator provider/model, alongside temperature, seed, budget and prompt-template version.

## Experiment groups

An `Experiment` is the unit of fair comparison. It freezes one test-suite configuration and has multiple audit runs representing model × memory-strategy conditions. The first run creates the canonical suite exactly once. Peer runs clone that suite, retaining a link to each source test while storing independent target responses and evaluations. This prevents LLM test generation from changing the questions between compared conditions.

The experiment-history analytics service is read-only. It aggregates completed runs by provider/model/strategy, preserves incomplete conditions, and aligns pairwise outcomes through `suite_test_id`. It produces a downloadable CSV with condition summaries, individual run scorecards, failures and paired signals. The target agent's private memory and retrieval context remain excluded from these public reports.

The execution service is deliberately idempotent: generated tests, target responses and evaluations are durable artifacts. A retry begins at the first missing artifact, so a temporary provider failure does not repeat earlier successful requests.

## Research validity

Operational Memory Health scores evaluate the target Agent; they do not by themselves prove that the Auditor is correct. A separate human annotation protocol and de-identified seed set live in `datasets/annotation/`. The `AuditorValidityService` compares independently labelled PASS/FAIL outcomes with automated evaluations, reporting accuracy, failure precision/recall, false-positive rate and Cohen's kappa.

The research-validation router is deliberately separate from operational audit routes. It validates a frozen annotation release, calculates extraction, relationship, test-review and evaluator metrics from explicit prediction mappings, and returns a reproducible content hash. It retains no research payload. A LongMemEval-compatible adapter provides a local format boundary. Its optional deterministic runner operates only on caller-supplied, authorised payloads: each case receives an isolated in-memory target-memory simulation, sequential user-message ingestion, controlled policy retrieval and a transparent reference-overlap evaluator. It does not write benchmark payloads to PostgreSQL, download data, call an LLM, or claim an official external-benchmark result.
