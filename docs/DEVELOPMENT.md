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
3. Experiment A: compare direct ground-truth questions, a deterministic
   rule-generated fixed-template draft that a researcher reviews/edits/confirms,
   and contextual/indirect Auditor tests under equal budgets, with a manually
   labelled failure inventory and traceable outcomes.
4. Experiment B: compare predeclared Weak/Strong retrieval/update policies
   using the same base model, histories, storage and budget. Freeze repetitions
   and generation settings after the pilot; retain non-improving results.
5. Experiment C: compare Weak/Strong relative rankings under the Auditor and
   technically compatible LongMemEval evaluation with verified semantic
   outcomes. Lexical overlap is not official accuracy or ranking evidence.
   Auditor ranking uses the unrounded, equal-weight macro-average of all four
   measured dimensions. Missing dimensions make that ranking unmeasured.
   Under Experiments -> Research tools -> Does the benchmark agree?, repeated
   comparison packages can declare at least three planned trials. The analysis
   retains missing/invalid trials and exposes mean scores, sample variability,
   directional agreement and ties. Complete evidence is required for aggregate
   metrics. The uploaded plan is declared at analysis time; it is not a server
   pre-registration receipt. See `HUMAN_EVIDENCE_HANDOFF.txt` for the input format
   and the separate server-frozen plan API/UI and formal evidence
   requirements. Migration 0038 saves only frozen metadata and execution hashes;
   it does not retain benchmark source or full model responses.
6. Complete regression and manual GUI checks, then prepare simple comparative
   charts and source-backed failure demonstrations for the final report.

Broad vendor integration, model training, provider expansion and additional
benchmark families are not substitutes for these acceptance requirements.
Exploratory repair studies remain secondary to the proposal's A/B/C experiments.

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`; API documentation is at `http://localhost:8000/api/v1/docs`.

Browser API traffic defaults to `/api/v1` on the page origin. The Vite development server proxies only that route to the backend: Compose uses `AUDITOR_PROXY_TARGET=http://backend:8000`, while a host-run frontend defaults to `http://127.0.0.1:8000`. Browser Origin, cookies and CSRF headers remain intact. No failed write is automatically repeated. `VITE_API_URL` remains an explicit override for deployments with a separate API origin; an empty override uses the same-origin default. A production static deployment must route `/api/v1` through its own reverse proxy, because Vite development proxy configuration is not included in the compiled application.

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
format. Configure target, test-generation, semantic-review and evaluator models
independently in the audit screen. Extraction, generation and semantic review require an endpoint supporting JSON
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
Ollama is available for new extraction, test generation, semantic duplicate
review, target-answer and evaluator calls when the local service is reachable.

### Local Qwen 3 1.7B through Ollama

The audit configuration can use **Local Qwen 3 1.7B (Ollama)** separately for
test generation and semantic duplicate review, as well as extraction, target
answers and response assessment. Install Ollama and download the model on the
host:

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

For an isolated offline backend test run, use this entry point from the repository root (with backend dependencies installed):

```sh
python scripts/run_offline_backend_tests.py
# Optional focused selection; pytest arguments follow --
python scripts/run_offline_backend_tests.py -- -q tests/test_target_identity_evidence.py
# In the running development container:
docker compose exec backend python /scripts/run_offline_backend_tests.py
```

Plain `pytest` inherits the process's service configuration. In a container configured for OpenRouter, a test that omits an explicit provider or mock can therefore call the real service even when its database fixture is temporary SQLite. Do not label such a run offline merely because its test data is synthetic. The isolated entry point sets rule-based pipeline/evaluator defaults before collection, removes provider credential variables, selects a fresh temporary SQLite global database, and disables automatic global schema creation. Provider-specific tests can still install their own synthetic keys and mocks.

The entry point blocks external Python socket DNS/connect attempts in the pytest process, permits loopback and Unix sockets required by local tests, and saves the pytest exit status and blocked-attempt count in a unique `backend/.engineering-smoke/offline-tests/isolated-suite-*/isolation-evidence.json`. Use `--backend-root` or `--evidence-dir` when needed. This harness is not a security sandbox: child processes inherit the isolated defaults and stripped credentials but their sockets and native networking libraries are not instrumented by this plugin. Multiprocessing children do not restart the launcher. PostgreSQL-specific tests skip under this SQLite entry point; run the CI PostgreSQL check separately against a disposable database ending `_ci` or `_test`.

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

