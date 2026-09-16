# Development

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`; API documentation is at `http://localhost:8000/docs`.

## Hot reload

While Docker Compose is running, save a file under `frontend/src/` to update the browser automatically, or save a Python file under `backend/app/` to restart the FastAPI server automatically. The development containers use file polling to keep reload reliable with Docker Desktop. Changes to dependencies, `.env`, Compose configuration, or Alembic migrations require a Compose restart.

## Optional target AI providers

The configuration screen lists a local baseline and three external target providers. Add only the keys you intend to use to the root `.env`, then restart the backend:

```sh
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
GEMINI_API_KEY=...
```

The browser never receives these keys. `gpt-5.6-luna`, `deepseek-flash`, and `gemini-2.5-flash-lite` are selectable once their corresponding key is configured. Gemini's free tier requires a Google AI Studio API key and is subject to Google's applicable limits.

Provider execution uses a bounded retry policy for temporary network and service failures. Authentication, missing-model, and malformed-response errors are returned as clear API errors without exposing a credential or upstream response body.

## Quality checks and local end-to-end smoke coverage

The repository deliberately keeps its quality toolchain lightweight: TypeScript performs the frontend static check, Ruff prevents Python undefined/unused-code regressions, Vitest exercises UI components and the complete browser workflow in JSDOM, and pytest exercises the API and database contracts. Formatting conventions are defined in the root `.editorconfig`; no additional formatter or browser-driver download is required for normal development.

Run the same checks used by CI:

```sh
# from backend
sh scripts/check.sh

# from frontend (after npm install)
npm run check
```

From the repository root, `sh scripts/check.sh` runs all offline backend,
frontend and paper-artifact checks. Use `docker compose exec backend alembic
current` to inspect the development database migration revision. Alembic also
resolves the backend application path when run from `backend/`; the Compose
command is required on a host because the default database hostname `db` is a
Docker service name. The API rejects request bodies above
`MAX_REQUEST_BYTES` (5 MB by default); the conversation-import screen applies
a more conservative 1 MB client-side JSON limit to prevent accidental
oversized uploads.

The frontend workflow test follows the user-visible local path: authorised conversation → ground-truth acceptance → shared-suite generation and review → rule-based execution → results → target-memory trace. The matching backend API smoke test uses a temporary SQLite database and verifies the same rule-based path, including an explicit reject/regenerate/accept test-review cycle. These are offline tests: they never need provider credentials, Docker services, or a cloud model. They are intentionally complementary to a short manual Docker smoke check in a real browser when changing styling or file-upload behaviour.

GitHub Actions repeats backend static compilation and tests, upgrades a disposable PostgreSQL database through the complete Alembic chain, runs the paper-artifact generator contracts, and performs frontend type-check/build/tests on every push and pull request. The migration check gives early warning when a new revision is incompatible with a clean database. The workflow is in `.github/workflows/quality.yml`; `.editorconfig` defines the shared whitespace and indentation baseline.

Docker Compose applies `alembic upgrade head` before the backend starts, so the running application always uses the versioned database contract.

The frontend container uses `npm ci`, and `frontend/package.json` pins the tested dependency versions. Run `npm ci && npm run check` locally to reproduce the frontend CI contract. Backend `pytest.ini` sets its local import path, so both `pytest` and `sh scripts/check.sh` collect the same suite.

## Real-model experiment modes

The default `rule_based` pipeline, target and evaluator form a deterministic offline baseline. To use a cloud model for memory extraction and test generation, set `PIPELINE_PROVIDER` to `openai`, `deepseek`, or `gemini`; `PIPELINE_MODEL` is an optional override. To use an LLM-as-judge, set `EVALUATOR_PROVIDER` similarly; `EVALUATOR_MODEL` is optional.

The extraction, generation and evaluator modules use structured JSON and locally validate their schemas, source references, evidence references and test budget. A pipeline failure is reported rather than silently substituted, preserving experimental validity. The evaluator falls back to the deterministic judge only when its configured provider cannot return a valid decision, and labels that fallback in the stored result.

The controlled target's private memory writer is separate from the Auditor's ground-truth extractor. Leave `TARGET_MEMORY_WRITER=rule_based` for the deterministic baseline. Set it to `llm_structured` only when the run's frozen pipeline provider/model is a configured cloud provider. This environment setting is a **creation default only**: each `AuditRun` persists its selected writer kind and resolved writer version, and execution never consults a changed environment value. The writer sees only authorised source messages and its configuration is retained in the run response, reproducibility metadata and post-audit memory trace.

For controlled comparisons, keep provider, model, temperature, seed, test budget and prompt-template version unchanged between weak and strong runs. The audit also records the resolved pipeline and evaluator provider/model at creation, so later generation and evaluation use the same selections even if environment variables are changed. The target receives only private relevant memory context; evaluator-only expected behaviour is never sent to it or exposed by the tests API.

For research comparisons, use the Configuration page to select multiple target models, memory strategies, and optional repeated runs per condition. The application creates one Experiment Group, generates one canonical test suite, and clones it for every model × strategy × repetition row. This is required for a fair comparison when using an LLM test generator. The results page reports condition averages and standard deviation when at least two repetitions complete; a failed condition can be retried without rerunning completed calls.

## Local benchmark-compatible baselines

The repository does not include or download LongMemEval, LoCoMo or BEAM. After independently obtaining a permitted local source file, validate its structure at `POST /api/v1/research/benchmarks/{family}/validate`, where `{family}` is `longmemeval`, `locomo` or `beam`. Then run the controlled memory-policy baseline through `POST /api/v1/research/benchmarks/{family}/run` with that JSON payload, `source_authorised: true`, a selected `memory_strategy`, and a fixed seed. The same workflow is available in the **Experiments → Research Workspace** page. Each run is ephemeral: every case gets a new in-memory store, user messages are ingested chronologically, and no source content is saved to PostgreSQL.

These runners are intentionally deterministic and provider-free. They return a source SHA-256 fingerprint, runner/evaluator versions, case order, retrieval evidence, and category/dimension summaries. Their compact lexical reference-answer matcher is useful for repeatable integration and policy-ablation checks, but is **not** an official external evaluator. Do not call the resulting values official benchmark scores; record the upstream data licence/citation and any official evaluation method separately in the research protocol.

## Local LoCoMo- and BEAM-compatible baselines

The same caller-supplied, ephemeral boundary is available at `/api/v1/research/benchmarks/locomo/*` and `/api/v1/research/benchmarks/beam/*`. First call `validate`, then call `run` with the unchanged payload, `source_authorised: true`, a frozen memory strategy and seed. The adapters accept a practical common subset: `question`/`query`/`prompt`, `answer`/`expected`/`reference`, and a `messages`, `conversation`, `dialogue`, `turns`, `history`, or session list.

These are not official dataset loaders or evaluators. They never download, persist, or redistribute source records. Their deterministic outputs are appropriate for policy ablations and integration tests only, and must be labelled **local compatibility results** in reports. See [the frozen formal protocol](FORMAL_EXPERIMENT_PROTOCOL.md), [synthetic illustrative cases](SYNTHETIC_CASE_STUDIES.md), and use `scripts/generate_paper_artifacts.py INPUT_EXPORT.csv OUTPUT_DIRECTORY` to create deterministic overall, dimension-comparison and failure-distribution CSV/SVG artifacts plus a SHA-256 manifest. The bundled input under `datasets/paper-artifacts/` is synthetic illustration only, not an empirical result; generated figures are presentation only and make no significance claim.
