# Real-model benchmark pilots

Open **Experiments → Research tools → Real-model benchmark comparison**.
Upload a permitted LongMemEval subset (up to 8 cases, 1 MB), review its questions
and references, select Ollama or OpenRouter and one deployed model, then select
up to four memory strategies. Confirm permission to send this source to the
selected provider and run the comparison. Credentials remain backend-only.

The adapter accepts both the project's flat local format and official session
arrays, preserving user/assistant roles, aligned session dates and question
dates. Explicit invalid dates or misaligned session arrays are rejected.
Missing dates use a deterministic fallback; they do not establish real temporal
order. For the upstream weekday date format without a timezone, UTC is used as
a consistent storage convention, not an assertion of the user's real timezone.

Each condition and question runs in a separate temporary database with the
ordinary controlled memory store and rule-based writer. Gold answers,
`has_answer` and evidence-session labels stay outside model inputs. The writer
extracts user facts, so this is not a claim of complete assistant-memory or
all-category support. Capacity, retrieved-record and character budgets apply.
The reader model is called with its real connector. No model is trained.
All strategies use the same strong reader instruction; weak first-hit changes
retrieval only. Early v1 development evidence used a weak reader instruction for
weak retrieval and is confounded. Do not use v1 to claim isolated retrieval gains.

The screen displays lexical reference matches as exploratory proxies. A match
can include a negation or an unsupported explanation, and a paraphrase can miss
it; neither lexical matches nor token F1 are a calibrated semantic judgment.
Results are not official benchmark scores. The recorded seed is provenance;
it is not sent to the provider and does not guarantee deterministic generation.

Download evidence before leaving: it contains model replies, actual call
attempts, memory records and retrieval/supply flags, source and configuration
hashes and versions. Hypothesis downloads use the upstream `question_id` and
`hypothesis` JSONL layout. Run these with the upstream evaluator against the
matching authorised dataset, then independently review a frozen sample.
The reference annotations can change without changing model inputs; this is
covered by a metamorphic isolation test.

Cancellation aborts the browser request. The server checks disconnection and
stops before the next case; an already in-flight provider call may finish.
Temporary results are not added to audit history. Operational workflow tests
remain separate from this benchmark pilot.

Earlier GUI evidence used wholly synthetic data with the official input
structure. `output/official-benchmark-v1` now records acquisition of the official
MIT-licensed cleaned oracle file at revision
`98d7416c24c778c2fee6e6f3006e7a073259d48f`, its SHA256, all-500-case format
validation, a pre-execution sampling manifest, and actual GUI Qwen results for
eight cases. The selection covers six categories plus numeric-answer and
abstention cases without selecting on model responses. Oracle histories contain
only evidence sessions: this pilot cannot establish full-history retrieval
performance. Upstream semantic scoring, independent human labels, full-history
category studies and ranking comparisons remain incomplete. Hypotheses and a
blind review package are saved; condition mapping stays in a separate file.

Adapter v3 preserves finite numeric reference answers as text, including zero.
The official file contains 32 integer answers that v2 rejected; all 500 records
now validate. Boolean, structured and nonfinite references remain invalid.
Numeric reference conversion happens only on the auditor side and does not
change the target conversation.