The default `rule_based` pipeline, target and evaluator form a deterministic offline baseline. To use a cloud or local model for memory extraction and test generation, set `PIPELINE_PROVIDER` to `openai`, `deepseek`, `gemini`, or `ollama`; `PIPELINE_MODEL` is an optional override. To use an LLM-as-judge, set `EVALUATOR_PROVIDER` similarly; `EVALUATOR_MODEL` is optional. The test-generation Agent and semantic duplicate reviewer can also be selected independently in the audit screen; their exact provider/model pair is frozen with the run. New controlled-memory audits also default to an AI retrieval Agent. Its local/cloud service and model can be selected independently; it receives the question and target-private memory records, never expected behaviour or reference-memory IDs. Large stores are reviewed in batches so lexical matching does not pre-filter records before the Agent sees them. The original fixed retrieval policies remain available as comparison conditions. Agent selection is recorded with per-question reasons and a safe provider-call receipt; a failed call is reported rather than replaced by a fixed policy.

The retrieval Agent reviews the target's private records in batches when a store exceeds one model request's input limit, then compares the retained candidates. Every eligible record is reviewed by the Agent; lexical matching does not pre-filter the candidate set. The configured memory-count and context-size limits are applied to its final selection.

The extraction, generation and evaluator modules use structured JSON and locally validate their schemas, source references, evidence references and test budget. A pipeline failure is reported rather than silently substituted, preserving experimental validity. The evaluator falls back to the deterministic judge only when its configured provider cannot return a valid decision, and labels that fallback in the stored result.

The controlled target's private memory writer is separate from the Auditor's ground-truth extractor. Leave `TARGET_MEMORY_WRITER=rule_based` for the deterministic baseline. Set it to `llm_structured` only when the run's frozen pipeline provider/model is a reachable Ollama service or configured cloud provider. This environment setting is a **creation default only**: each `AuditRun` persists its selected writer kind and resolved writer version, and execution never consults a changed environment value. The writer sees only authorised source messages and its configuration is retained in the run response, reproducibility metadata and post-audit memory trace.

For controlled comparisons, keep provider, model, temperature, seed, test budget and prompt-template version unchanged between weak and strong runs. The audit also records the resolved generation, semantic-review, retrieval-Agent and evaluator provider/model selections at creation, so later generation, retrieval and evaluation use the same choices even if environment variables are changed. The target receives only private relevant memory context; evaluator-only expected behaviour is never sent to it or exposed by the tests API.

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

The fast backend suite uses isolated SQLite fixtures and skips the dedicated
PostgreSQL checks. Run those against a fresh, migrated PostgreSQL 16 database:

```sh
docker compose -p mha-isolated-ci -f docker-compose.ci.yml up -d --wait postgres-ci
docker compose -p mha-isolated-ci -f docker-compose.ci.yml run --rm --build integration
docker compose -p mha-isolated-ci -f docker-compose.ci.yml down
```

This separate Compose project exposes no ports, mounts no application database
volume, reads no `.env`, and uses memory-backed disposable database storage.
The integration service first applies the entire Alembic migration chain and
checks model/migration drift, then checks benchmark-plan contracts and PostgreSQL metadata persistence, the API workflow, paired repair identity, timezone-aware revocable
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


### Experiment B deidentified research releases

`POST /api/v1/research/formal/research-matrix` accepts the same frozen formal
B request plus `source_release`, and requires `synthetic_data_confirmation=false`
and dataset `data_origin=deidentified_research`. See
`datasets/templates/research-source-permission-template.json` (intentionally
invalid until reviewed). The receipt binds the exact dataset fingerprint and
records permission scope, team reviewer, time, deidentification, research use,
operational storage and cloud processing. Without cloud permission only local
Ollama or rule conditions are accepted. Demo-only personal histories are rejected.

The research page shows a separate source permission upload and storage consent
for that origin. It requires formal B mode; it never silently labels a research
release as synthetic. Source histories are persisted as `deidentified`, and the
permission receipt is saved in the acceptance protocol/manifest and input
fingerprint. Restoring a plan retains this receipt; changing it invalidates
execution. The service does not independently authenticate consent or human
reviewer claims. Existing synthetic endpoints keep their original source gate.


### Experiment C execution plan UI

The research page now exposes BenchmarkExecutionPlan before repeated analysis.
The plan file is unread until source processing consent; persistence also needs
metadata permission. Freeze/read/find use the plan APIs, and each repeat invokes
the explicit planned execution endpoint. Original evidence stays in memory for
per-trial downloads (multiple completed repeats do not overwrite one another).
Permission revocation invalidates late reads/results. The server only stores
fingerprints/status, so users must save full evidence before navigating away.
The Find action retrieves up to 50 saved metadata plans without model calls.
A plan ID dispatches repeated analysis to its frozen-plan endpoint and the
report labels that provenance separately from caller-declared analysis.

