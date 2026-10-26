# Synthetic engineering evidence

These artifacts contain explicitly approved synthetic engineering facts,
real local Ollama outputs, and labelled read-only API probes with missing data.
They are not independent human labels, research gold,
participant data, held-out results or completed audit results.

The source fixture and smoke approval are bound by SHA-256 in
`../../datasets/smoke/qwen-four-dimension-approval-v1.json`. The approved memory
values are copied verbatim from the source, with aliases M001–M008 used only for
the isolated runner. Its three edges are SYN103 UPDATE SYN102,
SYN105 CONTEXTUAL_OVERRIDE SYN104, and SYN106 CONFLICT SYN107.

Reproduce generation and review with the installed local `qwen3:1.7b` model:

```sh
docker compose exec -T backend python /scripts/smoke_qwen_generation.py --output /tmp/qwen-generation-smoke.json
```

A failed smoke exits with status 1 and still writes its complete report. It
does not connect to or write the audit database. The runner uses Ollama
explicitly and does not download a model or switch to a cloud provider.
Current runner executions also record the local model inventory before dispatch.
The output preserves configured/reported model receipts, prompt fingerprints,
structured candidate outputs, local rejection reasons and bounded retries.

| Artifact | Actual outcome | SHA-256 |
|---|---|---|
| `qwen-generation-v10-scoped-2026-10-13.json` | Failed: Conflict Resolution slot unfilled after three repairs; no partial suite saved. | `d3b99a5603aeb1cc5e192f670b47cdc79da1e4be680aec3cf1a4fc4813813d8a` |
| `qwen-generation-v11-scoped-2026-10-13.json` | Failed: Accuracy and Appropriate Use slots unfilled after three repairs; no partial suite saved. | `3de069c7dc137a5f3dd085f1d51a4bc5489d935e89ce2f6ea2580ee3d9eb99a9` |
| `qwen-generation-v12-scoped-2026-10-13.json` | Failed: Appropriate Use unfilled after three repairs under the strengthened region-leakage gate. | `bd104b37dd8f57c45c4d1eb3225712886952210b8b904f158cabb976220ccac8` |
| `qwen-generation-v13-scoped-2026-10-13.json` | Failed: Appropriate Use still unfilled after candidate-specific feedback and three repairs. | `0c03ec72a285743f719458913c65ca0f6fd5334cf0bbf8dcdb241ea1fc03a832` |
| `qwen-inventory-after-smokes-2026-10-13.json` | Local inventory observed after the two smokes; does not retroactively bind a digest to a request. | See file. |

None of these generation trials reached semantic review, target answering or
answer evaluation. The latest quality gate also rejects the North/South answer leakage
that the earlier v11 local check missed. Preserve those failed outputs; do not
report a passed complete Qwen workflow from these artifacts. Trials v12 and v13
include local inventory captured before dispatch. Different prompt versions
must not be pooled as a formal repeated experiment. Generator calls use
temperature 0; the current pipeline client does not send a random seed to
Ollama, so the nominal seed in the smoke AuditRun is not evidence of controlled
provider randomness.

## Experiment C missing-evidence API probe

`experiment-c-repeated-missing-evidence-2026-10-13.json` is the actual local
read-only API response to
`../../datasets/smoke/experiment-c-repeated-input-template.json`. HTTP 200
returned a partial report with all three planned trials missing, no suite
scores and a null ranking-agreement rate. The template and response contain no
benchmark source, model replies or labels and triggered no model inference or
audit record creation. This verifies missing-data handling only; it is not a
completed Experiment C trial or a benchmark result.

## Extraction format recovery

`openrouter-extraction-v11-smoke-2026-10-13.json` records an actual in-memory
OpenRouter `openai/gpt-6-luna` call with one synthetic user message stating
Meadow's current production database is PostgreSQL. Extraction, relationship
analysis and independent review completed. No user conversation was replayed
and no database records were created. This small engineering check does not
establish correctness on the saved failing conversation or research accuracy.
Its first extraction response passed; automatic format repair is covered by
mocked contract tests, not exercised by this live call.

Extractor v11 allows exactly one format-correction attempt after Pydantic
validation failure. Both attempts retain separate traces; only safe field paths
and error types are fed back, with the original authorised source. Transport
failures and invalid evidence references are not retried by this repair loop.
Verification: 57 tests passed across `test_llm_pipeline.py`,
`test_memory_review_diagnostics.py` and `test_pipeline_http_receipts.py`; Ruff
passed for the changed extraction source and tests.


## Qwen generation v14–v16: scoped override and semantic repair

All three used the same approved synthetic Maple release and local
`qwen3:1.7b`; none reached target answering/evaluation or wrote operational
records. Model inventory was observed before dispatch. Different prompt and
validator versions are engineering trials, not repeated formal study conditions.

| File | Actual outcome | SHA-256 |
| --- | --- | --- |
| `qwen-generation-v14-scoped-2026-10-13.json` | Failed: answer leakage was removed, but backend-language wording hit a deterministic topic mismatch. | `c7188fe1604edb29ffe96973903d9a5bd9e975baaf2ce5d49bb691627d94a054` |
| `qwen-generation-v15-scoped-2026-10-13.json` | Initial four slots passed local quality; semantic review flagged them, and batched semantic repair changed a frozen dimension/evidence contract. | `5b612479795fe2eb205ae87009917722312c9067f07ff4cf3c5ae81a9a7f0044` |
| `qwen-generation-v16-scoped-2026-10-13.json` | Single-slot semantic repairs kept structure; subsequent conflict repairs still put hidden memory IDs in the reference answer. Bounded repairs exhausted; no partial suite saved. | `fcbba3623fd09ec46d52fc499bd930edcfc068e14dd1aea0db44c2b810c54f25` |

The reviewer also flagged neutral Accuracy wording as unclear and confused
some relation semantics in v15. These findings were preserved, not treated as
independent human judgments or silently discarded. They motivate inspecting the
semantic review/repair handoff before declaring a complete Qwen workflow.

## User-authorized GPT 6 Luna migration (2026-10-13)

The user explicitly superseded the earlier local-Qwen-only instruction for future model calls. New configured extraction, planning, writing, reviewing, target answering, and judging use OpenRouter `openai/gpt-6-luna`. The running backend was recreated and its nonsecret configured identities verified. New benchmark UI defaults and plan templates use the same model. Historical frozen experiments and explicit legacy provider choices remain readable; rule comparison arms and mechanical checks remain part of the experiment design. The native Mem0 pilot is still a separately selected local-Qwen-only integration and was not migrated or dispatched.

Actual approved synthetic Maple generation (Agent v20 / writer v18 / reviewer v8) completed four dimensions. One semantic quality repair was followed by a clear final review. This is engineering evidence, not independent human research evidence. Target and judge smoke supplied all eight approved memories in full context; it is not a Weak/Strong comparison or an official benchmark. All four target replies completed; all four judge requests returned valid contract data without fallback. Accuracy is decided positive. Freshness, Conflict Resolution and Appropriate Use retain null verdicts because the model judge and deterministic cross-check disagree. No audit database writes occurred. This does not establish formal research completion.

Verification: 32 backend provider/default/live-benchmark tests passed; 47 relevant interface tests passed; interface typecheck passed. The previous selected pipeline/generation regression run passed 142 tests.

Retained Qwen v17/v18/v19 runs failed; the isolated thinking probe succeeded, but no complete Qwen target/evaluation run was produced. A passive clarification false rejection was fixed in quality v23 after v19. Those failed receipts remain available and are not relabelled as passed.

- `luna-generation-v20-2026-10-13.json` SHA256 `8ba0217606374d2f8c102e333280827825af1ffdad29e8e11674ff7c5eaf09e3`

