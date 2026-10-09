# Diagnosis and validation workflow

This workflow measures a deployed model **with its surrounding memory mechanism**. It does not train model weights. An OpenRouter model or local Ollama Qwen can serve as the fixed generator. Keep its model, temperature and other generation settings fixed when measuring memory-policy changes.

## Target and auditor separation

Normal target ingestion receives authorised conversation messages. Normal answering receives a task and the target's privately retrieved context. Expected behaviour and reviewed evidence identifiers belong to the auditor. Review endpoints expose reference behaviour to researchers; they are not target inputs.

`TargetMemoryProfile` freezes a name/version, retrieved-record limit, context character budget, project isolation, current-state preference and additional general instructions. New audit exposes these settings. The diagnosis workbench also allows a targeted retrieval strategy. The original and generic controls retain their original strategy and generation policy; the candidate uses the generation policy corresponding to its chosen strategy. The saved report lists every change. This package measures the whole changed mechanism, not an isolated individual switch.

The generic control appends a generic evidence guardrail to existing instructions. The candidate may use a diagnosis-derived general rule. Never paste an expected answer or a case-specific fact into additional instructions.

## Experiments

1. Import and review authorised source history.
2. Freeze and inspect questions before executing the model. Paired design allocates complete recall/task pairs; an odd budget leaves one unused call.
3. Inspect diagnosis hypotheses and actual supplied-memory receipts. Source overlap and exact source-and-fact correspondence are separate proxies. An old fact and its update may share one message; shared message identifiers do not establish that the required fact was stored or supplied. Expand diagnosis rows to compare reference, stored and actually supplied text. Paraphrases or bundled records can preserve meaning without matching exactly. Such mismatches require fact review rather than automatic encoding or generation attribution. A passed answer with incomplete correspondence is an **unattributed pass**, not a detected retrieval failure; a pass with an unknown input receipt remains unobserved.
   Diagnosis v3 also separates historical trace records from answer-time retrieval
   eligibility. A visible record may already have been evicted. Capacity exclusion
   is established only by the saved ranking/eligibility observation for that
   answer, never by its current lifecycle state. An observed eligible exact copy
   prevents treating a duplicate removed copy as unavailable. Legacy or ambiguous
   eligibility remains unknown. Other update/diagnostic exclusions are shown
   separately; none of these observations establishes the sole causal explanation.
4. Record the rationale and prepare original, generic and targeted conditions. Canonical changes propagate within this new package. Completed source questions cannot be mutated by replay edits.
5. Run conditions. Pause stops after the current condition is durably saved. After a refresh, restore verifies database progress; frozen suites remain readable while edits remain prohibited.
6. Inspect paired answers and regressions, then validate the general rule on new histories. A different history ID is insufficient to establish independence. Exact overlapping source messages are rejected; semantic/template independence still needs review.

For a capacity-exclusion hypothesis, the workbench offers a **candidate memory
capacity**. Only the candidate receives this value; original and generic controls
retain the source capacity. The suggested capacity intervention retains the
source retrieval strategy, base instructions and reader policy. Configuration
name/version changes are recorded; no expected answers are inserted. A candidate
that changes only capacity still increases the memory budget and may increase
cost. Do not describe its improvement as an equal-budget retrieval advantage.
Opaque external targets do not expose this controlled-store capacity field.

New-history experiments are labelled **candidate held out** until independent scenario and label review. Diagnostic replays are exploratory. A favourable replay alone does not show generalisation.

## Diagnostic interventions

The workbench offers original context, memory removal and source supplementation. Supplementation is an **oracle diagnostic intervention**: auditor evidence identifiers select authorised raw source excerpts. It is not a deployable memory repair or a fair normal target configuration. It keeps the frozen retrieval strategy and generation policy, but prioritises a diagnostic packet. Packets persist as `DIAGNOSTIC_ONLY` for traceability and cannot enter another question's normal retrieval or retention capacity.

## Auditor reliability

