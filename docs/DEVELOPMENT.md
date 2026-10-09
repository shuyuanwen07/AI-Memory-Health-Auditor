# Development

## Current authorised scope — proposal prototype

The user confirmed on 2026-10-09 that subsequent development follows the
proposal and does not expand independent external-Agent integrations. Existing
optional adapters and historical evidence are retained; they are not required
for prototype acceptance and are not the next development priority.

The core target is one controlled memory-enabled AI: a fixed base LLM with
configurable external memory retrieval/update policies (proposal FR5, A2/A3,
C3 and sections 4.1/5.3). “External memory” means the target's memory store,
not a requirement to integrate an independently hosted commercial Agent.

Work proceeds in this order:

1. Verify the complete authorised-history, LLM extraction/test-generation,
   human-confirmed ground-truth and rules/semantic-evaluation workflow. Rules
   and AI pre-review do not replace independent human validation.
2. Calibrate extraction, relationships, question validity and failure
   detection/classification against genuine independent human labels; freeze
   pilot thresholds before inspecting held-out evaluation results.
3. Experiment A: compare direct ground-truth questions, fixed manually
   authored templates and contextual/indirect Auditor tests under equal
   budgets, with a manually labelled failure inventory and traceable outcomes.
4. Experiment B: compare predeclared Weak/Strong retrieval/update policies
   using the same base model, histories, storage and budget. Freeze repetitions
   and generation settings after the pilot; retain non-improving results.
5. Experiment C: compare Weak/Strong relative rankings under the Auditor and
   technically compatible LongMemEval evaluation with verified semantic
   outcomes. Lexical overlap is not official accuracy or ranking evidence.
6. Complete regression and manual GUI checks, then prepare simple comparative
   charts and source-backed failure demonstrations for the final report.

Broad vendor integration, model training, provider expansion and additional
benchmark families are not substitutes for these acceptance requirements.
Exploratory repair studies remain secondary to the proposal's A/B/C experiments.

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`; API documentation is at `http://localhost:8000/api/v1/docs`.

## Node.js version

Use `nvm use` in the repository root to select the committed Node `22.22.2`
version. The frontend package engine range matches the jsdom test runtime;
older Node 22 releases and Node 24 releases before 24.15 are not supported for
local checks.

## Hot reload

While Docker Compose is running, save a file under `frontend/src/` to update the browser automatically, or save a Python file under `backend/app/` to restart the FastAPI server automatically. The development containers use file polling to keep reload reliable with Docker Desktop. Changes to dependencies, `.env`, Compose configuration, or Alembic migrations require a Compose restart.

## OpenRouter model calls

New cloud calls use OpenRouter for target answers, memory extraction, test
creation, structured target-memory writing and LLM judging. Put the key only
in the root `.env`; Docker Compose passes it to the backend, not the browser:

```dotenv
OPENROUTER_API_KEY=your-key
OPENROUTER_DEFAULT_MODEL=google/gemini-2.5-flash-lite
PIPELINE_PROVIDER=openrouter
PIPELINE_MODEL=google/gemini-2.5-flash-lite
EVALUATOR_PROVIDER=openrouter
EVALUATOR_MODEL=google/gemini-2.5-flash-lite
# Optional upstream provider slug to pin a controlled experiment:
OPENROUTER_PROVIDER=
```

After changing `.env`, run `docker compose up -d backend` to recreate the
backend with its new environment. Model IDs use OpenRouter's `author/model`
format. Configure target, pipeline and evaluator models independently in the
audit screen. Extraction and judging require an endpoint supporting JSON
Schema output. Requests require parameter support and disable provider
fallbacks; a configured `OPENROUTER_PROVIDER` further restricts the upstream
provider. Missing keys and target/pipeline failures return readable errors.
The existing judge fallback remains explicitly labelled in results.

