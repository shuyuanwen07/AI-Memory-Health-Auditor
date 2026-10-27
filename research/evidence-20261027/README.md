# 27 October 2026 experiment and engineering evidence

This directory shares the existing evidence with the project team. It does not
certify that formal independent reliability or all acceptance criteria passed.
No new model experiment or annotation was executed to prepare the archive.

## Open the material

The adjacent `reports/` directory contains readable engineering reports. Start
with `PHASE_4_REVIEW_METRICS_2026-10-27.md` for the latest retrospective human-review
metrics and the repository-root `PROJECT_READINESS_AND_REMAINING_TASKS.md` for
the readiness audit. Other status reports are dated checkpoints; some explicitly
describe work that was completed later. Preserve their original scope and dates.

In a **fresh checkout** of this repository, run from the repository root:

```sh
python3 -m zipfile -e research/evidence-20261027/experiment-evidence.zip .
```

The archive restores the original `artifacts/local/...` and
`output/engineering-verification/...` paths used by the analysis scripts. Check
existing local files before extracting into a working checkout: extraction may
overwrite matching paths. The restored paths remain Git-ignored deliberately;
the versioned archive and manifest are the shared copy.

`manifest.json` lists every archive member's SHA-256, total size, and archive
SHA-256. Archive CRC and all 360 file hashes were verified during packaging.
The packaging script `scripts/package_experiment_evidence.py` can rebuild the
bundle from the restored original directories without model/API calls. It
records the checkout used for packaging, which is separate from the historical
source commits and dirty-tree snapshots recorded inside each experiment.

## Contents and status

| Restored location | Evidence | Boundary |
|---|---|---|
| `artifacts/local/phase12-20261027/` | Real Luna target workflow, source/configuration, requests, reviews, API/browser exports, test and verification logs | Earlier source snapshot; later evaluator/generator changes are not retroactively covered; UI receipt says screenshots were not saved |
| `artifacts/local/phase3-20261027/` | Source snapshots, regression and bounded before/after cases, real retrieval-context replay | Synthetic engineering validation; not general or independent human accuracy |
| `artifacts/local/phase4-20261027/A-live.json` | 36 actual answers, three equal-budget methods, reviewed source/inventory records and exports | Ambiguous cases and frozen-defect limitations retained; no complete formal discovery claim |
| `artifacts/local/phase4-20261027/B-live.json` | 72 included actual Weak/Strong answers, three repetitions, failures and excluded recovery cases | Three related synthetic histories; effective model-default sampling |
| `artifacts/local/phase4-20261027/C-live.json` | 84 actual target answers and 84 benchmark judgements, paired ordering comparison | Official Oracle 14/500 local compatibility adaptation, not full official benchmark |
| `artifacts/local/phase4-20261027/upstream/` | Original benchmark source, dataset, upstream revisions and MIT licence | Preserve attribution and original dataset identifiers |
| `artifacts/local/phase4-followup-20261027/` | Same-answer v65 reassessment, six new development probes, tests and source hashes | Development probes do not replace uncertain original A cases |
| `artifacts/local/phase4-formal-review-20261027/` | Frozen review materials, original returns, user-reported declaration corrections, rechecks and derived metrics | Original AI/non-independent declarations conflict with subsequent user correction; both are retained. Recheck exposed first-round judgments and is not independent blind evidence |
| `output/engineering-verification/` | Original phase checkpoint reports and latest metric report | Checkpoint status can be superseded; do not change original scores or reinterpret missing evidence as success |

The review directories include outcome/identity association keys needed to
reproduce existing analysis. They are **not API keys**, but this evidence bundle
must not be supplied as an unseen blind-review packet. Existing blank review
packets should only be used for an appropriately designed new review; reading
this evidence reveals outcomes and earlier reviewer judgments.

## Analysis and data limitations

The saved original request bodies were in some cases reconstructed from frozen
templates and retained context, then verified against original HTTP-boundary
SHA-256 receipts. They are not new model calls or complete network captures.
Failed requests, retries, exclusions, old scores and uncertainty remain present.
Model prices in historical logs are estimates, not invoices or future guarantees.

Current review statistics are retrospective and conditional on the stated
denominators. Uncertain answers, question validity and unresolved categories or
coverage are not silently changed to pass/fail. No independent formal gold-label
certification, complete extraction recall, or complete Experiment A discovery
rate is implied by the presence of these files. The source-code implementation,
software-test performance and target-memory performance are separate claims.

All phase inputs were the authorised synthetic engineering conversations or
the public LongMemEval data bound to the saved MIT licence/revisions. The package
excludes `.env`, databases, caches, unrelated local participant materials, Final
Report and presentation files. Configured provider-secret values and
high-confidence key markers were scanned, including nested archives. This is
not a universal security/privacy certification. The archive includes the team
review names and their reported provenance as supplied for this project.

Historical Release20 and Harbour raw result directories were not found and are
not reconstructed or included as if recovered. Their documented summaries do
not replace original response evidence.

The files support offline inspection and analysis. They do not restore the
application PostgreSQL database or automatically make historical run IDs appear
in a teammate's Dashboard. Start the application separately using the repository
setup instructions and each member's own environment/credentials; do not rerun
paid experiment scripts simply to read these results.
