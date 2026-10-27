# Phase 3 — reliability improvements and bounded validation

Date: 27 October 2026, Australia/Sydney. **Phase 3's targeted implementation, root-cause review, regressions and engineering comparison are complete.** This is not a certification of general memory reliability or completion of the formal Phase 4 experiments. Remaining failures and unavailable historical evidence are recorded below.

Final Report, Word and presentation files were not edited. Historical results and frozen thresholds were not changed.

## 3.1 Root-cause findings

| Observed problem | Origin / evidence | Disposition |
|---|---|---|
| Historical Release20 26/36, below 75%, with two critical actor errors | Only summaries found. Expected raw directory absent from workspace and HEAD tree. | Keep original FAIL and two errors unchanged. Exact source/actor/event mechanism cannot be established; do not attribute it to retrieval or claim the original errors resolved. |
| Old evaluator missed its only reference failure | Saved development source requires grayscale charts; answer uses colourful charts. Shared noun “charts” previously passed. | Already addressed in v62, retained through v64 regressions. Prior nine-answer replay is development evidence with unverified label independence, not a new human reliability estimate. |
| Explicit owner change still passed in v63 | “My sister’s partner is Mira” versus “Your brother’s partner is Mira”. Tail-name matching ignored the owner. | v64 compares supported affirmative possessive relationship bindings. Explicit changed owner is failed and classified as Accuracy; a bare correct name remains allowed. |
| A Java override displaces database conflict context | In-memory target-owned ingestion/retrieval before change selects PostgreSQL plus unrelated Java under record budget 2. | Strong ranks a matched typed domain before unrelated policy priority; conflict endpoints are budgeted together. Weak first-hit remains byte-identical. |
| Partial conflict pair may enter a bounded context | Greedy per-record budget has no atomic link preservation. | Target-owned explicit conflict components become atomic budget units for Strong. If a component does not fit, withhold it and record the budget exclusion; never increase the allowed record/character budget. |
| Casual SQLite example and food/technical boundary create lifecycle edges | Historical Phase 2 smoke contains false UPDATE / CONFLICT edges. Substring “change” and negation were mistaken for changed facts. | Rule extractor v27 refuses these bounded no-change and topic-boundary relationships. No existing gold records or old scores are silently rewritten. |
| Keyword-style live grading misses a natural clarification question | Frozen follow-up smoke check did not recognize “Which database requirement should be followed?” | All original false flags retained. Validation scoring was not tuned after seeing results. This check needs a new development cycle and fresh validation before being used as a performance metric. |

The diagnosis separates extraction/writing, relation inference, retrieval/budgeting, target response, test specification and assessment errors. The earlier Phase 2 freshness abstention was a genuine missing-context outcome; the earlier “there” tail rejection of a correct PostgreSQL answer was an evaluator error. Neither is automatically evidence of a base-model defect.

## 3.2 Strong memory changes

- Query-derived typed domain match now precedes unrelated policy priority in Strong ranking. Uses the target question and its own records only.
- Target-owned CONFLICT links are retained as connected budget units after eligibility filtering. No access to auditor support IDs, references or gold values. Record and character budgets remain unchanged.
- Within the available eligible set, conflicting endpoints are either delivered together or excluded together when the full group cannot fit. This does not magically recover missing/unwritten endpoints or infer new facts.
- Reason strings identify complete conflict groups and budget-excluded groups. Weak, full-context and other policies retain their prior selection logic; Weak unchanged contexts were verified exactly across every development and reserved validation case.
- Original source text, speaker attribution and source timestamps remain attached to stored records. No answer-specific memory or supplementary provider call was introduced.

## 3.3 Evaluator and extraction changes

Evaluator **rule-based-v64** adds bounded source-owner binding checks. Supported syntax includes explicit possessive owner/relation/name assertions and reversed “Name is owner’s relation” wording. It recognizes a finite set of kinship/work relationships with simple names. An explicitly different owner for the same named relation cannot pass solely because the person’s name is present. Negative and hypothetical statements are not upgraded into positive claims. Ambiguous coreference, compound names, nuanced implications and general semantic entailment remain outside this bounded rule; no universal semantic accuracy claim is made.

Source-owner failures use classification method source-owner-binding-v1 and cite the supporting source memories. The optional LLM judge's existing disagreement/uncertainty gate is preserved: a synthetic semantic “pass” conflicting with the owner check becomes unscored review_disagreement, not a scored pass or an automatic semantic override. No live LLM-as-judge bias benchmark or independent calibration claim is made.

Rule extraction **v27** prevents the observed denial-of-change and food/technical boundary from becoming lifecycle relationships. Memory policy is **target-memory-policy-v43**. Target instruction template and base connector remain unchanged and were hash-checked against the Phase 1/2 snapshot. Retrieval/delivery remains logically isolated from auditor Ground Truth.

## 3.4 Comparison protocol and results

Before changing product code, the complete prior app source was copied into artifacts/local/phase3-20261027/before-source/app. Its hashes match the Phase 1/2 verified source manifest. A separate synthetic specification was frozen in datasets/phase3-engineering-v1/ before modification.

Development: two person identities and one project. Reserved validation: four different person identities and three different project names, with no development response tuning against validation outcomes. Same grammar/template families are reused, so this tests bounded transfer to reserved entities, not broad unseen-domain generalization. Labels are authored synthetic software specifications, not independent human reference labels.

The validation-code-freeze.json records source hashes before validation. Original and final implementations were run once against the reserved cases in separate Python processes. Product code was not changed after these results. Thresholds and specifications were not relaxed.