- `luna-target-judge-2026-10-13.json` SHA256 `b4f3908b0352abf14fbf40f135e65abe2ea060ac951f03258a3d2f84835ebb4f`

## Evaluator and Experiment B controls follow-up (2026-10-13)

Rule evaluator v58 selects explicit current database values, recognizes user clarification of controlling constraints, checks separately scoped task/general language values, and recognizes source-derived deployment alternatives without demanding the literal word “conflict”. It still rejects denied clarification, missing alternatives, reversed task language scope, and choosing an unresolved region while asking for clarification. The database replacement check requires the earlier value when the question asks for replacement.

The first new v57 Luna target/judge trial yielded three decided positive cases and one conflict disagreement: its answer explicitly contrasted North/South and asked which controlled but lacked a literal conflict keyword. The exact four saved replies were then reassessed with actual Luna judge calls and v58 local cross-check, without replaying target requests. All four are decided positive; this is approved synthetic full-context engineering evidence, not a formal Weak/Strong run, independent gold, or an external benchmark score. Original v56/v57 disagreement files are retained unchanged.

Experiment B new matrices are v9, with protocol v2 and reader_control=fixed_strong_reader. Every strategy uses the same Strong reader. Restore, direct frozen-input/execution/acceptance guards, saved-run validity and condition-summary checks protect that control. Historical protocols retain absent control as None; their records/results remain preserved and cannot gain formal B certification from schema defaults. The settled focused formal regression passed 114 tests.

Saved intake now offers an explicit switch to the current OpenRouter model (GPT 6 Luna). Switching changes the next extractor selection only, sends no request, and preserves the exact saved source, request identity and acknowledged conversation ID. Continue resumes that conversation; completed extraction is still read without redispatch, and already-used conversations retain the existing audit guard. Five focused intake/recovery UI tests passed, with 26 unrelated tests excluded by the name filter; TypeScript passed.

- `luna-target-judge-v57-2026-10-13.json` SHA256 `3caec06017d587eab555ebf0670b0c850d67a2ed2c9a85f9964c332e85e626c1`

- `luna-reassessment-v58-2026-10-13.json` SHA256 `18f9e12fa300b09e2c618516f9c6127f91713c1bc7a0dcddd4e6660244c107f1`

Settled combined evaluator/formal-study verification: **400 backend tests passed**, one existing Starlette/AnyIO deprecation warning, 111.96 seconds. Ruff checks for changed backend files and final diff check passed. No live database records were changed by these tests or smokes.

## Intake recovery and entry-page verification (2026-10-13)

Historical Ollama submissions were incorrectly rejected by the browser checkpoint reader even though the application supports local models. The reader now accepts a nonblank local model identity while preserving the original source, source origin, message IDs/timestamps, request key and acknowledged conversation ID. Explicit Luna-switch recovery is covered for both cloud and local saved submissions. Existing completed-extraction and audit-use guards remain active.

The current running entry page was inspected at default desktop size and 390×844. OpenRouter GPT 6 Luna is visibly selected, and consent-dependent import/Continue controls remain disabled until authorization. The catalog/status text had no layout spacing; a small grid layout now separates those messages and the selected-model check button. Screenshots are synthetic/default entry data only; no source was submitted and no availability inference was requested in this visual check. This checks the entry screen, not full-screen acceptance or novice usability. Temporary viewport override was reset and the inspection tab closed.

Focused model-picker/checkpoint tests: 9 passed. The preceding recovery-selected run: 9 passed, 25 unrelated tests excluded by name filter. Production build and TypeScript passed; the existing large main-chunk advisory remains.

- `luna-default-new-audit-desktop-2026-10-13.jpg` SHA256 `6d1bdcd916f5546a06f96201adc70d7d8c8e2c41bc89fb77a2ef25a6fc0afac1`

- `luna-default-new-audit-narrow-2026-10-13.jpg` SHA256 `6f287daa94d5e97b62a4ce5fa99aa8848e3e2002ed3ee28a5889f9c55abeb483`

## Isolated API smoke: preserved incomplete attempts (2026-10-13)

`smoke_luna_isolated_api.py` creates a new temporary SQLite database before importing the application; it sends real API requests and actual OpenRouter Luna calls. Source bytes and prior user approval are SHA-bound. Engineering confirmation rejects model candidates and adds only the exact eight previously approved synthetic statements/three edges through supported routes. This reuses prior approval; it is not new human research annotation.

Attempt v1 completed extraction, relationship analysis and independent memory review, all reporting Luna; the harness then misparsed a successful empty HTTP204 response. That failure is preserved rather than relabelled. Attempt v2 corrected empty-body parsing and completed the Weak policy's own-history controlled-store generation, four target answers, blind model assessment and results. Its score was25.0, 1/4 positive, with0uncertain/excluded decisions. It then stopped on an actual diagnostic Agent HTTP502 before the Strong condition. Therefore v2 is incomplete, not a successful paired comparison or full pipeline. Temporary SQLite cleanup occurred; actual diagnosis failure details remain limited because the first harness did not fetch the failed Agent receipt before teardown.

Attempt v3 has been launched with explicit diagnostic failure retention, failed-Agent receipt collection and independent Strong continuation. Its final status is not yet established here. Inspect the live process or final receipts before deciding the next action; do not restart on an observation timeout. Original operational database records are untouched.

- `luna-isolated-api-e2e-v1-2026-10-13.json` SHA256 `898a3189672d5ed7c5992a2d315ba8dce490e053ee474c158d73c204502a11a2`

- `luna-isolated-api-e2e-v2-2026-10-13.json` SHA256 `09dcbd9d423156283948a77cc0d6539d5c4bb013ab4b41d98a0c678d501af84d`

## Completed isolated API pair and remaining release evidence (2026-10-13)

Attempt v4 preregistered both runs before the shared suite froze. Actual Luna extraction, relationship analysis, independent memory review, four-dimension planning/generation/review, eight controlled-store target replies, blind assessments and both diagnostic v2 syntheses completed. The supported API result/JSON bundle/CSV identities, answer text, scores and dimension denominators reconcile. Target store IDs are disjoint from approved auditor IDs and retain original source references; source inspection separately confirmed target ingestion receives original conversation history. This is observational delivery evidence, not proof of provider attention.

Weak:1/2 decided answers positive,2pending,overall50.0 and formal overall null. Strong:3/4positive,0pending,overall/formal75.0; Conflict Resolution is a failure. These are one-repeat approved-synthetic engineering results, not formal Experiment B or independent evidence of strategy superiority. The full instruction hash includes memory JSON and differs between inputs; verification reconstructs each full hash and compares only the reader-policy suffix. The Maple pair had identical policy suffixes.

All8 historical judge receipts had configured Luna but missing provider-reported identities. They remain unknown. The verifier was corrected to report judge_actual_model_verified=false rather than incorrectly importing the target’s identity. After this v4 record, the evaluator now saves sanitized model/modelVersion identifiers when actually returned (judge meter v3); a real diagnostic-free saved-answer probe returned reported_model=openai/gpt-6-luna with a valid judgment. No target request or historical result was rewritten by that probe.

The Strong reader’s previous conditional extra guidance depended on retrieved context. After v4 it now always includes the same conditionally phrased conflict guidance, so retrieval changes only evidence JSON rather than which policy text is added.119 selected backend judge/provider/formal-design checks passed on settled code. This latest reader/metadata delta has not yet been rerun through a fresh full API pair; v4 proves the earlier frozen runtime only.

Diagnostic v2 increases its finite output allowance to4096–12000tokens. The exact saved synthetic input failed at1200(noJSON,1200reportedoutputtokens) and completed at4096(1406reportedoutputtokens). Shared pipeline receipts now record requested limits and safe finish reasons, reject reported length even if text parses, and preserve that metadata in Agent traces.78 selected diagnostic/pipeline/trace tests passed. Old diagnostic failures remain retained.

