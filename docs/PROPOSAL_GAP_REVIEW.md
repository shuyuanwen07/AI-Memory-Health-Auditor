# Proposal gap review — 7 October 2026

Read-only code review of the current Owner C checkout and existing ABC evidence. Code presence is not a claim of successful live execution. Existing business implementation and frozen C results are unchanged.

## Existing capabilities to reuse

| Capability | Code evidence | Remaining work |
| --- | --- | --- |
| Qwen3 target through Ollama | app/target_ai/providers.py | Start services, verify model availability and actual inference; record model/runtime identity. |
| Persistent target memory, independent source ingestion | app/target_systems/controlled.py; app/memory_agent/store.py | Run through the normal audit execution path rather than the source-only C engineering script. |
| Weak/Strong and reference strategies | memory_agent/store.py; schemas/domain.py; NewAudit.tsx | Select and freeze conditions; do not develop another memory layer merely to run the comparison. |
| LLM extraction, generation and judging | extraction/factory.py; test_generator/factory.py; evaluator/factory.py | Configure and validate a supported cloud provider, or deliberately implement local structured pipeline support. Ollama is currently target-only. |
| Confirmed-ground-truth generation and quality review | api/routes.py generate; test_generator/quality.py | Import the reviewed reference correctly, review generated questions and preserve four-dimension coverage. |
| Three suite modes | test_generator/baselines.py; NewAudit.tsx | Rule-based behavioural and fixed-template share the same generation implementation, so using both does not establish a distinct proposed GenAI method. Freeze genuinely distinct conditions. |
| Shared suite and per-condition runs | api/routes.py; formal_matrix.py | Use existing paired test IDs and settings. Formal matrix copies an existing gold suite rather than generate the three methods. |
| Repeat and paired analysis | services/experiment_analytics.py; ExperimentStatistics.tsx | Collect actual comparable runs and use existing mean/SD, delta, bootstrap interval and sign-test output. |
| Annotation, validity and calibration metrics | research/validity.py; research/pilot.py; evaluator/calibration.py | Supply genuine reference/prediction mappings and record actual provenance; successful gates are not established by code alone. |
| Benchmark-compatible upload and deterministic runner | benchmarks/longmemeval.py; benchmarks/runner.py | Existing runner explicitly does not call an LLM. It cannot by itself establish Qwen Weak/Strong external ranking agreement. |

## Actual narrow implementation/integration gaps

1. LongMemEval evaluation needs a compatible path measuring the same Qwen-plus-memory conditions as the Auditor, lawful source data, scorer/mapping decisions and ranking comparison. Reuse adapters; do not equate local deterministic compatibility scores with model benchmark results.
2. Experiment A needs distinct direct, fixed-template and proposed personalised/GenAI methods. Existing rule behavioural equals the fixed-template implementation apart from version metadata. Configure the existing LLM generator or revise the experimental design explicitly.
3. Distinct failure discovery rate requires stable failure-unit identifiers/mapping across different suites; category coverage and external ranking agreement need a declared report calculation. No dedicated implementation was found by scoped source search; existing counts/exports can be reused rather than build an entire new framework.
4. The Formal Synthetic Matrix import loops over all supplied gold_tests and stores them as accepted. The current A release includes rejected candidates. Freeze an execution-only accepted-test release (preserving rejected candidates separately for validity analysis), or implement explicit reject filtering. Never import the unfiltered A candidate release as an executable accepted suite.
5. Success thresholds, repetitions and final study choices remain protocol/data decisions. The protocol file is a template, not evidence of a completed preregistered freeze. Its measured-dimension macro-average is a prototype reporting policy; the proposal's four-dimension overall score requires actual four-dimension coverage.

## Revised owner sequence

A: finalise a versioned reviewed ground-truth release, accepted execution suite, separate rejected-review inventory, accurate provenance and data custody. Decide whether fresh formal holdout is needed before B sees/tunes against old heldout findings.

B: reuse Qwen connector and persistent adapter; validate runtime, isolate retrieval-policy effects, configure existing LLM stages as required, freeze three genuinely distinct equal-budget methods and a shared Weak/Strong suite. Complete development pilot and thresholds. Prepare same-model benchmark integration; record unsupported seed guarantees and repeated-run choices. Freeze a new revision if implementation changes are required.

C: verify freeze and unused formal holdout, execute operational-path experiments, explicitly map extraction/relationship predictions to references, label actual outputs, apply existing metrics/analytics and supplement missing discovery/coverage/ranking calculations. Report exclusions, all four dimensions, success-threshold outcomes and limitations. Preserve prior nine-test run as engineering evidence.

## Current environment observations

.env selects Qwen3:1.7b for the Ollama model, while extraction/generation and judging default to rule_based. The supported cloud-provider key entries are empty or absent; no credentials were printed. Previous live probes could not connect to local Ollama/backend. This review did not start services, install software, run new inference or retune the system.