Automated or AI pre-review does not create independent human references. The dedicated blind review page hides target identity, automated verdicts and other reviewers' labels. Use distinct reviewers; adjudication requires two independent references. Unavailable or invalid LLM judges abstain with an uncertain result. Advisory fallback labels are excluded from decided-test metrics.

The reliability page separates binary pass/fail agreement from failure-category accuracy. Category accuracy uses jointly detected failures with known human categories; detection-and-classification recall also counts human failures missed by the auditor. Unknown human categories are excluded explicitly. Human-labelled uncertain answers count toward review coverage and labelled abstention, but not binary decision accuracy. The page shows unmeasured metrics when eligible labels do not exist. Wilson intervals describe the reviewed items, not independent scenario confidence. Questions within a history are correlated; formal analyses must use histories/scenarios as the resampling unit. An independent defect inventory is necessary to measure how many underlying failures the auditor missed.

Method comparisons freeze three independently generated suites (direct reference, fixed template and paired probes) under equal call caps. Compare **actual calls** as well as caps. Count distinct human-confirmed failure families per history; do not use raw failure counts or target pass-rate improvements as auditor reliability.

## Independent example service

`reference_target/` is a separate FastAPI process with its own SQLite database and no auditor imports. Its strict ingest/answer contract accepts only history, frozen target settings and questions. Namespaces and request IDs are idempotent and reject conflicting reuse. It supports local Qwen and backend-configured OpenRouter.

Start the optional `external-demo` Compose profile and set backend `EXTERNAL_TARGET_URL=http://reference-target:8010`. The service has no host port. It is a simple keyword-memory demonstrator, **not** a Mem0/Zep integration or production memory product. Its profiles affect whole-message retrieval; it is not equivalent to the controlled target's extracted-fact store. Treat its audit trace as black-box: a response is not an authenticated memory-input receipt.

## Remaining scientific evidence

Software checks can demonstrate isolation, state transitions, reproducibility and recovery. They cannot certify all future questions or establish market novelty. Formal claims require independently labelled multi-domain scenarios, defect inventories, reviewer disagreement resolution, equal-budget established baselines and scenario-level uncertainty. Vendor/cloud performance requires actual configured credentials and live runs; local Qwen results cannot substitute for these claims.

A single report labels partial dimension coverage as a tested-ability average. Its derived `formal_overall_score` is available only when all four core dimensions have decided scores, including zero. Every failure includes ordered original source statements selected within its own authorised conversation; canonical facts alone do not substitute for raw source evidence. Historical evaluation verdicts remain immutable.

Retrieval quality only scores traces explicitly linked to a saved final answer.
Unlinked historical or failed-attempt traces remain inspectable but are excluded;
the report discloses their count. A retrieval event alone does not establish a
completed model call or its input. This deliberately removes the legacy latest-
trace fallback rather than silently crediting unverified historical attempts.

Rule judge v29 limits its lexical negation window at explanatory and contrast
clause connectors. The round50 phrase “instead of MariaDB because PostgreSQL”
exposed a false failure in v28. Historical verdicts remain immutable; the apparent
round50 strategy gain must not be treated as improvement evidence. This repair
addresses that measured rule error only; unsupported explanations and broader
semantic correctness still require independent review.

## Local semantic pre-review

The behavioural evaluator can now use Ollama independently of the target provider and the extraction/generation pipeline. Select the local provider under Behaviour evaluator and record an installed model name. The pipeline remains rule-based or a supported cloud provider; this change does not add Ollama extraction or training.

The local judge uses the official Ollama chat structured-output schema, non-streamed completion, disabled thinking and bounded context/output. It receives the test, complete answer and relevant confirmed/edited reference memories; target memories remain a separate input boundary. Local definitive verdicts must cite a supplied evidence ID. Invalid JSON, foreign IDs, uncited definitive decisions, incomplete/length-truncated replies and provider errors remain unscored with a disclosed advisory rule result. These contract checks do not establish semantic correctness.