Temporary v4 SQLite was actually removed after context exit. A separate synthetic-only snapshot is retained at /private/tmp/luna-isolated-api-e2e-v4-synthetic-only.db for local evidence inspection; it is not the operational database. SHA25686cc9ec35a272782a116d25ce252319df83523430424c60f16a86f82221e2161. No production database writes occurred.

Complete interface run:451passed,1failed across55files; the failed fixture still selected the old default provider. It was corrected to switch to the other provider and its2targeted tests passed. An attempted VM worker rerun was incompatible with installed Ant Design/rolldown dependencies and cannot count as release verification. The supported isolated fork-pool rerun with2workers is live (session32854); final outcome pending. The standard production build/TypeScript passed earlier in this turn.

- `luna-isolated-api-e2e-v3-2026-10-13.json` SHA256 `8b82a2dfff3ba4d91983793c39f9fd75fd09fc84af6723e976740b20b3a1e983`

- `luna-isolated-api-e2e-v4-2026-10-13.json` SHA256 `af18378f8858b56a69af37780b655ed0595c881223972502fe8d4a61ceb6d4b2`

- `luna-isolated-api-e2e-v4-2026-10-13.bundle.json` SHA256 `c71ce8a3035cbc35bbbad0d25a77ce2e64c14778d42dcd149b397c6b12a03a22`

- `luna-isolated-api-e2e-v4-2026-10-13.csv` SHA256 `73f9ccc71952671149fd48356fe304c8348a42bd02baa3197372611726015140`

- `luna-isolated-api-e2e-v4-verification-2026-10-13.json` SHA256 `0a50bb6b090e3240c80806c8783467f2557248880daa0aee9c1ba62215bd4ac3`

- `luna-diagnostic-probe-1200-2026-10-13.json` SHA256 `16d899a5eb93e5a36132d08e043c81901d25054b06f6e5fe71f417f860cf4a8e`

- `luna-diagnostic-probe-4096-2026-10-13.json` SHA256 `fa7ce102088120d5be897af64b4b93e32812ad85ccc7680260545c7ae125ac92`

- `luna-judge-identity-v3-2026-10-13.json` SHA256 `6b25e98a83c4915aefd6cda3e6ff885d8138960b4690b4645dbd6cff086ee173`

Final interface verification update: supported command `docker compose exec -T frontend npm test -- --pool=forks --maxWorkers=2` completed **55files /452tests passed**, 435.44seconds, no skipped tests. The earlier default-provider fixture failure and incompatible VM-pool attempt remain historical outcomes, not current release failures.

Current model receipt follow-up: actual saved-answer probe using judge meter v3 returned configured and provider-reported `openai/gpt-6-luna` with valid judgment. The source v4 report SHA is retained in the probe; original8unknown model identities and judgments remain untouched. `probe_luna_judge_identity.py` makes no target request or database write. Full integrated evidence on the final fixed reader/identity metadata runtime remains next work; formal research and novice acceptance remain pending.

## Latest integrated runtime verification and separate reassessment (2026-10-13)

Isolated API v5 completed on the final fixed reader and judge meter v3 runtime: all model-backed roles and all eight target/judge calls report OpenRouter openai/gpt-6-luna. Both diagnostic v2 calls completed. Strict verification (--require-reported-models) passed shared four-dimension suite, exact previously approved8facts/3edges, source/store separation, reconstructed instruction hashes, one fixed reader-policy suffix, and API/JSON/CSV identity/answer/score/denominator correspondence. Disposable SQLite removal was checked after context exit; production database writes0. No snapshot was requested for v5; its complete report, bundle and CSV are retained.

Original v5 decisions: Weak1/4positive,0pending,overall/formal25.0; Strong2/3decidedpositive,1pending,overall66.7/formalnull. The Strong Freshness answer was correct (“PostgreSQL applies now; it replaced MySQL”), but its reference used “current system” rather than “current database”; the local lexical parser wrongly selected the explanatory word “previously”. Rule v59 now recognizes an explicitly current database value without requiring that category noun. Eight positive/negative category tests and the selected evaluator/judge suite passed275tests.

A separate actual Luna reassessment of the exact eight v5 saved answers under rule v59 completed: Weak1positive/3negative/0pending, Strong3positive/1negative/0pending. Every new judge receipt reports Luna. Target requests0, database writes0. This changes the assessment of the saved Freshness answer; it does not demonstrate improved target behavior. Original v5 records and exports remain unchanged. The reassessment is linked by SHA256 to the original report and is synthetic engineering evidence only, not independent human annotation.

Verifier now rejects historical runtime mismatch before reconstructing instruction receipts. A no-inference check on preserved v4 evidence under current runtime confirmed that refusal. A future historical reconstruction requires its original application source; the old verification supplement remains the check performed at that time. Requirement/Agent table column counts were also corrected and checked.

Research remains pending genuine independent labels/adjudications, held-out releases/repeated studies, authorised compatible LongMemEval data and novice usability observations. These were requested from the user; none are inferred from the synthetic approvals. Current rule v59 delta is verified by focused tests and exact-answer model reassessment, rather than a newly regenerated full pair.

- `luna-isolated-api-e2e-v5-2026-10-13.json` SHA256 `329fe1282e7529a29d1b7b72760a6fe2b3b7e36ffa23f155f674f97713632d75`

- `luna-isolated-api-e2e-v5-2026-10-13.bundle.json` SHA256 `9978554e53e99900b8f57762baa84ca24b9a58fd9df1a2d83abd0b012ef16494`

- `luna-isolated-api-e2e-v5-2026-10-13.csv` SHA256 `df727eeedb47557c724affcca709d2b3dce397d451f55fc314c0776767742ffb`

- `luna-isolated-api-e2e-v5-verification-2026-10-13.json` SHA256 `449e68e37ae3659a34c3e36fd0fe2357bcbf52983b9041d49bd0f4e4d2e355dc`

- `luna-v5-saved-answer-reassessment-v59-2026-10-13.json` SHA256 `328a68c3451ac818c4a5359d8d743ceac653cadea571839dc42c474e64128a61`

## Read-only report inspection and team handoff (2026-10-13)

The user confirmed that genuine independent annotation/adjudication, authorised LongMemEval subset/permission/citation material, and real novice acceptance records will be supplied by the team later. These remain pending; synthetic engineering approvals do not satisfy those research requirements. Do not repeatedly request these deferred inputs or fill them with invented observations.

The preserved v4 synthetic snapshot was served using two temporary loopback-only inspection containers, a read-only SQLite mount, GET/HEAD/OPTIONS-only middleware and empty cloud keys. The actual Strong report showed75%,3/4passed, four decided dimensions; its conflict detail expanded to the saved question, actual answer, North/South reference memories and original timestamped messages. The actual Weak report showed50%,1/2decidedpositive and2awaitingreview, with Freshness/Conflict displayed as awaiting review rather than zero or passed. Its percentage explicitly excluded undecided answers and warned that old rule versions retain their saved verdicts. These are historical v4 display checks, not current v59 performance results.

Desktop screenshots and a390×844 Weak screenshot were saved. DOM widths were390/390, with no horizontal overflow. The browser download event tool timed out and did not provide a file path; actual browser download remains unverified. Prior API/JSON/CSV reconciliation and frontend export tests remain separate evidence and do not substitute for observing a browser-saved file. No additional model calls or research labels were produced. The viewport was reset, the temporary tab closed and both named inspection containers removed. The snapshot SHA256 remained86cc9ec35a272782a116d25ce252319df83523430424c60f16a86f82221e2161.

- `report-strong-v4-desktop-2026-10-13.jpg` SHA256 `fbeedd009c351b4e01cc706a948b60416d84922db7c466f410559284ece831a6`