### Research-file processing permission

In Research Workspace, confirm research-file processing before selecting annotation, prediction, pilot, development or permission files. Unchecking clears loaded material and invalidates pending file reads/previews. The annotation validation, validity report and pilot-analysis API wrappers now require an explicit strict boolean source_authorised:true; omission/false is rejected before analysis and truthy strings/numbers do not count. The front-end API helpers default to false and the workspace forwards the checked permission. This is separate from permission to save histories, dispatch models, or claim independent human provenance. Existing research source files do not need editing: the flag belongs to the outer request, so dataset/package fingerprints remain intact.


### OpenRouter peak-load capacity limits

A completion may fail with a capacity error even when HTTP status is200. The application now recognises the provider's peak-load maximum-usage rejection and preserves it as a failure, without blaming source data. `PIPELINE_MAX_OUTPUT_TOKENS` optionally caps OpenRouter extraction, relationship, memory-review, planning, question-writing and question-review output requests. Set an integer256–12000; empty preserves each role's existing budget. The effective limit is the smaller of the role budget and configured cap; roles without a budget use the cap. Ollama and other providers are unaffected. The example1800 is a tested diagnostic value, not a guaranteed service capacity limit.

Every receipt preserves the role's declared limit, configured cap and effective requested limit. The cap participates in the formal runtime signature: changing it invalidates an existing frozen formal experiment. Complete source evidence, test coverage, validation and bounded repair rules remain enforced. No automatic model/provider switch or capacity-envelope retry is introduced. An undersized cap may yield incomplete JSON and will not turn a failed stage into success. The live project's environment was not rewritten by the diagnostic trial; its1800override was scoped to the disposable smoke process only.


Target provider failures now retain safe request facts in a failed target_answerAgent execution. HTTP200completion errors remain errors; capacity messages advise retrying later or choosing a smaller target output budget in a new audit. Existing target configuration remains frozen. Do not alter saved settings to evade software/input guards: recovering an older partial audit requires its original software or a new audit. Failed calls carry no fabricated response. Already completed responses are retained.


### Validated current engineering configuration

On13October2026, the local backend.env pipeline output cap was set to1800after a0-stage-lock check. Only the backend was recreated; operational counts/schema matched before/after. This setting completed the exact approved8fact/4dimension v16fixture with2repetitions per policy, including all diagnosticcalls. It is not a guaranteed limit for larger conversations, longer diagnostics or future providercapacity. Keep truncated/invalid output failed; do not lower coverage or accept a partial response.

Model smoke outputs must be written to a mounted persistent path (for example/app/.engineering-smoke) and copied to docs/evidence, with SQLite/source archives, before any backend recreation. v15/tmpartifacts were lost at recreation; v16replaces them with durable strict-verification evidence. Never infer archival completeness from terminalpassalone.

### LongMemEval pilot grading and memory-loss diagnosis

Pilot data and reports live in ignored `experiments/` and `backend/.engineering-smoke/` directories. Keep source revision, file SHA256, complete histories, sample IDs, capacity and context/output limits in a protocol before execution. The19October follow-up uses50as the preserved original control and500as an explicit larger-capacity condition; changing capacity is an experimental intervention, not a code-only improvement claim.

`run_longmemeval_pilot.py` retains legacy custom grading for old frozen protocols. New protocols should set `upstream_evaluator_directory` to a local directory containing the pinned upstream `evaluate_qa.py`, MIT `LICENSE`, and `source-binding.json` with `revision` and `source_sha256`. The shared `longmemeval_grading.py` loader uses only the inspected string-template helper; the model remainsLuna and JSON output is an explicit adaptation. All category rules apply uniformly; preserve previous assessments when correcting a grader.

`diagnose_longmemeval_memory.py` performs zero-model-call private-input tracing, using benchmark annotations only after target preparation. `run_longmemeval_suite.py` executes every frozen member in isolated processes with at most3workers. `summarize_longmemeval_suite.py` checks source/model/reply correspondence; `reassess_longmemeval_upstream.py` regrades all saved replies under pinned task rubrics, preserving original labels. `replay_longmemeval_inputs.py` checks exact context/instruction/question fingerprints offline after code changes. These pilot utilities do not establish independent human labels or official full-benchmark scores.

### Conversation history and context repair (19 October 2026)

