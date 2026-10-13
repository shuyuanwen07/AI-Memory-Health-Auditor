# AI Memory Health Auditor

An ELEC5623 full-stack application for auditing how reliably a controlled conversational AI remembers and uses information over time.

It provides consented conversation intake, memory-ground-truth review, controlled weak/strong target configurations, behavioural tests, evidence-backed evaluation, Memory Health scorecards, audit history, and experiment summaries.

## Start

```sh
cp .env.example .env
docker compose up --build
```

Open the product at `http://localhost:5173` and the API contract at `http://localhost:8000/api/v1/docs`.

The browser and backend are bound to loopback; PostgreSQL is internal to the
Compose network. For the optional owner password gate, see
[workspace access](docs/ACCESS_CONTROL.md). This is a single-operator gate;
independent human reviewer identities and production security remain separate
validation requirements.

Real-model LongMemEval pilot comparisons are available under Experiments →
Research tools. See [live benchmark setup and score limits](docs/LIVE_BENCHMARKS.md).

With OpenRouter configured, **New audit** automatically prepares three methods:
rule tests + rule review, model tests + rule review, and model tests + hybrid
review. Confirm the shared facts, review the two question suites, then execute
all conditions. **Audit methods** restores saved three-colour comparisons.
The two model methods share questions and the same saved target answers; all three share confirmed facts and
target settings. These charts show target-answer pass rates, not auditor
accuracy. Independent labels are required to establish auditor reliability.
See the [architecture](docs/ARCHITECTURE.md) and
[formal experiment protocol](docs/FORMAL_EXPERIMENT_PROTOCOL.md).

## Assessment evidence and handoff

See [requirements and evidence](docs/REQUIREMENTS_TRACEABILITY.txt),
[the report draft](docs/A2_REPORT_DRAFT.txt), and
[the remaining human tasks](docs/HUMAN_EVIDENCE_HANDOFF.txt).
The research workspace guides proposal A/B/C and general repair validation.
Independent blind review offers a complete blank source-and-answer download.
Formal results and actual member contributions require human verification.

Create a clean source package with `python3 scripts/package_assessment_source.py`.
The package manifest records included-file hashes; it excludes local conversations,
credentials, databases and development outputs.

## Local Qwen setup

Qwen 3 1.7B through Ollama can be selected as the target AI, memory extractor,
test-generation Agent, semantic duplicate reviewer, or answer assessor. Install
Ollama on the host, then run:

```sh
ollama pull qwen3:1.7b
ollama serve
```

Keep these values in the root `.env` for Docker Compose on macOS:

```dotenv
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_DEFAULT_MODEL=qwen3:1.7b
```

No Qwen API key is required. Model requests go through the backend to the local
Ollama service; the browser only selects an installed model. Start with a small
four-test audit on an Apple M1 before increasing the test budget.

## Development hot reload

Docker Compose mounts `frontend/` and `backend/` into their development containers. Changes to React code refresh the browser through Vite HMR; changes to FastAPI code restart the backend automatically. File polling is enabled so this also works reliably with Docker Desktop file sharing. Restart Compose only after changing dependencies, `.env`, Docker configuration, or database migrations.

New cloud-model calls use **OpenRouter** for the target, memory extraction,
test generation and evaluator. Set `OPENROUTER_API_KEY` in the root `.env`
(backend only), then restart the backend. The default model is
`google/gemini-2.5-flash-lite`; target, pipeline and evaluator model IDs can be
configured independently. The audit screen prefers OpenRouter once its key is
configured. Historical direct-provider and Ollama runs remain readable.

For offline development, explicitly set `PIPELINE_PROVIDER=rule_based` and
`EVALUATOR_PROVIDER=rule_based`, and select the rule-based target. See
[development instructions](docs/DEVELOPMENT.md) for OpenRouter configuration.

For formal evaluation, the repository includes a versioned synthetic seed annotation set and a practical double-annotation procedure in [docs/ANNOTATION_PROTOCOL.md](docs/ANNOTATION_PROTOCOL.md). Real participant data should not be committed to the repository.