- `report-strong-v4-detail-2026-10-13.jpg` SHA256 `1a519ecc9a53b10860b23d7c989c2a3074076f2d7b00f14e8955b454f3ce68b2`

- `report-weak-v4-desktop-2026-10-13.jpg` SHA256 `e40090fa7321cac0ed2f2aa39cd58ed1a9d957ad8f330764622cab26b4afaa2e`

- `report-weak-v4-narrow-2026-10-13.jpg` SHA256 `a7c8b731c37462fb072703ae70e192cd53013fda95dbe53bce467d7af10dd8cc`

- `migration-plan-verification-2026-10-13.txt` SHA256 `abd128128e1a6c73859cd859402f7315df1c46a02457beaec8f51360df6bf2fd`

- `migration-plan-intermediate-failures-2026-10-13.txt` SHA256 `48893dfa50e79109cc499fb6e06f1d19759162341e996634e5dcc32569e03ab7`

- `migration-0038-roundtrip-2026-10-13.txt` SHA256 `a291f6eb79a1c13d3941b02cbcc60175abc82cc95a55a7c18e4142bcf701863f`

## Backend regression fixture repair

Initial full regression failed; final focused suite passed84tests. Full settled rerun remains pending. These are simulated contracts; no new provider calls or research labels.

- `full-backend-regression-initial-2026-10-13.txt` SHA256 `8274e3c1206e89a548e051483cc2374cebf477615357e23159e89e2c9f52ba1f`

- `backend-regression-initial-source-manifest-2026-10-13.json` SHA256 `42a4039bbf1d8242edac861a2f677ddef006d7be21d1e6ef0907e62c7571c7a1`

- `backend-focused-intermediate-2026-10-13.txt` SHA256 `896fb5b9acfb44bf48a6dcb6d65a0f86321fde2f390412919a7307b9fd5a75aa`

- `backend-focused-final-2026-10-13.txt` SHA256 `b6a757e41ed4e3f7ea5bbcc955ee4f3a25827ba7d152d508ba2645141cf55b1f`

- `backend-regression-final-source-manifest-2026-10-13.json` SHA256 `b6f8533e1b89ebffda5a6eebadccca3a9aecd27eebd05d28b79932939a1e879c`

- `paper-artifact-contracts-2026-10-13.txt` SHA256 `0a9a5ce2ac061b595f60d39d4306edf2eb88390f0ae1757f8bd32b3e880f88f8` —15script contracts passed; simulated fixtures, no real human labels or model calls.

- `full-backend-regression-final-2026-10-13.txt` SHA256 `6ca9924ab5bac3df96fa2e4d274c10f6cab7fa2a163adb3f110fa201fe8f100f` —complete backend1311passed,8PostgreSQLskips; Ruffpassed;221.09seconds.

- `repeat-export-contracts-2026-10-13.txt` SHA256 `d2e3ab0e57a82325149ead147a592c386dcf132a7587cb91fc8fda78429ef2ba` —20script contracts passed, including repeat means/variation, denominator drift and pending-not-zero export checks; no provider calls in these tests.

## Completed v6 repeat receipts and separate v60 assessment

- `luna-repeated-isolated-api-v6-2026-10-13.json` SHA256 `a999237ae6ceb3258747aef5d8aa517783893762df6835da3d132e70eb59ee6b`

- `luna-repeated-isolated-api-v6-2026-10-13.bundle.json` SHA256 `51eb6b7e5a94266558fcc3da486d1395770337eb80ec032504e005946ccab275`

- `luna-repeated-isolated-api-v6-2026-10-13.csv` SHA256 `7fc548455d3dbc742444850646b37869255fd7eff0e8a6fee01f7a766b008840`

- `luna-repeated-isolated-api-v6-verification-2026-10-13.json` SHA256 `d761681319dfc3e07ba2e1b1c92c204b693b116dcc708346274ca111560f4a7c`

- `luna-v6-frozen-application-source.zip` SHA256 `92bf8b8463c1eb4763a4ae58e945f0433b2df81dc2b41a9360ef00facc4c2e3d`

- `evaluator-v60-regression-2026-10-13.txt` SHA256 `8f1d188bc70a6931a819da7524dca102e1cbf3a06f592ba3d8cb6ab4cd1cbf7b`

- `luna-v6-freshness-reassessment-v60-2026-10-13.json` SHA256 `b3a4638d333dae4d0732d1bb0dd9d2a92963f7e40dda8ee35443d50c66a39ff7`

## Completed real Luna repeats and v60 wording repair (2026-10-13)

Actual isolated v6 completed all4runs:Weak/Strong each2repetitions, same4question frozen suite and same Strong reader policy. Every model-backed role and all16target/16judge calls reportedLuna;4diagnostic calls completed. The strict no-inference verifier passed exact source-approved inventory/edges, target-store ID separation, reconstructed instruction receipts, repeat membership, JSON/CSV answer/score correspondence, independently recomputed condition means and population standard deviations. Temporary SQLite cleanup confirmed. The separate synthetic snapshot SHA256 is a7bedb5ae0180321a816ae2ff4b0d1527a77938cddcbc5023252deac954581bf. The application source was archived before further evaluator changes, excluding credentials, databases and source history;124files with their content manifest allow restoration of the verifier's original runtime.

Original saved observations:Weak25.0/25.0%,2/8positive,0pending,mean25.0%,populationSD0.0pp. Strong66.7/75.0%,5/7decidedpositive,1pending; descriptive mean70.85%,populationSD4.15pp. Strong repeat1formal overall isnull because Freshness is pending. The available-score mean does not resolve that missing judgment. This is a one-source approved-synthetic engineering repeat, not formal Experiment B, independent sampling, human gold or strategy superiority evidence. Requested seed is not proof of provider determinism. All original scores remain unchanged.

A new v6 reference said “The current system is PostgreSQL; it replaced MySQL, which was used previously and is no longer used for that backend.” The v59local parser incorrectly demanded the tailword“backend” from an answer “PostgreSQL applies now; it replaced MySQL.” Rulev60recognizes both value-first and category-first explicit current-database statements; correct and reversed-answer tests cover database/system/engine/datastore. Selected evaluator/judge regression283passed; Ruffpassed. This is a post-run software change, not part of the original v6runtime.

A separate actual Luna assessment of exactly that one saved question under v60returnedpassedtrue and provider-reportedLuna. It is SHA-bound to the original v6report, targetrequests0, databasewrites0; stored apart from the original archives. It does not replace v6scores or establish improved target memory behavior. The v60delta has focused regression and a real exact-answer reassessment; it has not been subjected to a new full backend suite or regenerated repeated pair. Read-only comparison screens and actual browser downloads remain next engineering work. Team research and real novice records remain pending.

## Actual browser downloads and comparison inspection

- `comparison-v6-desktop-2026-10-13.jpg` SHA256 `bc903966ec1e35d1628ce13c0bda5520430497c42dfaf3390ca4bfa12f932d9c`

- `comparison-v6-narrow-2026-10-13.jpg` SHA256 `988e37df6e36435c1ece764f6d29b240ffe36d92ff8230bc94c0b95e2512ca65`

- `comparison-v6-narrow-fixed-2026-10-13.jpg` SHA256 `37a3a3b7a8edb0889a0c7e151827b332835eb8e1cf433929652fd12c16b888fd`

- `comparison-v6-narrow-fixed-preview-2026-10-13.jpg` SHA256 `b3a9d60c3bb16346ca36e90834009b893505dd01a79887e4c4b71fe4a95a5fc9`

- `comparison-v6-repeat2-desktop-2026-10-13.jpg` SHA256 `9b5778b9abf96ecb74084c0c79f81ca202551d43ca161eb7c3ef2a4d61b3e7a4`