`TargetMemoryProfile.retain_assistant_history` opt-in wraps the private target writer, retaining one attributed, untrusted assistant turn per memory. It does not change the auditor's user-fact extraction, human ground truth, or inferred user relationships. Assistant records are episodic and count toward normal capacity. System/developer messages remain excluded. Missing flags default false so earlier saved configurations remain reproducible.

`retrieve_message_context` opt-in expands fixed Strong retrieval to available fragments sharing an already relevant source message, normalises English plurals for retrieval only, and ranks Strong records by policy priority then relevance divided by square-root rendered length. It does not revive unavailable memories or expand the Weak first-hit baseline. Delivery includes source observation times/IDs in chronological order; actual rendered metadata and text count toward the context budget. Agent retrieval also renders and charges this metadata, while its selection remains the Agent's own selection. These are configuration changes and require a new audit, not resuming a frozen old run under different software.

Both controls are available in the target configuration editor and survive saved browser settings. Local exploratory rerun evidence is under ignored `experiments/longmemeval-context-repair-budgeted-20261019/`; earlier diagnostic stages are preserved separately. Use the same 12 cases, model and budgets when comparing results. These inspected development cases are not held-out research evidence or full LongMemEval accuracy.

### Fresh LongMemEval evaluation (20 October 2026)

Frozen policyv13 was evaluated on30 new questions, twice, after excluding49 previously prepared/executed IDs and any history session overlap with their source histories. Quotas:5 knowledge-update,5 multi-session,5 assistant,3 preference,5 user,7 temporal; only3 preference histories met the strict independence requirement. Same Luna model,500 capacity setting,50 retrieval records,16000 rendered characters and512 output tokens. No implementation changes during evaluation.

Primary Strong results were20/30 and21/30; Weak0/30 in both passes. The first Strong pass includes one upstream empty-response failure; its conditional assessed accuracy was20/29. That technical case was retried once separately and remained automatically incorrect; original scores were retained. Among29 Strong cases graded in both passes,26 verdicts agreed (89.7%). Assistant questions were5/5 each pass; temporal questions3/7 each pass. The debugged12/12 result did not reproduce on fresh questions. Same-model automated grading has two possible preference discrepancies pending human review; no scores were changed. Small strata and shared backgrounds among some new cases limit inference.

Evidence is in ignored `experiments/longmemeval-fresh-20261020/RESULTS.txt`, `study-summary.json`, `study-results.csv`, and `input-equivalence-proof.json`. Offline verification matched121 successful receipts and the failed request's instruction/combined-input hashes, with no new model/network calls; maximum actual rendered context15998characters. Source/runtime/configuration remained frozen. Do not combine repeated answers as independent questions or present these exploratory scores as formal Experiment C acceptance or full LongMemEval accuracy.

### Temporal retrieval regression (20 October 2026)

Policy v15 / controlled adapter v7 add bounded temporal retrieval over stored records: query-relative date windows, compound-word matching, same-source and same-session context links, and information-weighted ranking within the existing rendered-character budget. Relative phrases are resolved against their own source timestamps as reference metadata, with explicit caution that a recollection date does not establish an event date. Personal event questions can use assistant text as a topical bridge to nearby user statements; that assistant text is excluded as event evidence unless the question asks to recall assistant history. Third-person questions do not trigger this personal-event filter. Expansion stays one hop and uses no benchmark answer annotations.

The same30 previously inspected questions were rerun twice at500 stored capacity /50 retrieved records /16000 rendered characters /512 output tokens, with the same Luna target and pinned automated rubric. Strong22/30 in both passes; temporal5/7 in both, versus the original fresh-study temporal3/7. Weak0/30 both. Three primary Strong attempts failed technically (music twice; one multi-session attempt); each received one separate bounded technical recovery, all unsuccessful. Original and recovery reports remain separate. The intermediate v14 trial and its regressions are preserved.

All seven temporal cases' annotated source records are present in final offline inputs. Garden planting and mesh/thermostat ordering pass both new rounds. Music evidence is restored, but visible-answer generation remains unreliable at512 tokens; a separate transport diagnostic observed HTTP200, finish reason length and485 of512 completion tokens used for reasoning. At1024, the response stopped normally but still declined a complete event ordering; this ungraded budget experiment does not replace primary outcomes. The museum reference depends on treating a recollection as an approximate visit date; the model abstains. Rachel's birth year/first-birthday wording and same-day post-question thermostat source remain dataset caveats.

