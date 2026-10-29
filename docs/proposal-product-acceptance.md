# Proposal product acceptance review

Review date: 2026-10-28 (Australia/Sydney)  
Base revision reviewed: `40876e47e44f2af18187766a46976fe3bb15c3a5` plus the retained local working-tree changes

## Status update — 28 October 2026

The repository has since fast-forwarded to `40876e47e44f2af18187766a46976fe3bb15c3a5`; local implementation and documentation changes remain uncommitted. The new remote commit adds shared experiment evidence, not application behavior. A/B/C raw records and retrospective review metrics are now restored and independently hash-verified; see `docs/proposal-experiment-audit.md`. A separate post-fix synthetic intake retest now verifies that extraction, relationship analysis, and second-source review can complete on the current code; it stops with 14 candidates awaiting operator review, so it is not a full intake-to-results walkthrough. The research acceptance gaps remain: 13/48 question-validity decisions remain uncertain, six extraction candidates remain disputed, reference-unit recall is null, 32 review items remain unresolved in the formal cross-review, and independent blind provenance conflicts with original return declarations.

The current 40-item feedback supplied in chat matches the archived Shuyuan recheck for all 40 identifiers and decisions. It is retained as a post-disagreement assessment; it does not replace the original review files or establish an independent blind first-pass. One critical-error decision remains disputed between reviewers.

This is an engineering review of the current implementation, not a claim that
the proposal's formal research criteria have passed. The proposal's functional
workflow is substantially implemented. The remaining acceptance gaps mainly
concern independent human evidence, a frozen held-out protocol, and a complete
end-to-end receipt tied to this exact revision. The reviewed code is the local
working tree based on this commit; these working-tree changes have not been
committed or pushed to `origin/main`.

## Local assessed-source snapshot

A point-in-time source archive and per-file SHA-256 manifest are available at
`../output/proposal-delivery/source/AI-Memory-Health-Auditor-source.zip` and
`../output/proposal-delivery/source/source-manifest.json`. The manifest records
the base Git revision and marks the packaged tree as modified; this is a
content-addressed local snapshot, not a committed release or proof that the
current browser run used every packaged file. It excludes local experiment
exports and private review keys, which remain separate evidence artifacts.
Regenerate the archive after the final source edits, then record its resulting
manifest/archive hash with the submitted report. A fresh install/build against
the lockfile can establish package reproducibility, but it does not replace an
end-to-end receipt from the same source snapshot.

## Requirements