- `comparison-v6-browser-export-2026-10-13.svg` SHA256 `92dd29577aabf510b82232d58a8699044aa825012e61cbf38589803f1ec287e6`

- `report-v6-browser-export-2026-10-13.json` SHA256 `8842e50101d28b0237eeb976717482b7c2fe073e778e4791af48ca879c362a3c`

- `report-v6-browser-export-2026-10-13.csv` SHA256 `90b2c96a8a6f24147a8ff4a95e4f67016a2c344db0b49e2b0559beb52575c72c`

- `browser-v6-export-correspondence-2026-10-13.json` SHA256 `f95d578d8d606711d115e575d08f900eb7c0ef490620f1339e6ea7da872d7907`

- `comparison-export-ui-tests-2026-10-13.txt` SHA256 `b9c3dc678b9f943a8317977bd690740827b7255ba3598930e07ff01a6d715fda`

- `comparison-layout-build-2026-10-13.txt` SHA256 `4de62e54cb30771c87d47412787d7fdc53c84cbe4732fb3ec37eaed17a53b4ed`

## Actual comparison/export UI acceptance (2026-10-13)

A temporary read-only server mounted the completed v6 synthetic snapshot read-only, blocked all non-GET/HEAD/OPTIONS requests and had empty cloud keys. The current interface was inspected for both actual repeat pairs. Repeat1 showed25.0/66.7%full-suite scores,3comparable decided questions,+33.3pppaired change,1pendingexcluded, and Freshness notscored/no comparison. Expanding Appropriate Use showed exact expected behaviour, both original replies and assessment reasons. Repeat2 showed25.0/75.0%,4comparable questions,+50.0pp,2improvedanswers and1stillfailing. These are saved automated engineering outcomes, not causal/research assertions.

Actual browser download files were obtained for comparisonSVG, reportJSON and reportCSV. The SVG includes saved scope/model/policy labels, counts and Freshness“Not scored” rather than a zero bar. The downloaded JSON/CSV were reconciled with the original savedv6run:all4question/response/evaluation identities, exact prompt/expectation/reply/assessment, source statements, outcome states, selected model/strategy and summary/dimension denominators correspond. Current runtime-version warnings can differ; originalscores remain66.7%,2/3decided,1pending. A separate correspondence receipt retains hashes. This closes the previously unverified browser-save observation for these exports; the earlier failed download-tool observation remains historical.

A real390×844comparison check found long selected audit labels expanded the grid to838px. Scoped minimum/maximum width and full-width select rules now constrain both labels/selects; reread DOM gave390pxpage/viewport and324pxselectors with rightedge357px. The chart remains horizontally scrollable inside its own bounded area. Before/after screenshots are retained; the“narrow”file is the pre-fix failure, and“narrow-fixed”is the corrected view.49comparison/report/chart UI tests passed across3files; production build/typecheck passed with the existing large-main-chunk advisory. This delta was not followed by another complete frontend suite; prior complete452passresult is separately scoped.

Viewport reset, temporary browser tab closed and only the two named inspection containers removed. Synthetic snapshot SHA256 remaineda7bedb5ae0180321a816ae2ff4b0d1527a77938cddcbc5023252deac954581bf. No model calls, writes to the snapshot, operational database modifications or human labels were produced. Real novice and formal A/B/C research records remain team-pending; these automated/browser checks do not satisfy novice usability. Other primary screens and formal experiment workspaces still require release-specific acceptance before claiming all engineering requirements complete.

- `research-permission-ui-initial-2026-10-13.txt` SHA256 `9324c83d00a64fa5ff5e7f890d8e13d24156d9c77dcbaf6e0b802fc365e116cf`

- `research-permission-build-final-2026-10-13.txt` SHA256 `5757e256363a7d6834bb44b6bc4d60b72aa3c670784b67d86283895a2dd2aa27`

- `research-file-permission-default-2026-10-13.jpg` SHA256 `538066fe539a5766dbdfa949258d02bbb387762fcbc44d9c00c7000530487e0f` —actual390pxread-onlyworkspace,permissionunchecked.

- `research-file-ui-final-2026-10-13.txt` SHA256 `401957e28479a3ab800fef62c4c183cb305ae8e50a856923044c6c760c7890e6`

- `research-api-permission-final-2026-10-13.txt` SHA256 `7646f121fa27b02ddb3e1c01a137e87ec6ac1187232bbc32170170dc0f0ac143`

- `research-api-permission-build-2026-10-13.txt` SHA256 `cbb49f8702016c06687bd019730520685cac3eea5c305f5f6771c96ad762eeda`

- `research-permission-api-ui-final-2026-10-13.txt` SHA256 `329f3970f740ba4cecfc6db73cc7ea79219dad70d9f7592d16f6064b1a96d80d` —50interface/client tests passed after final API argument migration.

## Whole-regression outcomes and diagnostic target isolation repair

- `full-backend-current-permissions-2026-10-13.txt` SHA256 `045149001770288ea51f59ae43f3397668fe641b05798073e3cc0e7b89790303`

- `full-frontend-current-permissions-initial-2026-10-13.txt` SHA256 `a6ef22cfe0a19e991b69e29f2409f5d7171725cf6b4ace78e7955b211a85b10f`

- `target-isolation-stage-initial-2026-10-13.txt` SHA256 `cc1b5f9a7c794b54360b0b908b1cfe5daf7ad437c56da7e9b5db618117e39697`

- `target-isolation-stage-verified-2026-10-13.txt` SHA256 `31f0d5b79510788ff94153093735ca68132beabf12ec3f230d2c08b1eb5e8a21`

- `target-isolation-budget-initial-2026-10-13.txt` SHA256 `ffd6404a0d0406a72ae41e2e0e7571cbb37446c2bc1381847f42e8c4084fe212`

- `target-isolation-settled-2026-10-13.txt` SHA256 `005db1be2d9ecb7d7745ef664cdee6ea8cb38b27bc3ccbc6ca1cd064f9dce9cf`

- `frontend-regression-repair-focus-2026-10-13.txt` SHA256 `40ced1e8e02b2947479dd6e168f687890893f124207017d24a05f8a2009feb2a`

- `luna-current-normal-input-equivalence-2026-10-13.json` SHA256 `8ac8c0d2478bcb7bf8cf435a1a81fcb97b574be7c7ec65a4b3bdde20b76c5b46` —current secure input renderer reproduces16original model instruction hashes on saved target-owned contexts only;0inference/DBwrites,not a full-runtime rerun.

- `full-frontend-after-regression-repairs-2026-10-13.txt` SHA256 `9bec62240683e62bc70671468d8de99d400bc9c607919ead73598ace8ae62cff` —456tests/55files passed,608.40seconds; full settled UI source unchanged.

- `full-backend-target-isolation-2026-10-13.txt` SHA256 `ad5faded0092bc2a9923f47ba1f1e6ad19d086b91240595d3da5470cd1489d8e` —1325tests passed,8dedicatedPostgreSQLskips,Ruffpassed,244.26seconds;222source entries unchanged.


## Current v7 failure and completion envelope handling