Two original preference grading disputes were reviewed against source: the cashew-yogurt rejection contains a demonstrably invalid unsupported-claim rationale; the sweet-potato response has support but may overstate the user's burger-and-fries preference. No original automatic score was edited and these reviews are not independent human gold. Evidence is under ignored `experiments/longmemeval-temporal-repair-final-20261020/`; these are development regression results, not another held-out stability estimate or formal Experiment C acceptance.

### Music chronology and reasoning budget repair (21 October 2026)

Policy v17 / controlled adapter v9 / live benchmark v9 distinguish a qualified likely chronology from exact event dates. Contemporaneous recency claims may support an approximate sequence, but the response must visibly qualify any ordering link inferred from those claims. Bare mentions, recollections, conflicting dates and unresolved overlapping intervals still require uncertainty. A return from a long trip does not establish the date of every activity on that trip. The response format now preserves necessary uncertainty instead of requiring an unqualified factual answer.

New model-audit configurations default to2048 output tokens in both the API and editor, because reasoning can consume the same output allowance. Explicit existing512 settings remain512 and historical run profiles are preserved. Both Weak and Strong use2048 in the new regression; this is a declared budget change, so do not present its improvement as a matched512-budget result. Truncated empty replies now retain sanitized upstream status, finish reason, reported model, token usage and reasoning usage through persisted failure diagnostics. Successful responses also retain typed reasoning-token usage. The connector does not silently increase budgets or switch models.

The v16 diagnostic factorial isolates the two causes: old reader/512 had3 technical failures; old reader/2048 produced0/3 complete correct orders; revised reader/512 produced1/3 correct with2 technical failures; revised reader/2048 produced3/3 correct. A later v16 regression still gave one incomplete music sequence, and one synthetic answer omitted its approximation qualifier. Those failures are preserved and motivated v17; they are not replaced by later successes.

Final v17 development verification used the frozen same Luna model,500 memory capacity,50 retrieved records,16000 rendered characters and2048 output tokens. Music passed all5 planned occurrences (3 confirmations plus2 regression runs), with qualified full orders. Six independent synthetic guards passed both runs (12/12), including bare-mention uncertainty, overlapping intervals and recollection-date separation. The seven original temporal questions scored6/7 in each round; the museum date remains ambiguous and automatically incorrect. The additional multi-session question returned usable answers but remained semantically incorrect. These are inspected development cases and same-model automated checks, not new held-out accuracy, independent human gold or formal Experiment C acceptance.

Evidence: ignored `experiments/longmemeval-music-repair-20261021/` preserves the factorial and intermediate failures; `experiments/longmemeval-music-qualified-final-20261021/` contains the final source snapshot, protocols, response receipts, source review and offline input proof. Final outputs should be read with the source caveat that Brooklyn/Queen placements are plausible recency inferences, not uniquely proven event dates.


### Multi-session event counting repair (21 October 2026)

The remaining inspected wedding-count question did not lose its three main annotated event sources during writing, capacity retention or delivery. The prior v17 reader received them, but also received unresolved mentions of another cousin and a sister. The reference contains a spouse name absent from the complete source history. These conflicts must not be hidden by selecting only annotated answer sessions or by injecting the reference into memory.

Current-period phrases (this/current week, month and year) now trigger temporal retrieval and carry calendar ranges anchored to the question or source timestamp. Those ranges are reference metadata, not proof of event dates. Personal-event retrieval excludes assistant advice as attendance evidence while retaining relevant user statements, including ambiguous additional mentions. Generic question words no longer attract unrelated annual health records. In the inspected case, all main and ambiguous sources remain supplied; rendered context decreased from15416 to10023 characters without raising its16000-character limit.

The v18 exploratory trial is preserved under ignored `experiments/longmemeval-multisession-repair-20261021/`. Although its six independent synthetic counting cases passed twice, all five wedding answers introduced unsupported distinct-event counts or lower bounds. Different relationship labels and unidentified mentions were wrongly counted as additional events. This is a real grounding failure, separate from the reference ambiguity; a disclaimer about the exact total does not repair an unsupported lower bound. All35 target attempts and assessments completed, with exact offline input/source verification. The two eight-question rounds scored Strong7/8 and Weak0/8, including temporal7/7; the wedding question failed every occurrence. These results remain unmodified.

Policy v19 / controlled adapter v11 / live benchmark v11 add explicit identity checks before counting: a role and name in the same narrative may describe one occurrence; consistent named participants and distinctive details can link descriptions across sessions despite different relationship labels. Unknown sameness does not establish distinctness. A numeric lower bound requires mutually distinct, in-period events; unresolved identity or date mentions remain outside a guaranteed count. This remains model-based interpretation, not a deterministic event identity graph.