| Requirement | Current product state | Acceptance gap |
|---|---|---|
| FR1: upload authorised conversation history | Import and explicit consent/source-origin selection are implemented. | Permission declarations do not independently establish ownership or licence. |
| FR2: extract memories and relationships | Extraction and UPDATE/CONFLICT/CONTEXTUAL_OVERRIDE records are implemented. | Independent source-backed memory and relation labels are incomplete; formal extraction Precision/Recall is not established. |
| FR3: review and correct ground truth | Accept, edit, reject, add, and confirm workflows exist. | Human correctness of confirmed facts remains an operator responsibility. |
| FR4: generate four-dimension tests | Four dimensions, evidence slots, grounding checks, duplicate checks, and test review are implemented. The requested count is allocated with at least one question per ability; extra slots are distributed as evenly as available source-backed evidence allows. | Independent test-validity evidence is incomplete. A one-question dimension has a fragile score and remains reported with its sample count. |
| FR5: initialise controlled target | Controlled target memory, strategies, writer, and target connector are implemented. | Current-revision full workflow needs a bound run receipt. |
| FR6: execute and retain run settings | Target calls and run configuration/reproducibility metadata are persisted. | Recheck seed/sampling descriptions against the provider actually used; recorded-only seeds do not guarantee identical model outputs. |
| FR7: evaluate and classify failures | Rule-based and model-backed evaluation paths and uncertainty handling are implemented. | Formal classification accuracy requires independent reference labels and frozen thresholds. |
| FR8: present scores and evidence | Dashboard, dimension scores, failure details, and exports are implemented. | A final-version browser/export walkthrough should bind one run ID to its evidence and exports. |
| FR9: persist ground truth and sources | Conversation, message, memory, relationship, and evidence records are persisted. | This does not establish production-grade security or independent annotation provenance. |
| FR10: configure target and audit | Provider/model, strategy, generation, retrieval, and audit settings are selectable before execution. | Check final-version model-availability and recovery behaviour in the end-to-end receipt. |
| FR11: calculate health results | Measured dimensions and macro reporting are implemented; unmeasured dimensions can remain null. | Formal four-dimension interpretation requires valid, independently checked tests in all dimensions. |
| FR12: inspect detected failures | Reports preserve source, fact, prompt, expected behaviour, response, and verdict links. | Confirm this correspondence in the final-version saved-run walkthrough. |
| NFR1: explicit authorisation | Submission and research-data permission gates are implemented. | The application records declarations; it cannot authenticate the user's underlying rights. |
| NFR2: security and server-side credentials | Credentials are configured server-side; access-control and isolation checks exist. | These checks are not a penetration test, production identity system, or certification. |
| NFR3: explainability | Evidence-linked reports and exports are implemented. | Human comprehension of the explanations remains unmeasured. |
| NFR4: guided, validated use | Guided steps, validation, recovery, and actionable errors are implemented. | A real novice walkthrough is still required. |
| NFR5: reproducibility | Runs retain model, policy, prompt, budget, source, and suite metadata; frozen comparisons are supported. | External provider sampling and seed limitations must be disclosed; full reproduction is not guaranteed from a recorded seed alone. |
| AC1: validate extraction/relationships | Contracts and some reviewed synthetic evidence exist. | **Not established:** complete independent source labels and adjudication are missing. |
| AC2: executable, grounded tests | Quality gates and execution checks exist. | **Partly evidenced:** independent review of unsupported facts and test validity is incomplete. |
| AC3: held-out auditor performance | Blind-review and metric workflows exist. | **Not achieved:** independently labelled held-out data and pilot thresholds frozen before inspection are not established. |
| AC4: report scores and traceable evidence | Reporting and evidence paths are implemented; historical receipts exist, and the separate post-fix intake retest is recorded. | Bind a full current-revision intake-to-results walkthrough and export before claiming end-to-end acceptance; the latest retest awaits operator review and has no target run. |
| AC5: repeat and retain metadata | Shared suites, repetitions, and saved settings are implemented. | Historical repeats are engineering evidence; provider-controlled stochastic output and a final frozen research release remain limits. |

## Evidence-aware question allocation

The previous model-backed configuration divided the requested count evenly
across four abilities. At eight questions this required two slots per ability
and blocked the audit when one ability had only one distinct evidence slot.
That rule was stricter than the proposal and did not make the requested total
more useful when other abilities had additional evidence.

The proposal defines Experiment A Category Coverage as the proportion of the
four dimensions with at least one valid question. The new allocation keeps at
least one distinct evidence-backed question in each ability, then distributes
remaining slots as evenly as the confirmed evidence allows. For example, an
eight-question budget with capacities of 6/2/1/2 produces 3/2/1/2 rather than
blocking Conflict Resolution. It still blocks if an ability has no eligible
evidence or if the available distinct slots cannot fill the requested count.
Each saved suite records the exact allocation, and execution continues to
enforce that frozen allocation for every comparison condition.

One question can count for proposal category coverage, but it gives a fragile
score estimate; results retain each dimension's actual question count and
should be interpreted with that limitation. The configured minimum is one per
dimension, not two.

## Verification performed for this review

- Read the relevant proposal requirements and evaluation definitions.
- Traced the coverage preview endpoint, Agent planner/generator gate, saved-suite
  execution gate, and configuration screen.
- Confirmed the existing frontend dependency volume runs Vite 8.3.5, Vitest
  5.0.5, and TypeScript 5.7.3, matching `frontend/package.json`.
- Updated the configuration help text to explain the one-per-ability minimum
  and evidence-based allocation of remaining questions.
- Ran `npm test -- src/pages/NewAudit.workflow.test.tsx` in the frontend
  container after adding the sparse-evidence case: 40 tests passed. The run
  emitted existing React `act(...)` warnings in a synthetic-example test; no
  test failed.
- The UI case for an eight-question budget with evidence capacities 6/2/1/2
  previews 3/2/1/2 and leaves the start action enabled. Backend checks cover
  redistribution and rejecting a count larger than all available distinct
  slots before the planner is called.
- Re-ran `tests/test_llm_pipeline.py` and
  `tests/test_execution_coverage_gate.py` in the backend container after the
  quota change: 71 tests passed; one existing Starlette/AnyIO deprecation
  warning was reported.

No paid model request or database write was made for this review. The test used
mock API calls. A real novice walkthrough, independent research labels, and a
full current-revision run using a model-backed pipeline remain outside this
verification.