- `luna-current-isolated-api-v7-failed-2026-10-13.json` SHA256 `445b2ca367e002e5df334d3e0955a978286d0e2ce2d628ef7ff558db399764fe` — Terminal failed current-runtime trial; extraction/planning completed, no target answering.
- `luna-v7-relationship-envelope-probe-2026-10-13.json` SHA256 `e6ad73cc1d0454a7074fbe68287a5ce88deae5245e1edfd3a399dad3d5905521` — One approved synthetic relationship request; HTTP200 top-level provider error; no production writes or target requests. Does not identify the underlying provider cause.
- `provider-error-envelope-tests-2026-10-13.txt` SHA256 `f67f0ed45aa931850cf94ba5cd7747a01b8b60e6953df78880933c9545850b0c` — Ruff passed and157focused tests passed; no-network mocked completion cases.
- `full-backend-error-envelopes-2026-10-13.txt` SHA256 `c6124ce3ee1422ae1c9288e58ea20afb9454105506dcc8f2a2744501ac0db93f` — Ruff passed;1340tests passed,8dedicated PostgreSQL skips,one existing warning;304.40seconds. No-network temporary database.
- `backend-error-envelope-source-manifest-2026-10-13.json` SHA256 `8ef6185e6a3d64a1ebbf95da3b5665c9c92974df04ff6b7ba216923de7f5d1ce` — 223app/test files hashed before regression and confirmed unchanged afterward.

- `luna-provider-error-shape-2026-10-13.json` SHA256 `1d347b52f9d99e6a5bee48d01312c0945865a38521dd958ae976a221ce87da91` — one bounded source-approved relationship call; actual numeric provider code502, HTTP200, no recognised message category; no production writes or target answers. Script setup first failed before any HTTP request; corrected setup produced exactly one model request.

## Peak-load capacity controls and v8 outcome

- `luna-provider-redacted-error-2026-10-13.json` SHA256 `71c0b7b5408f93fd4f6d2d606876ce42a05c88b9f2393e8a1063367a1454b688`
- `luna-relationship-ordinal-budget1800-2026-10-13.json` SHA256 `338e397fa8c5820b8fe5ef6d7e3fa73fe57558848b3331cab21e37205fd7a119`
- `luna-current-isolated-api-v8-failed-2026-10-13.json` SHA256 `2d676cb44a73685dc82715405b4bee23f47335775b4cb12a0a030086456b01a0`
- `pipeline-output-cap-tests-2026-10-13.txt` SHA256 `4d48808f073828306a368c97ff9c5f89241a7f4658575c929db6b803210e2d02`

The redacted-error probe confirms peak-load maximum usage rejection. The correctly aliased1800relationship probe completed; v8complete trial at1800failed during extraction and made no target requests. These are engineering-only probes, not human research evidence.105focused tests and Ruff passed.
- `full-backend-capacity-controls-2026-10-13.txt` SHA256 `69f8344e78e2438d6d2990d73721ffb14dd7d4c9914c81321344f671ca4dbf51`
- `backend-capacity-controls-source-manifest-2026-10-13.json` SHA256 `2de06dc5fe1a00666cc242da7b16ea895ba6f496a6bb5320dc1667039f3b14e3`
- `luna-v8-failed-frozen-application-source.zip` SHA256 `4ccccf842c6927ec304c5c96fec89616db3a797c3cd57de48550a7752b5de354`
- `luna-v8-failed-source-binding-2026-10-13.json` SHA256 `c1ed7a01e7d31da324930a47c0c9511bea6a2df128ca5f576cc86c6eb40acad6`

Final current backend: Ruff passed;1352tests passed,8dedicated PostgreSQL skips,one existing Starlette warning,216seconds;224app/test files unchanged. The failedv8runtime source archive was reconstructed by reversing only the later extraction-error-summary edit in the archive, and its122app-file hash exactly matches the original runtime receipt. The failure snapshot SHA also matches. No working-tree code was reverted.

## Final1200-budget and same-model route checks

- `luna-current-isolated-api-v9-failed-2026-10-13.json` SHA256 `cfb254421713d4bc442ce778ce680e8b234af9a741c0817d9d0949cdebae1c63`
- `luna-current-isolated-api-v10-route-failed-2026-10-13.json` SHA256 `3d313561fb318280b4a018180e7014ee9ae609218498dfba1127f282af36b978`
- `luna-current-isolated-api-v11-route-failed-2026-10-13.json` SHA256 `38862392b4bfb8c02ad5cada110f708b80055bceb6d2b30e5582d9f2c629e4de`
- `luna-v10-route-dispatch-2026-10-13.json` SHA256 `ddab7f87f2fc7699e199c9724dd3d43126dd9397db08e1f0d0cb07ed936f0a41`
- `luna-v11-route-dispatch-2026-10-13.json` SHA256 `32d0981573903b17a03ffe638353fd40053a2db6b2018d510f08fa7c756ba17b`
- `luna-budget1200-frozen-application-source.zip` SHA256 `6696e4bf8e187b55bece9fbf39878e8813c5a9006586551af69b9326ab8c038e`
- `luna-budget1200-source-binding-2026-10-13.json` SHA256 `4a24c4d93edb9f3b3391ef1aef01d3f2a69c0f405d07dc77377c8b795efb4ad9`

v9failed at coverage planning with capacity_limit at512requested output tokens after extraction/review completed. v10/v11explicit-route trials failed upstream404at extraction. All terminated; no target replies; disposable DBcleanupconfirmed. Frozen app source matches all three original reports. Historical matrix moved intact to docs/REQUIREMENT_TRACEABILITY_HISTORY_2026-10-13.md.

Final same-model route check:

- `luna-v12-route-dispatch-2026-10-13.json` SHA256 `23eba2dd61a786bd9eb1301a606016bed845da8dc351ede54e3ca265c6d62264`
- `luna-current-isolated-api-v12-route-failed-2026-10-13.json` SHA256 `1bfea65d875f3fac5a44a36a68c6d9dfc3f1b280af8091ff96025cf3e2f2c8c6`
- `luna-v12-source-binding-2026-10-13.json` SHA256 `99affed97f88c4a9e22e9125f5880876fe89102533546951136f28b8563a3b6c`

v12amazon-bedrockroute returned upstream404(API502); all trial jobs terminal; cleanup and source/snapshot bindings verified. Active requirement matrix now has25current requirement rows and6assumption/constraint rows; prior chronological matrix is preserved intact.

- `luna-current-isolated-api-v13-retry-failed-2026-10-13.json` SHA256 `d919b3a149cabadb1128fe930a1e3d6f39f745b1d2c2b496379cc267709dcb8c` — user-requested default-route1200retry: source extraction/relations/generation completed; independent review capacity error and target502; fullworkflow failed. Original source matches1200frozen archive; snapshotSHAverified; cleanup confirmed.

## Target failures and original-version recovery

- `target-failure-receipts-2026-10-13.txt` SHA256 `61daca8cc54a4b72c5456b99ad4a85fb5520c68fc3369bb4b88f8e5106e3a699`
- `full-backend-target-failure-receipts-2026-10-13.txt` SHA256 `0d032d503ad0571cd39bd0ade37e7805bd5b26c6aa11f019edc7eeb0b5eb2551`
- `backend-target-failure-source-manifest-2026-10-13.json` SHA256 `44aa4ee6e34c73ad74a434c41f0c5aedf35961f4837eaeb04111f50b1be8cb88`
- `luna-saved-target-error-probe-2026-10-13.json` SHA256 `9878e33933f194cd1474017ae2bf4ef2323ddd093c9db58ab66cbc7b29a8b2d3`
- `luna-v13-recovery-runtime-blocked-2026-10-13.json` SHA256 `c6995ee4993c8e2bb9569aebb3fd4a2409eb7a0caaf3d8e919099449c2d8eb82`
- `luna-v13-frozen-runtime-recovery-failed-2026-10-13.json` SHA256 `c002e48e974f4c7ccbc489984e80bd21882fd521d1823f627cf144f87dac14e0`
- `target-failure-receipts-frozen-application-source.zip` SHA256 `59581f730e5347437a4167431da6bb59334fd833df25c33c587d7715a9fb1d34`
- `target-failure-recovery-binding-2026-10-13.json` SHA256 `faabca93ee8766239736778e9f55ca7d239c19a67d06215b89a04ddf74266c84`
- `probe-saved-target-failure-2026-10-13.py` SHA256 `a522d332605a2b43a096eebd2fde52534e428c753e4271c11dc069aecd265dcd`
- `resume-frozen-v13-2026-10-13.py` SHA256 `c56cf8d370751c4962f175dcd124f3ffb768e8001012fef1f73090c63f1beec1`

