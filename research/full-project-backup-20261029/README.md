# Selected experiment evidence (29 October 2026)

This folder contains the latest database snapshot, newly run exploratory audits, and selected evidence underlying the dashboard's A/B/C and AC1–AC3 results. The earlier A/B/C evidence package remains available in `research/evidence-20261027/`. These archives contain experiment data; the user has approved publication of the included conversations.

- `key-experiment-evidence-20261029.tar.gz`: selected experiment summaries, paired analyses, review returns, adjudications and cost evidence. Paths inside the archive are relative to the workspace.
- `new-audits-20261029.tar.gz`: five recent exploratory audits, their failed generation attempts and the 36-answer summary. See `NEW-AUDITS.md` for scope and limitations.
- `new-audits-review-20261029.tar.gz`: blank review forms and materials for the 52 new answers. These are awaiting human review.
- `audit-database-final.sql.gz`: post-experiment database snapshot, excluding authentication sessions and transient locks.
- `ELEC5623_Memory_Auditor_Final_Results_2026-10-29_v60.pptx`: latest existing presentation, including speaker notes.
- `presentation-source-scripts.tar.gz`: presentation authoring scripts, excluding dependencies and render caches.

Full historical archive parts remain only in the original local workspace and are not part of the current checkout. To inspect an archive, extract it into an empty directory; extraction into an existing checkout can overwrite files. Restore the database only into a fresh compatible PostgreSQL database, after backing up any existing database.

Credentials and the provider account-limit snapshot are excluded. `NEW-AUDITS-SHA256SUMS` verifies the latest audit and database files; `SHA256SUMS` verifies the selected evidence and review archives.
