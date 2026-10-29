# Research and audit archive (29 October 2026)

These split, losslessly compressed archives preserve the ignored local research material alongside the tracked source. Individual parts are below GitHub's per-file limit. Original workspace files remain in place.

- `experiments.tar.gz.part-*`: historical experiment working files and raw results under `experiments/`.
- `output-artifacts.tar.gz.part-*`: `output/`, `artifacts/local/`, and the review working copy `reviewer-1(1)`. This contains an initial database export at `output/remote-main-backup-20261029/audit-database.sql.gz`.
- `auxiliary.tar.gz.part-*`: datasets, handoff materials, presentation production files and chart work files. Package dependencies are excluded.

The actual configuration secrets, login-session data, temporary locks, and the OpenRouter account-limit snapshot are excluded. Research cost evidence is otherwise retained. The public repository contains the conversation material and reviews that the user explicitly approved for publication.

To reconstruct the archives, from this directory run:

```sh
cat experiments.tar.gz.part-* > mha-experiments-all-20261029.tar.gz
cat output-artifacts.tar.gz.part-* > mha-output-artifacts-20261029.tar.gz
cat auxiliary.tar.gz.part-* > mha-auxiliary-20261029.tar.gz
shasum -a 256 -c SHA256SUMS
```

Extract into a separate empty directory before comparing or restoring files; extraction into an existing checkout can overwrite files. The PostgreSQL dump is a consistent export of audit data, excluding authentication sessions and transient locks. Restore it only into a fresh, compatible PostgreSQL database; never replace a populated database without an independent backup. A later database export, if present beside this README, supersedes the earlier archive snapshot.
