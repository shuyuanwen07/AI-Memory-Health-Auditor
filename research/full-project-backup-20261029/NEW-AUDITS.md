# Exploratory audits, 29 October 2026

Five separate audits used the OpenRouter `openai/gpt-6-luna` target and automated assessments. These are additional exploratory results, not replacements for proposal experiments A–C and not independently human-validated.

| Study | Histories | Questions | Accuracy | Freshness | Conflict resolution | Appropriate use |
|---|---:|---:|---:|---:|---:|---:|
| Single audit `RUN2D220099B3474F1CB3F4679CA7CBF74F` | 1 | 16 | 4/7 decided; 1 uncertain | 2/2 | 2/4 | 2/2 |
| Four separate audits combined | 4 | 36 | 4/20 | 3/4 | 7/8 | 0 decided; 4 uncertain |

The single audit's reported 76.8% is the average of ability percentages, not the question-level pass rate (10/15). The four synthetic histories are distinct but template-related; they are not independent random samples, and their combined figures are not one audit. The 2-question abilities in the single audit remain particularly small. The 36-answer set needs human review before treating automated judgments as ground truth.

The two failed attempts for the original conversation remain in the archive: one rule-generated suite failed the quality gate, and the model-generated suites were rejected for leaking reference answers. No unsuccessful generation was treated as a completed result.

`new-audits-20261029.tar.gz` preserves individual run artifacts, errors and the multi-history summary. `audit-database-final.sql.gz` is the final post-experiment database snapshot and supersedes the earlier snapshot contained in the larger archive. Authentication session and transient lock data are excluded.