Primary format and scoring reference:
[LongMemEval repository](https://github.com/xiaowu0162/LongMemEval).

## Import semantic assessments for a saved comparison

In **Experiments → Research tools → Review saved benchmark assessments**, upload
the original source JSON, downloaded live comparison evidence and one matching
upstream evaluator result file (JSONL or a JSON array). Choose the evaluated
condition and record the 40-character evaluator code commit used to produce
that file. Evaluation rows contain `question_id`, the exact `hypothesis`, and
`autoeval_label: {"model": "...", "label": true}` with a real Boolean label.
Use the upstream evaluator externally before importing; this import itself
does not call a model, train weights or create human annotations.

The [upstream scoring script](https://github.com/xiaowu0162/LongMemEval/blob/main/src/evaluation/evaluate_qa.py)
uses category-dependent semantic prompts, with separate treatment of
unanswerable questions. Its result file retains hypotheses and automatic labels.
Our importer validates source fingerprints, questions, references, categories,
condition membership and exact response text. It rejects duplicate or unknown
questions, changed responses and mixed evaluator models. Missing rows remain
pending; an overall pilot percentage appears only with complete coverage.
Per-category summaries and disagreements with lexical matching are available.

The report fingerprints the complete saved evidence and imported rows, in
addition to recording source/configuration fingerprints and the declared
evaluator model/revision. This is a binding/integrity check, not authentication
of the uploaded file's author, actual model execution, code revision or label
accuracy. Independently review automatic labels. Even full coverage of a small
saved pilot is not an official full-benchmark score. Files remain ephemeral;
download the bound report before leaving the page.

`output/semantic-import-v1` contains contract tests and an actual GUI import
check using real previously saved replies with deliberately artificial format
labels. The evaluator is explicitly named `IMPORT CONTRACT FIXTURE - NO JUDGE
WAS RUN`; these labels are not research results and are excluded from reliability
and performance conclusions. Official semantic scoring remains pending.

Ordinary audit configuration differs from the live benchmark: the historical
weak-first-hit condition also selects the weak reader instruction. Such ordinary
weak-versus-strong comparisons measure a combined configuration intervention,
not retrieval alone. Use the shared-reader live runner for isolated retrieval comparisons,
or ordinary full-context/scope-aware conditions that share the strong reader.
Do not relabel previous combined comparisons as pure memory-policy experiments.

The ordinary rule evaluator v27 abstains when an otherwise matching answer adds
programming-language versions absent from linked source evidence. This narrow
guard excludes uncertain results from scoring; it is not full semantic
verification. Other invented explanations remain subject to independent review.
The live benchmark retains its openly labelled lexical proxy and does not
silently substitute ordinary audit judgments for upstream benchmark scoring.

## Native memory and diagnosis-guided repair pilot

With the optional local Mem0 OSS service running, check **Include native Mem0
comparison**. The memory-only service performs native fact extraction and
retrieval; the ordinary auditor connector answers with the same strong reader
as the controlled reference. Native records have no fabricated original-source
attribution or source timestamps. This configured vector-search pilot is not a
claim about the best tuned Mem0 product.

Choose one controlled reference to enable **Compare native generic and directed
repairs**. Live runner v4 prepares each native history once and reuses its frozen
retrieval snapshot for three answer conditions: original, generic careful-answer
instruction, and versioned diagnosis-guided task filtering. The directed policy
uses only the question and native fact text, never reference answers. It changes
supplied records for explicit task queries only when a separable requirement
fact exists; preference queries and missing-task cases retain their context.
Bundled preference/requirement facts are retained. The current heuristic is
English-specific and does not resolve arbitrary entity conflicts.

Evidence records the shared snapshot hash, actual supplied IDs, removed IDs and
additional instructions. Preparation is charged once within each three-condition
comparison. Native service v2 observes actual SDK chat and embed attempts during
ingestion and retrieval, retaining per-call success, latency and vendor-reported
token counts when available. No prompts, replies or credentials are stored in
these usage events. The GUI sums shared preparation once and displays unknown
historical or partial instrumentation explicitly. A v2 real-service GUI pilot
in `output/native-cost-v1` observed four answer requests plus one preparation
LLM call and three embedding calls for one shared native snapshot. These are
counts for completed preparation, not billing estimates: model setup, network
retries below the SDK call, vector operations, aborted preparations, hardware
cost and monetary charges are not included. Reader requests alone are not total
system inference work. This small synthetic pilot validates observation, not
market superiority or independently judged repair benefit.

Freeze the diagnosis, implementation and new cases before execution. Preserve
negative results, regressions and ambiguous refusals. Do not tune the policy on
the prospective result and then present the same cases as untouched validation.
Synthetic prospective pilots and AI pre-review cannot replace independent human
labels or official benchmark scoring.

The later `output/longmemeval-official-v1` release separately freezes development and candidate held-out question IDs and evidence-session IDs, with complete cleaned-S histories and oracle controls. The seven-category development oracle GUI pilot completed21answers/21reader attempts; a matched complete521message knowledge-update history completed3answers/4attempts. All outputs and inputs were AI pre-reviewed, not human-labelled or upstream semantically scored. In the full-history run the current capacity retained50of240extracted records; all three answers abstained. These bounded negative results are preserved and do not establish benchmark rankings or successful repair benefit. Candidate held-out files remain unexecuted and are not certified independent on filler-session or theme overlap.
