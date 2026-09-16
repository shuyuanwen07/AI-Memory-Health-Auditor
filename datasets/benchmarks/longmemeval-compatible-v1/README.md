# LongMemEval-compatible local sample

This is a tiny synthetic compatibility sample, **not LongMemEval data** and not a benchmark result. It exists solely to test the import contract in `backend/app/benchmarks/longmemeval.py`.

The adapter accepts a JSON array, or an object whose record list is called `records`, `data`, `questions`, or `examples`. Each record needs:

- `question_id` (or `case_id` / `id`);
- `question` (or `query` / `prompt`);
- `answer` (or `expected_answer` / `reference_answer`);
- session context under `haystack_sessions`, `sessions`, `conversation`, or `messages`.

Obtain official benchmark data independently, check its licence and citation requirements, de-identify any extra data, and validate it through `POST /api/v1/research/benchmarks/longmemeval/validate`. The endpoint validates and normalises input only; it does not download, run, score, or redistribute external data.