60focused and1355complete backend checks passed;224source files unchanged. The current-connector512target probe completed. Public recovery correctly rejected changed software; exact original source restoration passed that guard but target retry returned502. Both saved replies and original snapshot unchanged; temporary DBcleaned. Do not merge this single-input success into the originalfailedtrial or claim successful full/repeated/independent-research acceptance.

- `resumed-goal-impasse-audit-2026-10-13.json` SHA256 `38728c48684db0d5ef1a281eec43ba8ff5e1b5093ad963aa44641cc9ad962821` — thirdresumed-turn audit: unchanged source, terminal jobs, fullworkflow acceptance contradicted by saved failure, genuine research inputs still team-pending. No new model request or production change.

## Durable current full-workflowv16 and artifact-loss correction

- `luna-current-isolated-api-v14-partial-2026-10-13.json` SHA256 `1f3f7e1c33a7a9cf2c98f65c6f72013c972151b2a88015ccc1549f9d1d25b7a4`
- `luna-current-isolated-api-v14-partial-2026-10-13.bundle.json` SHA256 `dc65491780d204cd0ad2e18a772c439269a0ff0f61ac7639ede6a9f841b0281f`
- `luna-current-isolated-api-v14-partial-2026-10-13.csv` SHA256 `bcb803a2b6ba6b8463c1785dbfa0fe32942b381abdd1e3004da88f9dd9f35ad3`
- `luna-current-isolated-api-v14-core-verification-2026-10-13.json` SHA256 `eca31148d93ab9d6a32176a3a55e491b5b47c8b1c81f3c1d14ea269a8ffd9669`
- `v15-temporary-artifact-loss-2026-10-13.json` SHA256 `b9225be142f30db3a9fe2e190c6808f9f5078a4d2aa2f8cf8e55c0d424c7b370`
- `luna-v15-observed-terminal-log-2026-10-13.txt` SHA256 `3657957e0d505993da90d08b31818b2acbcfbf2ca51cfa9caa5fa3979f0582ad`
- `luna-current-isolated-api-v16-2026-10-13.json` SHA256 `5f1e290c7c5d531f44437578f26aecc9a25377fd75155c3b6403cf61c9bd4f57`
- `luna-current-isolated-api-v16-2026-10-13.bundle.json` SHA256 `090e17a152444c109beafac3807378a49a84889b2833c17f18d076400b5877df`
- `luna-current-isolated-api-v16-2026-10-13.csv` SHA256 `c8b2d8264678924852c9a2b68f1af39404ed36ef70fa7fbc26377826be282bcc`
- `luna-current-isolated-api-v16-strict-verification-2026-10-13.json` SHA256 `6d533f1c379123463872ce2196e57e2d3e7679ca97786a5a4450ad5fa2a11f93`
- `luna-v16-frozen-synthetic-evidence.zip` SHA256 `ff5b8e8f3aabdc4d713f1e1f2c70438c658434de8c384aa2e3b781ab5c6d297e`
- `luna-v16-current-runtime-binding-2026-10-13.json` SHA256 `45cb95ed40d12403425a93eb10675b42a72597e7e9672359f16a3d9d3385495d`
- `luna-v16-current-runtime-log-2026-10-13.txt` SHA256 `a1bf0e43e8a2970ef66651eb025d2648888f6eea61aa9f46a6e01a5a911f768d`
- `pipeline-cap-operational-application-2026-10-13.json` SHA256 `aafa2ebdcc681a1a7d8d42914b2a097ddb3da0fd2a926eb7a1e5ac5c48f2e24d`

v16fullworkflow and strict real-model/target-input/suite/repeat/export checks passed;16responses/16assessments/4diagnostics,2repeats perpolicy.4uncertain judgments retained; formaloverallscoresnull. All evidence now durable, including source/snapshotZIP. v14partial retained; v15temporary-fileloss disclosed and not silently promoted to an archive. Operational1800setting applied with no stage locks and unchanged counts/schema. Research evidence remains team-pending.

## Actualbrowser validation, rulev61 and freshv17

- `v16-paired-browser-2026-10-13.jpg` SHA256 `d7524fc9705a40281fc110aa1f54508419d0b0723bcd73af0c009de77d5ebf6e`
- `v16-paired-browser-dom-2026-10-13.txt` SHA256 `7818b3f7212e42a9252c83d996ec81ae2a173459d5f8b842f61d0f1f4864a145`
- `v16-browser-comparison-export-2026-10-13.svg` SHA256 `003dab19a2c9fa4e1078383c978dc1662594e0b670dbcfde5312e1951677ab3f`
- `v16-browser-report-export-2026-10-13.json` SHA256 `ed6716cad38d690e2a08ea2e186d8ef8d377c9a1729b316409b3286078045187`
- `v16-browser-report-export-2026-10-13.csv` SHA256 `0eef700541b4c07821d08ad122f7ce69dc324aa9f9843b2129a8b8be4314f538`
- `v16-actual-browser-export-correspondence-2026-10-13.json` SHA256 `47d7064d5fdb11d04da8169b18cbe431dbce6fb866ba6ced1376d90ddbc1c069`
- `current-record-rule-v61-initial-2026-10-13.txt` SHA256 `a8c1dfebfc960479dad7ea517dcf3d95e7798296377c0a70d34c5ca6258a531b`
- `current-record-rule-v61-focus-2026-10-13.txt` SHA256 `e68dd54c9e36a877c93a6d20bd37b841c2a4ae09535fb9ea930b0c0d382e0791`
- `full-backend-current-record-v61-2026-10-13.txt` SHA256 `66406dd22d6c18b00ee60c382f5bf2dde499037669c7d4589b44cf15cf35116f`
- `backend-current-record-v61-source-manifest-2026-10-13.json` SHA256 `e12bde47b9a89563e276e19be53a3003d7c3a1e932dcaba096343e2641ee2dd2`
- `v16-rule-v61-local-supplement-2026-10-13.json` SHA256 `179bec03abd089ab40b74ff80064d24b574e0ef72070d155c8e13052882208ab`
- `luna-current-isolated-api-v17-2026-10-13.json` SHA256 `250e1993cbf56edbad86c9cbae4b01d776b14a97081d9988b2f20741d2752a8c`
- `luna-current-isolated-api-v17-2026-10-13.bundle.json` SHA256 `ddc7499f1293424423ea657bef87384a4e76f876995957b12d74830fa8f90d93`
- `luna-current-isolated-api-v17-2026-10-13.csv` SHA256 `baa8d787d4eedbb8003b89e636655884749f5652fce49a203b72fc98054e0655`
- `luna-current-isolated-api-v17-strict-verification-2026-10-13.json` SHA256 `8c02320cd16524fe8b675cbee01ef267cb0d9101154bfd91d557fa1e6cb26774`
- `luna-v17-v61-frozen-synthetic-evidence.zip` SHA256 `7d5cec40eaaf714b73e9a9f279e1292b4cc153d5ff6aa41ed260a0c54d16cbc1`
- `luna-v17-v61-current-runtime-binding-2026-10-13.json` SHA256 `d2833dd5fb066eeb10531aeeca91a70c904b147917cacf09e0b4787d0f4b5d5b`
- `luna-v17-v61-runtime-log-2026-10-13.txt` SHA256 `6dc37b5b206f3f01621536d4a225a1c645205ba9185612317cfc08caf7c581cd`

