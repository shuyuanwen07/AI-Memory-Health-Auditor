# Experiment A answer cross-check — 27 October 2026

The user reported that both Yichao Wang and Shuyuan Wen independently considered all36 responses correct, then explicitly requested an AI cross-check. That user-reported conclusion is preserved. It has not been expanded into fabricated per-case human citations or submitted as a reconciled formal reference release.

All36 original answers, their questions, source histories and final input receipts were reviewed. This is an AI engineering review, not independent human annotation.

Findings:3 answers match their requested fact;27 answers do not complete their memory task (9 current-database,9 task-specific language,9 unresolved-region conflict);6 accuracy questions need temporal-scope review because the answer truthfully reports historical MySQL while the generic recorded-database prompt lacks an explicit current-state restriction and its expected behaviour requires PostgreSQL. These6 should not be resolved solely by a keyword mismatch.

The retained automatic evaluator gives3 pass and33 fail (each method1/12). These are automatic outcomes, not a newly validated human reference or a comparative Auditor-effectiveness score. All33 automatically failed answers were supplied only a historical MySQL record. The relevant PostgreSQL migration, Java requirement and both North/South conflict records are present in the target store but absent from those final inputs. The frozen weak_first_hit strategy explains this retrieval omission; the model's caution about its limited input does not by itself demonstrate successful end-to-end memory performance. No frozen Weak policy, prompt, expected answer or original result was changed, and no new model request was made.

The user-reported all-pass conclusion and source-based review disagree. Retain that disagreement and reconcile actual per-case judgements rather than declaring either artificial100% human correctness or AI-generated human gold. Later reviewers viewing this cross-check have exposure to automatic results and must record reference/adjudication provenance instead of claiming a fresh blind review.

Detailed evidence: `artifacts/local/phase4-20261027/A-AI-cross-check.html` and `.json` contain all36 questions, actual answers, supplied records, source citations and individual AI findings. Original A-live and its request/export proofs remain unchanged. Formal response-reference and discovery metrics remain pending reconciliation and actual mappings.