| Check | Development before → after | Reserved validation before → after |
|---|---|---|
| Evaluator verdict matches frozen software specification | 6/10 → 10/10 | 12/20 → 20/20 |
| Strong bounded-retrieval contract satisfied | 2/3 → 3/3 | 6/9 → 9/9 |
| Weak delivered context | unchanged | unchanged |

Retrieval contracts: budgets 1, 2 and 3; when only one record is allowed, do not supply a misleading half-conflict; when two or three fit, include both MySQL and PostgreSQL constraints. The one-record case can still supply an unrelated record and require target abstention; it is not a complete task answer. The main observed improvement is the two-record condition: old Strong sends PostgreSQL+Java; new Strong sends MySQL+PostgreSQL. Do not convert these contract counts into independent failure-detection precision/recall or population performance.

### Real target follow-up

Nine real OpenRouter openai/gpt-6-luna calls: three reserved projects × before-Strong context, after-Strong context and unchanged Weak context, with two-record / 800-character limits and 2048 generated-token limits. Same frozen question per project, same base model, unchanged Strong reader template for the before/after pair. Weak retains its original first-hit delivery and reader policy. No gold answer is passed to the target. This is real connector replay of frozen, source-derived retrieval contexts, not a second claim of a full application end-to-end run; Phase 1/2 already records that workflow.

| Condition | Real responses | Both source database values named | Frozen automatic task-check passes |
|---|---:|---:|---:|
| Before Strong | 3 | 0 | 0 |
| After Strong | 3 | 3 | 0 |
| Unchanged Weak | 3 | 0 | 0 |

All three after-Strong answers identify MySQL/PostgreSQL and ask “Which database requirement should be followed?” The automatic check's narrow wording fails to recognize that clarification form. Its 0/3 results remain unchanged. Source-option presence is only a text check and the preceding answer interpretation is AI-assisted source review, not independent semantic grading. **No target-score improvement, general reliability estimate, effect size or formal acceptance rate is claimed from this live check.** No further tuning was performed on these validation outcomes.

Requests and responses are saved in live-validation.json; each payload is verified against its original request-contract hash. The script initially encountered a Pydantic serialization error after the first response; live-script-failure-original.json is retained. Resume reused the exact saved first response, proved by equality checks, and called only the remaining eight targets. No repeated paid response was discarded or regenerated. Luna's provider-controlled sampling and absent seed mean exact answer reproducibility is not promised. The fixed order and small sample do not support causal generalization.

## Regression verification

- Final backend suite: **2715 passed, 8 PostgreSQL-only skipped, 1 upstream deprecation warning**; backend-final.log.
- All eight skipped PostgreSQL fixtures executed separately on the isolated migrated test database: **8 passed**; postgresql-final.log.
- New Phase 3 regressions: **16 passed**; development-regressions.log.
- Earlier focused budget/evaluator/judge suite: **302 passed**; focused-first.log.
- Engineering script tests: **25 passed**; script-tests.log.
- git diff --check passed. No frontend source changed during Phase 3; the Phase 1/2 581-test frontend/build result remains the applicable frontend verification.
- Source hash checks prove app code did not change after validation freeze. Configured API key scan found zero matches in saved Phase 3 text evidence. No Final Report/Word/presentation was changed.

Commands:

```sh
.venv/bin/python scripts/verify_phase3_contracts.py --split development --output artifacts/local/phase3-20261027/development-after.json
.venv/bin/python scripts/verify_phase3_contracts.py --backend-root artifacts/local/phase3-20261027/before-source --split validation --output artifacts/local/phase3-20261027/validation-before.json
.venv/bin/python scripts/verify_phase3_contracts.py --split validation --output artifacts/local/phase3-20261027/validation-after.json
.venv/bin/python scripts/run_offline_backend_tests.py --evidence-dir artifacts/local/phase3-offline-final
.venv/bin/python -m pytest scripts/tests -q
.venv/bin/python scripts/summarise_phase3_verification.py
# Paid real follow-up, already executed; do not rerun as offline verification:
docker compose exec -T backend python /scripts/verify_phase3_live.py --plan /tmp/phase3-live-plan.json --output /app/.engineering-smoke/phase3-live-validation.json
```

Cost evidence: 11,693 input tokens + 1,375 output tokens across the nine saved successful responses. Estimated US$0.0018568 at the session-checked standard listing (US$0.10/M input, US$0.50/M output), not an invoice. Well within the existing US$5 authorization. No semantic judge API calls were added.

## Evidence and remaining work

Main evidence: artifacts/local/phase3-20261027/. Frozen specifications: datasets/phase3-engineering-v1/. summary.json binds the paired results, Weak invariance, live response recovery and original output hashes. validation-code-freeze.json records before-validation source identity; current-source-manifest.json and phase3-source-and-protocol.tar.gz preserve the current implementation and protocol. Base commit remains b44ced90ea39eb569eaa6ea01dee4c3df5712085 with uncommitted working-tree changes.

Remaining limitations materially affect research claims:

1. Release20 raw records remain missing, so its original two critical errors cannot be reverified. Original 26/36 and failed 75% threshold remain unchanged.
2. Owner checks and synthetic validation are bounded; they do not establish general coreference, multiple-actor, multiword-name or broad semantic robustness.
3. The real follow-up automatic clarification checker has demonstrated false negatives. Retain these cases as used validation data; any future repair requires a newly frozen independent validation set, not repeatedly tuning and re-scoring these same cases.
4. Independent human labels, formal repeated Weak/Strong results, formal A/B comparisons and official-compatible LongMemEval consistency remain Phase 4 work. No software test count, AI-authored label or reserved-entity substitution is presented as independent human validation.