The subsequent v19 run also did not resolve the real case: its16 synthetic guard attempts passed their core source-grounded checks, but the five wedding attempts included two empty responses that exhausted all2048 tokens on reasoning, one visible truncated response, and two complete responses with remaining identity/date errors. An isolated4096-token three-answer diagnostic preserved exactly the same source, selected context and instruction fingerprints; more budget did not establish reliable grouping. Neither synthetic success nor absence of transport errors is sufficient to declare the wedding repair complete. Original failure receipts and automatic assessments remain under the separate ignored `longmemeval-multisession-qualified-final-20261021` and `longmemeval-multisession-budget-4096-20261021` directories.


Policy v20 / controlled adapter v12 / live benchmark v12 address fragmentation in the reader presentation. For counting questions only, consecutive selected fragments with identical complete source IDs and observation timestamps share one nested source group. Original record indices, global order and all other payload fields are preserved; multi-source fragments are not replicated. Only the outer stored JSON is decoded, and nested content remains untrusted evidence. If this representation is longer than the prior serialized memory section, the reader retains the original layout. Weak still receives only its original first selected record. Receipt record counts and context hashes describe the same selected records; instruction fingerprints bind the actual rendered representation.

The compact counting response format asks for an event list with known identity, place, period and attendance/uncertainty status before its supported subtotal. A source group is explicitly not an event: one message can contain multiple events and one event may span messages. Unknown identity or date mentions cannot increase a guaranteed lower bound. The103 related tests and Ruff passed after updating one obsolete pre-v17 response-format assertion; initial fixture/assertion failures remain recorded. The new real-case check starts with three4096-token responses, matched to the preceding budget diagnostic; selection equality is checked before calling the model. It is a presentation/prompt intervention, not a silent change to the application default2048 budget.


The v20 source-grouped pilot preserved the exact selected-record bytes and reduced the serialized memory packet from12334 to10729 characters (27 source groups,50 excerpts). Three4096-token target replies completed, but all still asserted an unsupported five-event subtotal and failed to bind the same-narrative named participants correctly. Source-aware engineering review therefore rejected the candidate; no broad regression was run for this version. `experiments/longmemeval-multisession-source-groups-20261021/` retains all three failures and the passed zero-call presentation/input proof. A subsequent counting-policy check separates basic time grounding from the ordering-only approximate-chronology guidance; the grouped evidence representation is held fixed to isolate that instruction change.


The v21 policy-only comparison held the nested packet byte-for-byte fixed. Two source reviews agreed that its first two replies gave a defensible non-exhaustive subtotal of two explicitly time-anchored occurrences, retaining other mentions as uncertain. Failing to assert a likely alias is conservative information use, not automatically a hallucination: the same-narrative linkage is strong but not a literal unique identity equation. The third reply included a reasonable recent-August/current-year inference but incorrectly labelled the subtotal confirmed without stating that assumption. All three original rubric verdicts remain false. This distinction prevents the reference answer from silently becoming the engineering source-grounding gate.

Policy v22 / controlled adapter v14 / live benchmark v14 add one generic calibration constraint: when period membership relies on qualitative recency or an unstated-year assumption, both the item and any subtotal containing it must be labelled inferred or conditional with that assumption. Explicit source-anchored relative dates such as last month retain their calendar grounding. The selected memory and grouped rendering remain unchanged. Final development verification uses an explicitly declared4096 output-token limit for both Weak and Strong; the application default remains2048. Earlier2048 failures and4096 diagnostic failures are retained separately.


Before any final live call, the generic-item condition was also corrected: attendance is required only for attendance questions; other counts use the question's own identity, status and period criteria. An additional independent active-projects guard checks this, while the original eight fixtures remain unchanged. The final protocol declares35 benchmark targets (three confirmations plus two eight-question Weak/Strong rounds) and18 synthetic guard targets (nine cases twice), all with4096 target output tokens. Pre-live preparation errors and the earlier eight-guard zero-call preparation are preserved separately; no live outcomes were overwritten. The final related unit suite remains106 passed with one existing Starlette deprecation warning, and static checks passed.


Final v22 observed development results: both eight-question rounds scored Strong7/8 and Weak0/8 under the pinned adapted automatic rubric. All seven temporal questions passed each round. The wedding question remained automatically incorrect in all five planned occurrences. Source-aware Agent reviews found all five replies safe and conservative: a supported subtotal of two explicitly time-anchored weddings, with other mentions unresolved and any added recent-August/current-year count explicitly conditional. This is improved source safety and calibration, not complete entity-resolution recall or official benchmark success. No unsupported reference spouse name was inserted, and unknown identity mentions were not silently merged or counted as additional events.

