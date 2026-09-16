# AI Memory Health Auditor

An ELEC5623 full-stack application for auditing how reliably a controlled conversational AI remembers and uses information over time.

It provides consented conversation intake, memory-ground-truth review, controlled weak/strong target configurations, behavioural tests, evidence-backed evaluation, Memory Health scorecards, audit history, and experiment summaries.

## Start

```sh
cp .env.example .env
docker compose up --build
```

Open the product at `http://localhost:5173` and the API contract at `http://localhost:8000/docs`.

## Development hot reload

Docker Compose mounts `frontend/` and `backend/` into their development containers. Changes to React code refresh the browser through Vite HMR; changes to FastAPI code restart the backend automatically. File polling is enabled so this also works reliably with Docker Desktop file sharing. Restart Compose only after changing dependencies, `.env`, Docker configuration, or database migrations.

The default workflow uses deterministic local rule-based implementations, so a complete controlled experiment can run without an external account or API key. For real-model experiments, the extractor, test generator, target connector and evaluator can independently use OpenAI, DeepSeek or Gemini through backend-only environment configuration. Every audit records its target, pipeline and evaluator identities for reproducibility.

Optional target-AI selections are available for OpenAI GPT-5.6 Luna, DeepSeek Flash, and Gemini 2.5 Flash-Lite. Put provider keys in `.env`; see [development instructions](docs/DEVELOPMENT.md).

For formal evaluation, the repository includes a versioned synthetic seed annotation set and a practical double-annotation procedure in [docs/ANNOTATION_PROTOCOL.md](docs/ANNOTATION_PROTOCOL.md). Real participant data should not be committed to the repository.

The **Experiments** page also contains a Research Workspace: permitted local LongMemEval-, LoCoMo- and BEAM-compatible JSON can be validated and run against the deterministic policy baseline; double-annotation pilot packages can be checked for coverage, adjudication and Cohen’s κ; and frozen human labels can be compared with Auditor predictions. Research uploads are request-scoped and never retained as audit history.

Conversation JSON import is lossless for supplied message IDs, roles, content, timestamps and source order. The Dashboard opens saved audit history; each completed run also has a durable `/audits/{run_id}` report URL, while saved experiment groups retain their comparison charts after refresh.

The optional benchmark runners use isolated in-memory target-memory simulations and return reproducibility metadata and retrieval evidence. They do not download, bundle, redistribute, or retain external benchmark data, and their results are **local compatibility results, not official benchmark scores**. Researchers must obtain each source lawfully and comply with its licence, citation, consent and privacy requirements. See [the API documentation](docs/API.md), [annotation protocol](docs/ANNOTATION_PROTOCOL.md), [formal experiment protocol](docs/FORMAL_EXPERIMENT_PROTOCOL.md) and [development guide](docs/DEVELOPMENT.md).