Owner A's [English handoff report](docs/OWNER_A_HANDOFF.md) documents a 20-scenario synthetic pilot with 325 completed AI-assisted label decisions. The [shared development package](handoff/owner-a/README.md) contains 12 scenarios, 195 filled labels, source evidence, decision records, annotation instructions and reproducibility checks. Eight held-out scenarios remain in a separate local custodian package for C after B's system freeze. Independent human double annotation remains pending; the AI review does not establish formal-evaluation readiness.

The **Experiments** page also contains a Research Workspace: permitted local LongMemEval-, LoCoMo- and BEAM-compatible JSON can be validated and run against the deterministic policy baseline; double-annotation pilot packages can be checked for coverage, adjudication and Cohen’s κ; and frozen human labels can be compared with Auditor predictions. Research uploads are request-scoped and never retained as audit history, except the explicit **Formal Synthetic Pilot Matrix** workflow: after a matching ready human double-annotation gate, it can materialise an authorised synthetic release into frozen, paired operational runs for target-model comparison.

Conversation JSON import is lossless for supplied message IDs, roles, content, timestamps and source order. The Dashboard opens saved audit history; each completed run also has a durable `/audits/{run_id}` report URL, while saved experiment groups retain their comparison charts after refresh.

The optional benchmark runners use isolated in-memory target-memory simulations and return reproducibility metadata, retrieval evidence, token-level F1 and measured case latency. They do not download, bundle, redistribute, or retain external benchmark data, and their results are **local compatibility results, not official benchmark scores**. Researchers must obtain each source lawfully and comply with its licence, citation, consent and privacy requirements. The research workspace also exposes `no_memory` and `full_context` reference ablations so strategy gains are not interpreted without baselines. See [the API documentation](docs/API.md), [annotation protocol](docs/ANNOTATION_PROTOCOL.md), [formal experiment protocol](docs/FORMAL_EXPERIMENT_PROTOCOL.md) and [development guide](docs/DEVELOPMENT.md).

## Before and after comparison

Open **Before & after** to select two completed audits, inspect dimension changes, and compare repaired failures, regressions and the saved answers on identical frozen questions. Each saved report also links to this comparison. Unrelated suites are not paired by prompt text; changes in model, evaluator and memory settings are flagged.

The AI-pre-reviewed synthetic repair pilot is frozen in `datasets/studies/repair-pilot-v1/study.json`. `scripts/run_repair_study.py --prepare` creates pending experiment groups; `--execute --split diagnostic --max-runs 20` runs the diagnosis phase, followed by `--execute --split held_out --max-runs 120` for the held-out phase. Run the script inside the backend environment with the repository mounted. It reuses saved responses, fingerprints the dataset and implementation, and exports results and a prioritised human-review queue into `output/repair-pilot-v1/`.

This pilot has **not** completed independent human annotation. AI pre-review is recorded explicitly; never present its labels as human ground truth or its offline policy smoke tests as model-performance evidence. Real execution requires the backend OpenRouter key. The plan uses two target-model sizes, five memory conditions, and three held-out repetitions. Generated results remain provisional until human review.

Native mature-product target preparation: see [comparison protocol](docs/MATURE_PRODUCT_COMPARISON.txt). The optional `mem0-demo` service uses pinned Mem0 OSS and local Ollama/Qdrant; native components and envelope tests are verified. Browser-driven matched-reader performance comparison remains pending.

## Independent human review (A, B and C)

Download or clone this repository, then open your assigned worksheet in a browser:

- A: `output/proposal-human-handoff-v2/A-review.html`
- B: `output/proposal-human-handoff-v2/B-review.html`
- C: `output/proposal-human-handoff-v2/C-review.html`

Each reviewer independently completes the same six source conversations, 32 audit responses and 21 benchmark pilot responses. No server, API key or model selection is needed. Follow `output/proposal-human-handoff-v2/START_HERE.txt`; do not discuss labels or view automated scores before submitting. Click **Export My Review** and return your final JSON file. The worksheets do not autosave: export before refreshing or closing, and export again after edits. These labels support development calibration, not independent held-out evaluation claims.