Local judge v3 also preserves a source-check abstention. For example, a response requiring Python 3.12 when the source only requires Python remains unscored even if the semantic judge returns a boolean verdict. The receipt records `review_source_uncertainty`, both original explanations and the source-check version. A disagreement remains a separate review reason. Saved v2 results are not rewritten or paired with v3 results as evidence of improvement. Agreement still does not establish correctness: the Ballarat/Wattle development run contains a passed explanation inventing robustness and scalability as the migration reason. Independent calibration is still required.

Rule judge v31 adds a narrow abstention check for asserted quality/cost causal explanations. A source saying only that the database changed does not establish that robustness, scalability or cost caused the change; mentioning a property without a source causal link is also insufficient. Explicitly hypothetical or unknown reasons are distinguished from assertions. This lexical provenance check does not prove semantic entailment, cover all paraphrases or validate other explanations. Local judge v3 preserves its abstentions. Historical v30 scores remain unchanged and cannot be used to show model improvement by comparing them with v31 scores on the same answers.

The Launceston/Acacia development GUI run triggered this guard on a real Qwen response claiming MongoDB provided a more flexible and scalable solution as the migration reason. The semantic judge returned pass, but the saved result remains uncertain with `review_source_uncertainty`; both original explanations are retained. This demonstrates one actual prevented false pass, not independently measured evaluator accuracy or failure recall. The Geelong/Melaleuca run did not trigger this branch. Neither run is an unseen scientific test set.

Formal synthetic matrix v2 freezes the actual controlled-adapter, memory-writer and evaluator versions, plus a SHA-256 fingerprint of the complete backend application Python source. Before target execution and response evaluation, installed software must match the saved signature. Version drift, source changes without a version bump, and legacy formal records missing the signature stop before provider calls or state changes. Existing replies and verdicts remain available. Restoring the original software permits continuation; a revised implementation requires a newly reviewed dataset release/experiment rather than rewriting the old signature. Ordinary development audits retain their existing workflow. These safeguards do not establish human-label validity, source-data immutability, environment/dependency reproducibility or independence of held-out scenarios; those require separate acceptance evidence.

Every local result is labelled AI semantic pre-review, uncalibrated and not independent human validation. Using the same model as both target and judge may reproduce shared errors. Select another judge where available and independently adjudicate source statements, core answers and material explanations. Reader request receipts do not measure judge token costs, retries or latency; no equal-total-cost claim follows from reader-only counts.

Implementation reference: https://docs.ollama.com/capabilities/structured-outputs and https://docs.ollama.com/api/chat .

## Judge execution evidence

Migration0021 adds nullable judge execution receipts to saved evaluations. Historical and deterministic-rule results remain null: unknown cost is not zero. LLM receipts record provider/model, actual HTTP attempts including retries, failed HTTP/transport attempts, elapsed time including retries, and provider-reported usage from the last successful HTTP reply. Missing or malformed usage stays unknown. A failed semantic verdict may still have a paid successful provider reply; its usage is retained even when excluded from accuracy scores. Concurrent evaluations use separate context-local meters. No prompt, reply payload, URL, header, credential or upstream error is stored in the meter.

These receipts are visible in reference/adjudication review alongside the automatic reasoning, and omitted from independent blind review. They do not include extraction/test generation, lower-level connection retries, aborted unpublished evaluations, all failed-attempt token usage, monetary price or hardware costs. Summing final-reply tokens alone does not establish equal total experiment cost.