The nine synthetic counting cases scored17/18 automatically; the single retained failure concerned the wording of an unresolved-alias count range. Its actual reply explicitly contrasted two distinct lectures with the same lecture and avoided an unsupported lower bound. This possible grading/presentation discrepancy is documented separately, not used to replace the original score. Both active-project checks correctly counted two without imposing attendance. All cases here are inspected development regressions or synthetic engineering checks, not new held-out evidence, independent human gold or formal Experiment C acceptance. Final evidence is under ignored `experiments/longmemeval-multisession-calibrated-final-20261021/`; every earlier failed stage remains in its own directory.


Final offline verification passed: all35 main target/assessment receipts matched reconstructed private inputs and grader fingerprints; all131 frozen app/script sources remained unchanged, with zero model or network calls during proof. The18 guard calls have their own frozen fixtures, receipts and result seal. Original scores, source ambiguity and grading/presentation disagreements remain visible rather than being replaced by source-aware review labels.


### Cross-session identity and contextual evidence repair (21 October 2026)

A further source audit distinguishes two failure locations. The roommate / Emily-and-Sarah / cousin Emily accounts already retained their names, city and rooftop details; their weak linkage was reader interpretation, not missing retrieval. A different contextual sentence describing Jen's venue as a countryside barn was genuinely omitted by the rule writer because it began with a pronoun and lacked its first-person memory signals. The two mentions of about50 guests concern different events (the roommate's past wedding and the user's future plans), so they must not be used as a matching fingerprint.

The v23 reader-only intervention introduced explicit, likely, possible and distinct identity levels while separating identity from date and attendance. Its three original-case confirmations all remained automatically incorrect and did not improve the important Emily linkage, despite safe conservative subtotals in all three. Its16 independent direct-reader guard attempts passed the automatic checks. Synthetic success did not justify claiming the original-case linkage repaired. All outputs and the exact unchanged50-record input proof are preserved under ignored `experiments/longmemeval-identity-link-20261021/`.

The subsequent v24 development intervention combines two changes: within-source role/name linkage before cross-source comparison, with explicitly conditional attendance inheritance; and a target-only contextual writer change. This is not a controlled estimate of either change alone. Unknown identity, year or participation cannot silently become a confirmed event count. New experiments must report changes to written, retained and retrieved records rather than claiming input equivalence to v23. Final results follow after the frozen rerun completes.


The v24 private `RuleBasedTargetMemoryWriter` leaves the shared Auditor extractor and default low-level store extractor unchanged. It adds bounded, attributed original source quotes only for omitted adjacent descriptive sentences; it does not resolve pronouns, rewrite identities, or infer relationships from those quotes. Questions, conditional/modal/planned claims, cross-message and cross-paragraph joins are excluded. Existing extracted fact IDs and relationships are preserved, and quoted records consume normal capacity and retrieval budgets. The110 related tests and Ruff passed before freezing.

The original-case zero-call preflight confirms that the omitted MSG-425 venue passes writing, active retention and actual retrieval. Written records change532→534 while retained500 and selected50 remain fixed. One selected contextual quote replaces the unrelated jewelry-organization statement from MSG-155. All original wedding identity, temporal and ambiguous-event evidence remains available. Context fingerprints change as declared; the old v23 reader rendered on the new context is separately fingerprinted rather than falsely claiming a matched-input reader-only comparison.


The v24 three-confirmation run restored usable venue evidence (one reply explicitly names the rustic barn), but did not reliably expose the full roommate / Emily-and-Sarah / cousin Emily identity chain. All three original rubric grades remained false. Source review accepts the first two conservative answers; the third retains a safe subtotal of two but adds a conditional four based only on years, without stating that unresolved identities must also be distinct. The initial all-safe review was corrected in an explicit erratum, preserving its original text. Neither source restoration nor conditional-year wording alone establishes complete identity/count safety. The v24 exact actual-input proof passed; no broader regression was run for this candidate.


The v24 identity guards retain an automatic15/16 result. The single false concerns incomplete pairwise relationship labels in a non-counting chain question; both replies avoided falsely confirming a transitive A–C link. That question's actual instruction/context fingerprints match v23, so its changed judgment is not evidence of the changed counting-policy input. Original scores and the separate safety interpretation remain available.

