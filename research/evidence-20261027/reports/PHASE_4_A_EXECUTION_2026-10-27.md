# Experiment A execution update — 27 October 2026

**All36 target answers completed.** Three histories × three construction methods × four questions. All nine conditions completed evaluation with no HTTP provider error recorded in this collection. This update supersedes the earlier pre-execution status; the earlier files remain historical snapshots.

The user explicitly approved all24 newly generated questions before execution. Together with the12 previously approved fixed-template questions, all36 have actual user-declared human-validity acceptances saved under Yichao Wang. Inventory acceptance by Yichao Wang and Shuyuan Wen was explicitly reported and confirmed by the user. These are recorded declarations; identities and independence are not authenticated by the application.

## Completed controls and evidence

- Three source-bound defect inventories and fixed-template releases were frozen before generation. Each inventory contains three known potential defects; discovery analysis unit remains distinct scenario-specific defect IDs, not a count of failed answers.
- Direct-ground-truth, rule-seeded researcher-reviewed fixed-template and contextual/indirect suites each use four questions, the same target and evaluator settings, and four actual target attempts in each condition. All server comparison-control checks passed. There was no post-outcome membership or threshold adjustment.
- Each condition covers all four intended dimensions, with automatic grounding/quality acceptance and explicit human validity approval: Category Coverage4/4=100%. This is test-category coverage, not failure-detection accuracy or evidence of discovering every defect.
- The target remains the frozen Luna reader with weak_first_hit retrieval. Target memory is built independently from authorised source, with empty gold expected behaviour/supporting gold IDs at the target boundary. Effective sampling remains model default; configured seed/temperature do not establish deterministic execution.
- All36 request bodies were reconstructed and verified against saved original HTTP-boundary SHA256; no request was resent for this verification.
- Nine JSON reproducibility bundles and nine CSV exports are saved. Bundle answer counts and pass/total fields match stored results. Automated outputs are retained under `private/A-api-exports` and have not been placed in reviewer ZIPs.
- Estimated recorded target usage$0.00769, within the existing authorised budget. This is a rate-based usage estimate, not a billing receipt.
-37 script tests passed, including six new tests for A review validation, uncertain predictions, disagreement, citations, missing mappings and exposure disclosure. Python compilation, diff-whitespace checks and frozen production-source hashes passed. No production code or Final Report/Word/presentation change was made in this continuation.

## Remaining independent actual-answer review

Two independently shuffled packets now each contain all36 actual A answers, original source messages, question text and frozen potential defects. Open `review.html`, then fill `labels-to-complete.json`. Each response needs pass/fail/uncertain, observed failure dimension when failed, supporting source message IDs, and explicit defect IDs actually demonstrated (an empty list when none apply). Record the actual reviewer identity, independent completion and prior exposure to automated A results. Question wording may suggest the construction method despite removal of method labels; blinding is therefore limited.

No actual-answer review has yet been received. Failure Detection Recall and Failure Discovery Rate remain **unmeasured**. The prior source-inventory approval and pre-execution question approval do not label newly produced answers. Two agreeing independent judgements or genuine adjudication, plus a complete researcher response-to-defect mapping, are still needed for the server's formal discovery metrics.

The read-only return validator `scripts/analyse_phase4_a_reviews.py` checks frozen material fingerprints, distinct reviewer names, source citations, complete IDs and explicit defect mappings. It keeps disagreement and uncertain cases unresolved and does not import or invent human labels. Software validation tests use explicit synthetic fixtures and are not research annotations.

Raw state: `artifacts/local/phase4-20261027/A-live.json`. Request proof: `A-verified-requests.json`. Server comparison results are embedded in A-live; independent response metrics are still null. Reviewer files: `A-blind-review/reviewer-1.zip` and `reviewer-2.zip`. Private key: `private/A-identity-key.json`; do not give this file or automated API exports to reviewers before they complete their judgements.

Run actual-return validation with:

```
python3 scripts/analyse_phase4_a_reviews.py artifacts/local/phase4-20261027/private REVIEWER1.json REVIEWER2.json NEW_ANALYSIS.json
```

B/C automatic collections remain complete as documented previously. Their independent Auditor reliability review is also still pending. No full Phase4 or final human-reliability completion claim is made.