Formal synthetic matrix v3 also makes the imported human reference suite read-only from creation: acceptance/rejection and regeneration routes reject changes even before the first target call. Its saved-input SHA-256 covers source messages (speaker/order/timestamps), confirmed facts and their provenance/status, relationship edges, each run's reference tests, the canonical suite link, suite configuration and controlled model/retrieval/execution settings. Execute and evaluate recheck this digest before calls or state changes; legacy formal rows without it require a newly reviewed release. UTC-normalised timestamps prevent database timezone round-trips causing false drift. Generated retrieval context and lifecycle status are deliberately excluded, so an unchanged experiment can proceed from execution to scoring. This is drift detection, not cryptographic protection against an operator who can rewrite both the database content and digest. It does not verify external model weights, package dependencies, human-label authenticity or held-out independence. Old reports remain readable rather than being re-scored.


Formal matrix v4 identifies a condition by memory strategy, service, deployed model and temperature, rather than strategy alone. Different models can therefore share one memory policy and the same reference suite with separate response/evaluation rows. Condition names are display labels and cannot bypass duplicate detection; model names are trimmed. The research UI accepts one model per line on the selected service and forms the model × strategy matrix with a 2–8-condition cap. It shows the planned count before creation, and retains the matching independent-review readiness gate. Local model names must already be deployed. A rule-based baseline remains a deterministic reference, not another language model; adding a model name does not make it an LLM. Cross-model runs isolate model choice only if policy, writer, questions and inference settings are held fixed; changing temperature or service can add confounds and must be reported. Separate target calls do not by themselves prove semantic assessment reliability or scientific independence.


Formal matrix browser recovery reads each audit's durable status before progressing. Completed conditions are skipped, saved responses proceed to evaluation, and failed conditions use the stage planner before status is rechecked. Cancelled or otherwise incomplete conditions cannot produce a matrix-complete message. A lightweight same-tab plan survives component remount/refresh; it stores matrix identities and counts, not uploaded source/annotation packages. Displayed progress counts conditions verified complete during the current check, rather than assuming a recovered plan proves completion. Retry itself now checks the formal software and saved-input digests before touching FAILED state or invoking the stage planner. Drift/missing legacy fingerprints therefore preserve state even at recovery entry; unchanged failed formal runs can recover their saved answers to completion. These are engineering recovery guarantees, not evidence of human semantic accuracy. Controlled ordinary GUI regressions remain distinct from formal production human acceptance.

Independent failure-category review must start without a preselected class.
The blind endpoint returns only question identity, wording and reference behaviour,
plus source excerpts and the exact response; generated dimension and quality metadata
are withheld. The UI requires an explicit category before an independent Fail label,
while Pass has no failure class. This removes a default-value bias; it does not prove
reviewer independence or semantic correctness. Use the dedicated blind workspace and
reviewers who have not seen automated results, rather than the results-page panel,
for formal independent annotation.

All semantic judge providers now use v4 evidence safeguards. A boolean verdict must
cite valid reference facts. A source-check abstention remains unscored, and a
semantic/rule disagreement remains pending review, for both local and cloud
providers. Saved receipts retain the original verdicts, explanations and rule
version; comparison requires that cross-check version. Previous provider versions
are not rewritten or compared with v4 as evidence of model improvement. These
contracts were checked with isolated provider substitutes; they do not establish
live cloud-provider accuracy. Agreement can still share an unsupported explanation
or other semantic error, so all such results remain uncalibrated AI pre-review.

Memory policy v6 distinguishes explicit personal-preference cues from the bare
state-replacement phrase “rather than”. New target stores therefore do not label
such replacements as preferences solely because of that phrase. Historical stores
retain their original scope labels. These are heuristic categories, not verified
semantic labels; incorrect history claims can still pass lexical assessment and
need independent adjudication. A new development GUI run demonstrates corrected
scope display and one excluded unsupported causal explanation, not measured
failure recall or independent diagnosis-guided improvement.

Comparison display uses one paired population for dimension changes: identical
canonical questions with comparable decided assessments. Exact dimension tables
and shared charts use those same pairs. Full-suite bars remain descriptive and do
not display change deltas; differing questions or excluded judgments cannot
produce an apparent improvement value there. Missing pairs are unmeasured.
These denominator safeguards do not establish semantic correctness or eliminate
selection bias when uncertain judgments are excluded; report coverage and use
independent calibration before scientific claims.