Default model: `google/gemini-2.5-flash-lite`. Select another explicit ID for
model comparisons; do not use an automatic model router in a frozen study.
See [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
and [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

For offline work, set `PIPELINE_PROVIDER=rule_based` and
`EVALUATOR_PROVIDER=rule_based`, then select the local rule-based target.
Legacy direct-provider and Ollama connectors remain for saved runs and
explicit API requests; they are not offered for new cloud audits in the UI.

### Local Qwen 3 1.7B through Ollama

Legacy API requests also support **Local Qwen 3 1.7B (Ollama)**.
It is target-only: extraction, test generation, and the evaluator retain their
existing rule-based or structured cloud-provider contracts. Install Ollama and
download the model on the host:

```sh
ollama pull qwen3:1.7b
ollama serve
```

For Docker Compose on macOS, keep `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
For a backend run directly on the host, use `http://127.0.0.1:11434` instead.
The provider chooser checks whether Ollama is reachable; no API key is required
or exposed to the browser. On an 8 GB Apple M1, start with the included
2048-token context and 120-token output limits, and use a 4-test audit for the
first real smoke run.

Provider execution uses a bounded retry policy for temporary network and service failures. Authentication, missing-model, and malformed-response errors are returned as clear API errors without exposing a credential or upstream response body.

Each AuditRun freezes `MAX_AUDIT_TARGET_CALLS` and
`MAX_AUDIT_EXECUTION_SECONDS` when it is created. During sequential target
execution or evaluation, `POST /api/v1/audits/{run_id}/cancel` requests a safe
stop between provider calls. The final lifecycle transition uses a conditional
database update, so a concurrent cancellation cannot be overwritten by a stale
executor. Completed responses/evaluations remain stored for traceability.
Cancellation is terminal; use a new audit or Experiment Group for a fresh
comparison. A persisted unfinished Experiment Group can also be cancelled from
the Experiments page after a browser refresh.

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

GitHub Actions repeats backend static compilation and tests, upgrades a disposable PostgreSQL database through the complete Alembic chain, runs `alembic check` to detect model/migration drift, runs the paper-artifact generator contracts, and performs frontend type-check/build/tests on every push and pull request. The workflow is in `.github/workflows/quality.yml`; `.editorconfig` defines the shared whitespace and indentation baseline.

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

## Unified React UI components

The frontend uses Ant Design through `src/components/ui/index.tsx`, with one `UIProvider` for theme and locale. Use these components for buttons, inputs, selects, checkboxes, uploads, cards, alerts, collapsible panels, progress and tables. Navigation and workflow steps use Ant Design Menu and Steps. Keep product-specific layout styles separate from component-library internals; do not reintroduce browser-native visible controls or `window.confirm`.

File selection runs the existing local parsing callback and prevents automatic Upload requests. Confirmation uses the Ant Design modal's awaited result. Dropdown tests interact with popup options instead of native select events. Integration coverage includes keyboard dismissal, form submission, numeric clearing, repeated file selection and cancellation confirmation. Recharts remains responsible for result visualizations.

## Disposable PostgreSQL integration checks

The fast backend suite uses isolated SQLite fixtures and skips the four dedicated
PostgreSQL checks. Run those against a fresh, migrated PostgreSQL 16 database:

```sh
docker compose -p mha-isolated-ci -f docker-compose.ci.yml up -d --wait postgres-ci
docker compose -p mha-isolated-ci -f docker-compose.ci.yml run --rm --build integration
docker compose -p mha-isolated-ci -f docker-compose.ci.yml down
```

This separate Compose project exposes no ports, mounts no application database
volume, reads no `.env`, and uses memory-backed disposable database storage.
The integration service first applies the entire Alembic migration chain and
then checks the API workflow, paired repair identity, timezone-aware revocable
operator sessions, and concurrent idempotent audit/experiment creation. Its
provider is the deterministic rule baseline; it makes no external model calls
and proves no semantic accuracy. Always run the cleanup command after success
or failure. Do not substitute the operational application's database URL.


### Development comparison within one model service

The ordinary New audit workflow accepts one deployed target model per line for each selected language-model service (up to eight unique names). The deterministic rule baseline retains its fixed identity. The interface previews the model × strategy × repetition run count and maximum answer requests before retries; preparation is limited to 64 conditions. Every condition receives the same reviewed source facts, frozen suite, target memory profile, temperature and seed. Model names appear explicitly in live progress and result labels. Names are deployment selections, not an assertion that the gateway guarantees identical model weights or deterministic outputs.

This development workflow does not bypass the independent-reference gates of the formal research matrix. Model comparisons must verify actual saved inputs and answer evidence, report retries and uncertain results, and distinguish AI pre-review from independent labels. A larger score in a small development history does not prove general model-size effects or auditor reliability.

Known output truncation is now retained in sanitized execution metadata (`completion_status`, whitelisted `finish_reason`). Explicit provider output-limit termination is excluded from both deterministic and model-judge accuracy scores, without calling another judge. Missing historical termination metadata remains unknown. Do not infer completeness from keyword presence or token count alone, or reuse the historical development Qwen4B 5/5 result as a model-scale conclusion: its saved answers are visibly incomplete. The regression evidence is retained in `output/multi-model-gui-v1`.
### Answer and update-context review

Diagnosis v8 separates a failed answer with supplied supporting facts and
exclusively missing superseded facts from a general memory-exclusion review.
It asks the operator to check the answer against the supplied newer fact and
whether the question required the older history. It does not assume historical
facts are unnecessary, claim a generation cause, or restore them automatically.
The condition uses the final input receipt and observed answer-time eligibility;
unknown copies, capacity exclusions and missing current facts cannot qualify.
The original target configuration remains unchanged.

Rule evaluator v34 binds an explicit assertion about an earlier database to
explicit past `used <database>` source assertions when those are present. A
database mentioned only in the current source is insufficient for that past
claim. It also abstains on database answers whose causal explanation cites a
programming language without a causal link in the supporting statements;
co-occurrence is insufficient. These are bounded rule guards, not a general
semantic entailment judge. Historical evaluations are retained unchanged.

The experiment list loads analytics only for the three visible groups, caches successful summaries and keeps individual result failures local to their cards. Failed summaries can be retried without refetching successful reports. The regression includes pagination, partial failure, retry and cached backward navigation; ignored stale-page responses cannot overwrite a later page.

Extractor v13 preserves common title abbreviations (`St.`, `Dr.`, `Mr.`, `Mrs.`, `Ms.`, `Prof.`, `Sr.`, `Jr.`) immediately followed by capitalised names when splitting source sentences. It retains the original substring and source-message attribution; ordinary terminal punctuation and newlines remain boundaries. This bounded English heuristic repairs an observed official temporal case, rather than establishing general extraction recall. Historical benchmark runs retain their original v12 writer metadata.

Generator v15 uses an answer-independent meeting question for explicit
“I met X on Y” facts. Quality validator v7 rejects generic “recorded stored
information” questions while preserving their source-grounding status. Source
confirmation alone does not make a question specific. Regenerated saved
questions retain their actual new generator/validator versions and require
review before model execution; historical accepted questions are not rewritten.

Frontend regressions use one worker, a bounded five-second asynchronous query
wait and a sixty-second whole-test limit on the shared development host.
Ordinary workflow mocks reset before each test. These settings preserve every
business assertion, do not change application waits, and do not constitute
performance acceptance. Failed prior runs remain in the evidence directory.

Proposal Experiment A method summaries distinguish completed answers from
recorded provider request attempts, including retries. Historical missing or
invalid attempt metadata remains unknown; offline rule targets record zero
provider attempts. Attempts without a saved response are outside this receipt
summary, so the display does not certify equal realised budgets. Distinct
finding counts still require resolved human labels and recall needs an
independently established failure inventory.