Policy v25 / controlled adapter v17 / live benchmark v17 require the counting response to show role/name identity links and uncertainties before filtering by year, followed by period/participation and a supported subtotal. Conditional numeric totals must state any assumed distinctness; a year assumption alone cannot justify adding possibly overlapping accounts. No private source selection or writer change is part of this stage. All111 related tests passed after updating two obsolete format-string assertions, whose original failures are retained. Final v25 checks bind the same v24 written/retained/selected inventory, ordered context and nested packet while recording a new reader instruction fingerprint.


The v25 forced three-section response candidate was rejected. All three rubric verdicts remained false; two replies omitted the supplied September/locket account, and no reply exposed the full intended likely identity chain. One reply also incorrectly attached meeting Alex to the wedding. The complete MSG-240 source attaches that pronoun to the preceding bachelor-party sentence, which the original writer had omitted. The selected fragment alone had lost that antecedent. This is a genuine source-context loss, not a justification to resolve pronouns from nearby wedding facts. The eight v25 guards repeated twice scored15/16 automatically, but independent review found a separate false-positive grade where an admitted attendance with unknown date was misread as no attendance evidence. All scores and source defects remain recorded; there is no blanket safety-pass claim.

The final v26 candidate reverts the forced three-section format while retaining explicit conditional-distinctness constraints. Private writer v2 preserves both directions of dropped adjacency: an omitted description after a retained sentence, and an omitted preceding sentence before an already retained pronoun-led statement. Quotes stay verbatim, same-message, source/time attributed, bounded and subject to ordinary capacity/retrieval; they never resolve a pronoun or create an identity relation. Both-retained pairs are not duplicated. Shared Auditor extraction remains unchanged. The actual MSG-240 writer check recovers the bachelor-party/Alex span, without including the earlier maid-of-honor sentence or rewriting what happened where.


Before final v26 live execution, all168 related tests and Ruff passed with no concurrent source edits. An earlier test invocation correctly rejected a benchmark execution while the writer was still being edited; that failure log is retained separately. The final frozen protocol runs three original-case confirmations, one same-eight-case Weak/Strong regression (sixteen target replies), and one eight-fixture identity guard pass. This single final regression is not stability evidence or new held-out accuracy.

The v26 zero-call full-pipeline gate confirms both the MSG-425 barn and MSG-240 bachelor-party/Alex quotes are written, retained and included in actual rendered target context. Relative to v24/v25, written records increase534→535, retained remain500 and selected remain50. The new selected antecedent quote replaces an unrelated generic statement about making future plans personal and meaningful (MSG-435). All changes and actual input fingerprints are recorded rather than implying unchanged inputs across this writer intervention.


Final v26 observed results: Strong6/8 and Weak0/8 in the single same-case regression; temporal questions6/7. The wedding question remained automatically incorrect in all four occurrences (three confirmations and one regression). Source review finds all four retain the September/locket event and do not introduce unsupported unconditional event counts. Two confirmation answers nevertheless unnecessarily downgrade Jen's source-anchored “last weekend” year and report a conservative subtotal of one instead of using both supported dated events. One answer shows a qualified partial roommate/cousin-Emily link, but none exposes the complete Emily/Sarah–roommate–cousin-Emily chain. Identity recall is therefore still unresolved. The new Alex antecedent is mechanically verified in the actual input; replies do not discuss Alex, so this does not prove the model now interprets it correctly.

The other regression failure is the previously disputed museum-duration case, where the answer declines to treat an observation/recollection date as the visit date; the automatic rubric remains false rather than being replaced by source-aware commentary. The final eight identity guards score7/8, with a real calibration defect: a likely A/B link was stated without its qualifier even though A/C was not hard-merged. This prevents an all-safety-passed claim. Prior automatic false positives and failed candidate phases remain preserved.

All19 main target/assessment inputs passed offline reconstruction, including both restored source quotes and all131 frozen app/script hashes; the eight guards have a separate completed-source proof and seal. There were no quality-driven reruns. This work repairs specific source-context omissions and preserves conservative uncertainty, but does not demonstrate complete cross-session identity reasoning, stable benchmark improvement, new held-out performance or formal research acceptance. Evidence is under ignored `experiments/longmemeval-identity-conservative-final-20261021/` and the preceding identity-link/context/ledger directories.


The final museum comparison was also completed without model calls: relative to v22, all435 canonical/source/lifecycle records and the selected50 records are unchanged, and the ordered context hash is identical (`d6781bf6…`). The relevant source messages remain supplied. Its automatic true→false change must therefore remain visible as observed performance variation/interpretation limits; it is not evidence of new writer information loss. Final main evidence is sealed in `v26-main19-artifact-seal.json`, with separate guard provenance.