## Supporting-reference provenance guard (diagnosis v4)

Before attributing a pass or failure to target-memory behaviour, all declared
supporting references must resolve within the audited conversation, contain a
nonempty fact, and link to actual authorised source messages in that conversation.
Missing or malformed legacy reference evidence is reported as incomplete evidence:
`unobserved_pass` for a passed answer or `unobserved` for a failed answer. An
uncertain assessment remains `uncertain_assessment` regardless of provenance.
The original verdict is preserved; restoring provenance does not itself prove
semantic correctness or causal model reliance.

The isolated regression matrix covers five deliberate reference defects across
pass/fail/uncertain verdicts. These seeded structural checks establish the guard's
behaviour, not independent human-calibrated diagnostic accuracy. Current valid
GUI histories are verified separately without corrupting operational evidence.

## Evidence-qualified candidates (diagnosis v5)

The recommendation now preserves the original instructions and controlled budgets.
Only decided failures with an observed retention-capacity hypothesis prefill a
capacity-only candidate. A decided retrieval hypothesis can prefill a scope-aware
retrieval candidate when capacity exclusion is absent and this is a real strategy
change. Profile naming/version changes are metadata; scope/current-state switches
and existing instructions are preserved. Reader-setting differences are still
reported and must be considered when interpreting strategy changes.

Uncertain verdicts, incomplete provenance, fact-text correspondence questions,
unknown past availability, generation hypotheses and policy exclusions require
review before choosing a repair. An independent service does not acquire memory
controls merely because the auditor offers an experiment form. No-op strategy
changes, capacity at the supported limit and no observed gaps preserve the base
configuration. The UI states why a candidate is suggested or why review comes
first. Users can still design an explicitly exploratory experiment.

The recommendation decision-boundary contracts test engineering behaviour; they
are not an independently labelled fault inventory or proof of causal diagnosis.

## Selection, final supply and profile exclusions (diagnosis v6)

A selected fact and an actually supplied fact are different observations. Exact
support selected by retrieval but missing from the final receipt is now an input
assembly review, with any other missing units still left open. Unknown final
receipts remain unknown, not empty. An exact duplicate supplied through another
record prevents claiming that this source-and-text unit was omitted.

Explicit `profile_context_budget_excluded` observations for unambiguously eligible,
unselected records are reported as context-limit review. Project/current-state
profile exclusions are reported separately. The generic budget reason does not
identify whether the retrieved-record limit or character limit bound; the system
therefore retains the configuration and asks for review instead of automatically
changing strategy or both budgets. Duplicate or incomplete ranking observations
cannot establish a budget exclusion. Facts unrelated to the question do not count.

These stage observations supplement stored/supplied correspondence and answer-time
availability. They remain exact-match proxies, not semantic completeness or proof
of a unique cause. The seeded regressions and new GUI pressure test validate stage
boundaries, not independent human-calibrated diagnostic accuracy.

Expanded automated-assessment text uses the shared friendly presentation helper to replace internal evidence IDs. This is a display transformation only: API results and evidence exports retain the original assessment for reproducibility. GUI round83 covers an empty-memory target; round82 covers a one-record context limit and an unattributed correct response. Neither is independent semantic calibration.

Diagnosis v7 treats a failed controlled-memory `no_memory` condition with an observed empty final memory receipt as an intentional reference outcome. It retains the original configuration and does not infer a broken retrieval mechanism or automatically enable memory. Unobserved receipts still require evidence review; a correct response lacking supplied support remains unattributed. This does not certify stored-memory quality or make an enabled-memory comparison a demonstrated diagnosis-guided repair.

GUI round84 is a fresh engineering regression with different fictitious facts. It shares the development scenario template and is not a prospective independent held-out scientific study. A no-memory factual failure is also compatible with a model correctly abstaining from unsupported personal facts: the factual task score and grounded abstention are different criteria.
