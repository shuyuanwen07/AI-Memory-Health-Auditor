# Selected experiment evidence (29 October 2026)

This folder contains the latest database snapshot, newly run exploratory audits, and selected evidence underlying the dashboard's A/B/C and AC1–AC3 results. The earlier A/B/C evidence package remains available in `research/evidence-20261027/`. These archives contain experiment data; the user has approved publication of the included conversations.

- `key-experiment-evidence-20261029.tar.gz`: selected experiment summaries, paired analyses, review returns, adjudications and cost evidence. Paths inside the archive are relative to the workspace.
- `new-audits-20261029.tar.gz`: five recent exploratory audits, their failed generation attempts and the 36-answer summary. See `NEW-AUDITS.md` for scope and limitations.
- `new-audits-review-20261029.tar.gz`: blank review forms and materials for the 52 new answers. These are awaiting human review.
- `audit-database-final.sql.gz`: database snapshot after the 52-answer exploratory audits, excluding authentication sessions and transient locks. The later AC2 feasibility attempts are preserved in their own ledger, not this snapshot.
- `ac2-prospective-feasibility-20261029.tar.gz`: frozen synthetic sources, source review, full product-flow ledger and blank review materials for the later AC2 feasibility study. Most attempts failed generation; it does not establish AC2 validity.
- `ELEC5623_Memory_Auditor_Final_Results_2026-10-29_v60.pptx`: latest existing presentation, including speaker notes.
- `presentation-source-scripts.tar.gz`: presentation authoring scripts, excluding dependencies and render caches.

Full historical archive parts remain only in the original local workspace and are not part of the current checkout. To inspect an archive, extract it into an empty directory; extraction into an existing checkout can overwrite files. Restore the database only into a fresh compatible PostgreSQL database, after backing up any existing database.

Credentials and the provider account-limit snapshot are excluded. `NEW-AUDITS-SHA256SUMS` verifies the latest audit and database files; `SHA256SUMS` verifies the selected evidence and review archives.