Actualv16UI/exportsource checks passed; oldpending results preserved. Rulev61fixed deterministicpreviously-as-answer bug;315focused/1366fullbackend tests passed,224sourcefilesunchanged. Purelocalsupplementmatches4saved semantic verdicts; noDB/model/human-label writes. Freshv17actualLuna fullpipeline/strictexports passed;2conflict judgments remain pending. Alltemporaryviewservices/tabcleaned; snapshot/frontendunchanged. Source/snapshot/reported-model archives available; formalresearchand genuine novice acceptance remain pending.

## 14 October Luna retry and operational output cap

Extraction and core audit completed:8responses/8assessments, JSON/CSV identities reconciled. One diagnostic reached1800 and was truncated; the original report stays partial. Separate reanalysis of saved synthetic cases completed at4096, which is now deployed. Health200, conversation/audit counts13/18 unchanged; these are count checks, not a full content audit. Fullworkflow at4096 and strict verification of this partial trial remain unmeasured. All224 backend source/test hashes match the prior1366-test manifest. Source/snapshot archived; no human research labels created.

- `luna-retry-2026-10-14.json` SHA256 `70fef69cd35ba946dd937dd6140e5dd25c43fa2b70d48ccd5a27f2173f347ca8`
- `luna-retry-2026-10-14.bundle.json` SHA256 `f4d4dd1bca9d892d5cec43f73fa75884389dd2fb090591c12de8dc5c8758454c`
- `luna-retry-2026-10-14.csv` SHA256 `c9197c6b50d2f82074d0479bf304043916e64572b73bf857d1bb52e0c7fae40e`
- `luna-retry-diagnostic-4096-2026-10-14.json` SHA256 `ce3e5527f69eae2b795d61b88b1d9c6b79b8732fb6900b769028d3dcbc03aaf3`
- `luna-retry-summary-2026-10-14.json` SHA256 `9d9d5e939e8d8dc3e664932390df358e9f5bf7142e9b9336cc1e079594490dc6`
- `luna-retry-artifact-binding-2026-10-14.json` SHA256 `e96ee4c507087c072246a73a6c0bb987ccb557cc94c1cdf014e61fa651b9018d`
- `luna-retry-source-and-synthetic-evidence-2026-10-14.zip` SHA256 `3055e5a541a06c234c30dddfc495936cd42dbba3275927ef2408f311c8888400`

## 14 October current4096 full-workflow acceptance audit

Actual two-repetition-per-policy trial completed16target replies,16assessments and4diagnostics; JSON/CSV identities reconcile. One judgment remains pending. Extraction succeeded and independent review succeeded, but relationship analysis failed `endpoint_evidence_mismatch`; the reviewer identified the missing conflict. The prior approved synthetic inventory allowed core execution to continue. Strict verifier rejected the failed role. Original script status `completed` is retained as recorded, but acceptance is **partial extraction failure**, not a full-role pass. Original source/snapshot/report/exports archived before changing the script. The smoke status now requires all three extraction-stage roles to complete;10offline status/export tests passed. No application source or original scores changed; no human research labels created. Latest all-role strictly successful trial remains v17at1800, not this4096trial.

- `luna-cap4096-full-2026-10-14.json` SHA256 `b016dcd66f37611a38d609cea4c2b1aad95942ea68a951f67033ecf977aa719d`
- `luna-cap4096-full-2026-10-14.bundle.json` SHA256 `f4f676b151921df3ccf66ff791743932f768e2a6f997b21da49980ba5648f8d6`
- `luna-cap4096-full-2026-10-14.csv` SHA256 `ac0e9bd77c4cc722858b6c4acf3674858e0a754c913c0900ea9adc46f0bbfcc7`
- `luna-cap4096-acceptance-audit-2026-10-14.json` SHA256 `eeb4f8309aa6f5c030afcc0910c0756a901bf07270dcc179f016509a99c19837`
- `luna-cap4096-original-source-and-synthetic-evidence-2026-10-14.zip` SHA256 `b658dbae81e3fc50263e1f0082510b0af4c480c2100c7517ea20a156a735ae14`

## Relationship citation diagnostics delta — 14 October

Two predeclared database-free Luna relationship probes completed with the three expected relation types and separate endpoint citations. Original failure remains; the exact faulty old fields were not preserved and cannot be recovered. These calls do not prove stable all-input performance or a full-workflow pass. Relationship validation now records faulty endpoint field paths and invalid-reference counts without recording invalid IDs or source text. The reject/atomic-mutation gates remain unchanged.23focused tests passed (one existing Starlette warning). The earlier1366-test result applies to the prior source; a whole-suite run for this diagnostics-only delta is not claimed.

- `luna-relationship-probe-2026-10-14.json` SHA256 `e66d5f4697913814dbfc3c7ab0634066b6633d0d8968dd28f0a8e012afe8af68`
- `luna-relationship-probe-binding-2026-10-14.json` SHA256 `07c27b442f5533c6a02ea5bdc1a2a2b3299f9245b99c17703b59c2ca93be38df`
- `relationship-diagnostic-delta-validation-2026-10-14.json` SHA256 `f427ba6a3afebe0edfe1eef0d66faf6ee37b1eb46b4fa234c6c51766ce9ecc8e`

## Current full regression — 14 October

The relationship diagnostics delta is now covered by the full backend run:1366passed,8dedicated PostgreSQL skips,1existing Starlette warning,315.84seconds. All224app/test hashes match dispatch. Earlier focused-only limits remain dated history. This verifies code contracts, not independent research labels or a new all-role model trial.

- `full-backend-relationship-diagnostics-2026-10-14.txt` SHA256 `0b21e28f4d8ee6888c0ee375dcb0df9033806724739f37d40f49b90247fccc48`
- `backend-relationship-diagnostics-source-manifest-2026-10-14.json` SHA256 `94de49e580806e23e85cbd0a271525bfa2557a0fcb057b74256277901aceedcc`
- `backend-relationship-diagnostics-full-regression-proof-2026-10-14.json` SHA256 `0b9cb1015df2082bedc979a935b43080df797ba93b6f7e4e2704d23b8aacd0e2`

## Latest current-runtime supersession — 14 October

Current diagnostics code at operational4096 completed all roles and passed strict verification:two repeats per policy,16target replies,16assessments,4diagnostics, same approved source/frozen four-dimension suite, actual reported Luna identities and target-owned input/export correspondence. Two judgments remain pending and affected formaloverallvalues remain null. All224backend/test hashes match the1366-test run. Original failed4096trial remains unchanged and separate. This establishes approved-synthetic engineering evidence only. FormalA/B/C, independent labels/adjudication, research freeze and genuine novice observations remain team-pending. No active inference/test job remains from this verification.

- `luna-current-diagnostics-full-2026-10-14.json` SHA256 `a89c673cbe9eaa745037b23604894fb84b48264ad71b5c4933ae390e61aa974b`
- `luna-current-diagnostics-full-2026-10-14.bundle.json` SHA256 `16dbc367af3782e4a8d0e248660e331a48fd7191197ef8303ca4ac3ff910e210`
- `luna-current-diagnostics-full-2026-10-14.csv` SHA256 `4897685f0d71ef004ea00e858017ea8fc99932c37cd050932752537c94b7cdde`
- `luna-current-diagnostics-full-strict-verification-2026-10-14.json` SHA256 `89b22cd9799e4c7ac1ed077e60c193cd612b04a3bc07bf13e54437ef87b4e942`
- `luna-current-diagnostics-runtime-binding-2026-10-14.json` SHA256 `8d39e1f216a19fd6d8315b886b1fd5d53a6b2140a379f6b230ae81a2222b85d1`
- `luna-current-diagnostics-source-and-synthetic-evidence-2026-10-14.zip` SHA256 `d507be3c7d0951b7716a43f852e5624af00ba262870296d217c9e3de798d1595`
